"""
Unit tests for ExtrinsicCalibrator class.

Feature: step-6-coordinate-mapping
Validates: Requirements AC-6.3.2, AC-6.3.3, AC-6.3.6

Tests homography computation, JSON serialization/deserialization,
and error handling for missing markers.
"""

import json
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.calibration.aruco_detector import ArucoDetector
from src.calibration.extrinsic_calibrator import ExtrinsicCalibrator

# Import helper functions from aruco detector tests
from tests.test_aruco_detector import (
    generate_marker_image,
    generate_multi_marker_image,
)


# Test configuration matching the design spec
TEST_CONFIG = {
    'calibration': {
        'aruco': {
            'dictionary': 'DICT_4X4_50',
            'marker_size_mm': 40.0
        },
        'aruco_markers': {
            'marker_0': [0.0, 200.0],
            'marker_1': [200.0, 0.0],
            'marker_2': [0.0, -200.0],
            'marker_3': [-200.0, 0.0],
        }
    }
}


def create_calibration_image_with_markers(
    marker_size_px: int = 60,
    image_width: int = 800,
    image_height: int = 600
) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    """
    Create a synthetic image with 4 ARUCO markers at known positions.
    
    Returns:
        Tuple of (image, ground_truth_corners)
    """
    # Position markers in a square pattern
    marker_configs = [
        {'marker_id': 0, 'marker_size_px': marker_size_px, 'x_offset': 400.0, 'y_offset': 100.0, 'rotation_deg': 0.0},
        {'marker_id': 1, 'marker_size_px': marker_size_px, 'x_offset': 700.0, 'y_offset': 300.0, 'rotation_deg': 0.0},
        {'marker_id': 2, 'marker_size_px': marker_size_px, 'x_offset': 400.0, 'y_offset': 500.0, 'rotation_deg': 0.0},
        {'marker_id': 3, 'marker_size_px': marker_size_px, 'x_offset': 100.0, 'y_offset': 300.0, 'rotation_deg': 0.0},
    ]
    
    image, ground_truth = generate_multi_marker_image(
        marker_configs,
        image_width=image_width,
        image_height=image_height
    )
    
    return image, ground_truth


class TestHomographyComputation:
    """
    Tests for homography computation with known point correspondences.
    
    **Validates: Requirements AC-6.3.2**
    """
    
    def test_calibrate_with_four_markers(self):
        """
        Calibration should succeed with 4 detected markers.
        
        **Validates: Requirements AC-6.3.2**
        """
        # Create image with 4 markers
        image, _ = create_calibration_image_with_markers()
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        # Create calibrator
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        # Run calibration
        result = calibrator.calibrate(camera_id=0, image=image_bgr)
        
        # Verify calibration succeeded
        assert result is not None, "Calibration should succeed with 4 markers"
        
        homography, debug_info = result
        
        # Verify homography shape
        assert homography.shape == (3, 3), "Homography should be 3x3 matrix"
        
        # Verify debug info
        assert debug_info['camera_id'] == 0
        assert len(debug_info['markers_used']) >= 4
        assert debug_info['num_points'] >= 16  # 4 markers × 4 corners
        assert debug_info['reprojection_error'] >= 0
    
    def test_homography_is_invertible(self):
        """
        Computed homography should be invertible (non-degenerate).
        
        **Validates: Requirements AC-6.3.2**
        """
        image, _ = create_calibration_image_with_markers()
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        result = calibrator.calibrate(camera_id=0, image=image_bgr)
        assert result is not None
        
        homography, debug_info = result
        
        # Check determinant is non-zero
        det = np.linalg.det(homography)
        assert abs(det) > 1e-6, f"Homography should be invertible, det={det}"
        
        # Verify we can actually invert it
        try:
            H_inv = np.linalg.inv(homography)
            assert H_inv.shape == (3, 3)
        except np.linalg.LinAlgError:
            pytest.fail("Homography should be invertible")
    
    def test_homography_with_known_correspondences(self):
        """
        Test homography computation with manually specified point correspondences.
        
        **Validates: Requirements AC-6.3.2**
        """
        # Create simple known correspondences
        # Image points (pixels)
        image_points = np.array([
            [100, 100], [700, 100], [700, 500], [100, 500],
            [150, 150], [650, 150], [650, 450], [150, 450],
        ], dtype=np.float32)
        
        # Board points (mm) - simple square mapping
        board_points = np.array([
            [-200, 200], [200, 200], [200, -200], [-200, -200],
            [-150, 150], [150, 150], [150, -150], [-150, -150],
        ], dtype=np.float32)
        
        # Compute homography directly
        homography, mask = cv2.findHomography(
            image_points, board_points, cv2.RANSAC, 3.0
        )
        
        assert homography is not None, "Homography computation should succeed"
        assert homography.shape == (3, 3)
        
        # Verify transformation works
        # Transform first image point to board coordinates
        pt = np.array([[image_points[0]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(pt, homography)
        
        # Should be close to first board point
        expected = board_points[0]
        actual = transformed[0, 0]
        error = np.linalg.norm(actual - expected)
        
        assert error < 1.0, f"Transformation error too large: {error}"


class TestJSONSerialization:
    """
    Tests for JSON serialization/deserialization round trip.
    
    **Validates: Requirements AC-6.3.3**
    """
    
    def test_save_and_load_calibration(self):
        """
        Saved calibration should be loadable and numerically equivalent.
        
        **Validates: Requirements AC-6.3.3**
        """
        # Create calibration
        image, _ = create_calibration_image_with_markers()
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        result = calibrator.calibrate(camera_id=0, image=image_bgr)
        assert result is not None
        
        homography, debug_info = result
        
        # Save to temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            calibrator.save_calibration(
                camera_id=0,
                homography=homography,
                debug_info=debug_info,
                output_dir=tmpdir
            )
            
            # Load back
            loaded = ExtrinsicCalibrator.load_calibration(
                camera_id=0,
                calibration_dir=tmpdir
            )
            
            assert loaded is not None, "Should load saved calibration"
            
            loaded_homography, loaded_metadata = loaded
            
            # Verify numerical equivalence
            np.testing.assert_array_almost_equal(
                homography, loaded_homography, decimal=6,
                err_msg="Loaded homography should match saved"
            )
            
            # Verify metadata
            assert loaded_metadata['camera_id'] == 0
            assert loaded_metadata['num_points'] == debug_info['num_points']
    
    def test_json_file_format(self):
        """
        Saved JSON file should have correct format and fields.
        
        **Validates: Requirements AC-6.3.3**
        """
        image, _ = create_calibration_image_with_markers()
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        result = calibrator.calibrate(camera_id=0, image=image_bgr)
        assert result is not None
        
        homography, debug_info = result
        
        with tempfile.TemporaryDirectory() as tmpdir:
            calibrator.save_calibration(
                camera_id=0,
                homography=homography,
                debug_info=debug_info,
                output_dir=tmpdir
            )
            
            # Read JSON file directly
            json_path = Path(tmpdir) / "homography_cam0.json"
            assert json_path.exists(), "JSON file should be created"
            
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # Verify required fields
            assert 'camera_id' in data
            assert 'homography' in data
            assert 'markers_detected' in data
            assert 'num_points' in data
            assert 'reprojection_error' in data
            assert 'calibration_date' in data
            
            # Verify homography is 3x3 list
            assert len(data['homography']) == 3
            assert all(len(row) == 3 for row in data['homography'])
    
    def test_load_nonexistent_file_returns_none(self):
        """
        Loading from nonexistent file should return None gracefully.
        
        **Validates: Requirements AC-6.3.3, AC-6.3.6**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ExtrinsicCalibrator.load_calibration(
                camera_id=99,  # Nonexistent
                calibration_dir=tmpdir
            )
            
            assert result is None, "Should return None for missing file"
    
    def test_serialization_preserves_precision(self):
        """
        JSON serialization should preserve numerical precision.
        
        **Validates: Requirements AC-6.3.3**
        """
        # Create a homography with specific values
        original_homography = np.array([
            [1.23456789, 0.00012345, 100.5],
            [0.00054321, 0.98765432, 200.5],
            [0.00000123, 0.00000456, 1.0]
        ], dtype=np.float64)
        
        debug_info = {
            'camera_id': 0,
            'markers_detected': [0, 1, 2, 3],
            'markers_used': [0, 1, 2, 3],
            'num_points': 16,
            'reprojection_error': 1.234567,
        }
        
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            calibrator.save_calibration(
                camera_id=0,
                homography=original_homography,
                debug_info=debug_info,
                output_dir=tmpdir
            )
            
            loaded = ExtrinsicCalibrator.load_calibration(
                camera_id=0,
                calibration_dir=tmpdir
            )
            
            assert loaded is not None
            loaded_homography, _ = loaded
            
            # Check precision is preserved (at least 6 decimal places)
            np.testing.assert_array_almost_equal(
                original_homography, loaded_homography, decimal=6
            )


class TestErrorHandling:
    """
    Tests for error handling with missing or insufficient markers.
    
    **Validates: Requirements AC-6.3.6**
    """
    
    def test_calibrate_with_no_markers_returns_none(self):
        """
        Calibration should return None when no markers are detected.
        
        **Validates: Requirements AC-6.3.6**
        """
        # Create blank image with no markers
        image = np.full((600, 800, 3), 200, dtype=np.uint8)
        
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        result = calibrator.calibrate(camera_id=0, image=image)
        
        assert result is None, "Should return None when no markers detected"
    
    def test_calibrate_with_insufficient_markers_returns_none(self):
        """
        Calibration should return None with fewer than 4 markers.
        
        **Validates: Requirements AC-6.3.6**
        """
        # Create image with only 2 markers
        marker_configs = [
            {'marker_id': 0, 'marker_size_px': 60, 'x_offset': 200.0, 'y_offset': 300.0, 'rotation_deg': 0.0},
            {'marker_id': 1, 'marker_size_px': 60, 'x_offset': 600.0, 'y_offset': 300.0, 'rotation_deg': 0.0},
        ]
        
        image, _ = generate_multi_marker_image(marker_configs)
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        result = calibrator.calibrate(camera_id=0, image=image_bgr)
        
        assert result is None, "Should return None with < 4 markers"
    
    def test_calibrate_with_three_markers_returns_none(self):
        """
        Calibration should return None with exactly 3 markers (need 4).
        
        **Validates: Requirements AC-6.3.6**
        """
        marker_configs = [
            {'marker_id': 0, 'marker_size_px': 60, 'x_offset': 200.0, 'y_offset': 150.0, 'rotation_deg': 0.0},
            {'marker_id': 1, 'marker_size_px': 60, 'x_offset': 600.0, 'y_offset': 150.0, 'rotation_deg': 0.0},
            {'marker_id': 2, 'marker_size_px': 60, 'x_offset': 400.0, 'y_offset': 450.0, 'rotation_deg': 0.0},
        ]
        
        image, _ = generate_multi_marker_image(marker_configs)
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        result = calibrator.calibrate(camera_id=0, image=image_bgr)
        
        assert result is None, "Should return None with exactly 3 markers"
    
    def test_calibrate_with_none_image_returns_none(self):
        """
        Calibration should handle None image gracefully.
        
        **Validates: Requirements AC-6.3.6**
        """
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        result = calibrator.calibrate(camera_id=0, image=None)
        
        assert result is None, "Should return None for None image"
    
    def test_calibrate_with_markers_missing_from_config(self):
        """
        Calibration should handle markers not in config gracefully.
        
        **Validates: Requirements AC-6.3.6**
        """
        # Config with only 2 marker positions defined
        limited_config = {
            'calibration': {
                'aruco': {
                    'dictionary': 'DICT_4X4_50',
                    'marker_size_mm': 40.0
                },
                'aruco_markers': {
                    'marker_0': [0.0, 200.0],
                    'marker_1': [200.0, 0.0],
                    # marker_2 and marker_3 NOT defined
                }
            }
        }
        
        # Create image with 4 markers (but only 2 have positions in config)
        image, _ = create_calibration_image_with_markers()
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        aruco_detector = ArucoDetector(limited_config)
        calibrator = ExtrinsicCalibrator(limited_config, aruco_detector)
        
        result = calibrator.calibrate(camera_id=0, image=image_bgr)
        
        # Should fail because only 2 markers have known positions
        assert result is None, "Should return None when insufficient markers have positions"
    
    def test_calibrate_with_empty_config(self):
        """
        Calibration should handle empty marker config gracefully.
        
        **Validates: Requirements AC-6.3.6**
        """
        empty_config = {
            'calibration': {
                'aruco': {
                    'dictionary': 'DICT_4X4_50',
                    'marker_size_mm': 40.0
                },
                'aruco_markers': {}  # No markers defined
            }
        }
        
        image, _ = create_calibration_image_with_markers()
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        aruco_detector = ArucoDetector(empty_config)
        calibrator = ExtrinsicCalibrator(empty_config, aruco_detector)
        
        result = calibrator.calibrate(camera_id=0, image=image_bgr)
        
        assert result is None, "Should return None with empty marker config"


class TestVerifyHomography:
    """
    Tests for verify_homography() reprojection error computation.
    
    **Validates: Requirements AC-6.3.2**
    """
    
    def test_verify_homography_perfect_fit(self):
        """
        Reprojection error should be near zero for perfect correspondences.
        """
        # Create perfect correspondences (identity-like mapping)
        image_points = np.array([
            [100, 100], [200, 100], [200, 200], [100, 200]
        ], dtype=np.float32)
        
        board_points = np.array([
            [-50, 50], [50, 50], [50, -50], [-50, -50]
        ], dtype=np.float32)
        
        # Compute homography
        homography, _ = cv2.findHomography(image_points, board_points)
        
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        error = calibrator.verify_homography(homography, image_points, board_points)
        
        # Error should be very small for perfect fit
        assert error < 0.1, f"Reprojection error should be near zero, got {error}"
    
    def test_verify_homography_with_noise(self):
        """
        Reprojection error should increase with noisy correspondences.
        """
        # Create correspondences
        image_points = np.array([
            [100, 100], [200, 100], [200, 200], [100, 200]
        ], dtype=np.float32)
        
        board_points = np.array([
            [-50, 50], [50, 50], [50, -50], [-50, -50]
        ], dtype=np.float32)
        
        # Add noise to image points
        np.random.seed(42)
        noisy_image_points = image_points + np.random.randn(4, 2).astype(np.float32) * 5
        
        # Compute homography with noisy points
        homography, _ = cv2.findHomography(noisy_image_points, board_points)
        
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        # Verify against original (non-noisy) points
        error = calibrator.verify_homography(homography, image_points, board_points)
        
        # Error should be larger due to noise
        assert error > 0.1, f"Error should be non-zero with noisy data, got {error}"
    
    def test_verify_homography_with_none_returns_inf(self):
        """
        verify_homography should return inf for None homography.
        """
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        image_points = np.array([[100, 100]], dtype=np.float32)
        board_points = np.array([[-50, 50]], dtype=np.float32)
        
        error = calibrator.verify_homography(None, image_points, board_points)
        
        assert error == float('inf'), "Should return inf for None homography"
    
    def test_verify_homography_with_empty_points_returns_inf(self):
        """
        verify_homography should return inf for empty point arrays.
        """
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        homography = np.eye(3, dtype=np.float32)
        empty_points = np.array([], dtype=np.float32).reshape(0, 2)
        
        error = calibrator.verify_homography(homography, empty_points, empty_points)
        
        assert error == float('inf'), "Should return inf for empty points"


class TestMarkerBoardCorners:
    """
    Tests for _get_marker_board_corners() helper method.
    """
    
    def test_get_marker_board_corners_marker_0(self):
        """
        Marker 0 at (0, 200) should have correct corner positions.
        """
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        corners = calibrator._get_marker_board_corners(marker_id=0, marker_size_mm=40.0)
        
        # Marker 0 is at (0, 200), size 40mm, so half_size = 20
        # Corners: TL, TR, BR, BL
        expected = np.array([
            [-20, 220],   # top-left
            [20, 220],    # top-right
            [20, 180],    # bottom-right
            [-20, 180],   # bottom-left
        ], dtype=np.float32)
        
        np.testing.assert_array_almost_equal(corners, expected)
    
    def test_get_marker_board_corners_marker_1(self):
        """
        Marker 1 at (200, 0) should have correct corner positions.
        """
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        corners = calibrator._get_marker_board_corners(marker_id=1, marker_size_mm=40.0)
        
        # Marker 1 is at (200, 0), size 40mm
        expected = np.array([
            [180, 20],    # top-left
            [220, 20],    # top-right
            [220, -20],   # bottom-right
            [180, -20],   # bottom-left
        ], dtype=np.float32)
        
        np.testing.assert_array_almost_equal(corners, expected)
    
    def test_get_marker_board_corners_unknown_marker_raises(self):
        """
        Getting corners for unknown marker should raise KeyError.
        """
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        with pytest.raises(KeyError):
            calibrator._get_marker_board_corners(marker_id=99)


class TestCalibrationIntegration:
    """
    Integration tests for full calibration workflow.
    """
    
    def test_full_calibration_workflow(self):
        """
        Test complete calibration: detect → compute → save → load → verify.
        """
        # Create test image
        image, _ = create_calibration_image_with_markers()
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        # Create calibrator
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        # Run calibration
        result = calibrator.calibrate(camera_id=0, image=image_bgr)
        assert result is not None, "Calibration should succeed"
        
        homography, debug_info = result
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save calibration
            calibrator.save_calibration(
                camera_id=0,
                homography=homography,
                debug_info=debug_info,
                output_dir=tmpdir
            )
            
            # Load calibration
            loaded = ExtrinsicCalibrator.load_calibration(
                camera_id=0,
                calibration_dir=tmpdir
            )
            
            assert loaded is not None
            loaded_homography, loaded_metadata = loaded
            
            # Verify loaded matches original
            np.testing.assert_array_almost_equal(
                homography, loaded_homography, decimal=6
            )
            
            # Verify reprojection error is reasonable
            # Note: Synthetic images may have higher error due to perspective transform artifacts
            assert loaded_metadata['reprojection_error'] < 15.0
    
    def test_calibration_with_different_camera_ids(self):
        """
        Calibration should work with different camera IDs.
        """
        image, _ = create_calibration_image_with_markers()
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            for camera_id in [0, 1, 2]:
                result = calibrator.calibrate(camera_id=camera_id, image=image_bgr)
                assert result is not None
                
                homography, debug_info = result
                assert debug_info['camera_id'] == camera_id
                
                # Save and verify file naming
                calibrator.save_calibration(
                    camera_id=camera_id,
                    homography=homography,
                    debug_info=debug_info,
                    output_dir=tmpdir
                )
                
                expected_file = Path(tmpdir) / f"homography_cam{camera_id}.json"
                assert expected_file.exists()


# =============================================================================
# Property-Based Tests
# =============================================================================

from hypothesis import given, strategies as st, settings


class TestHomographyCollinearityProperty:
    """
    Property-based tests for homography collinearity preservation.

    Feature: step-6-coordinate-mapping, Property 3: Homography Preserves Collinearity

    For any three collinear points in board coordinates, their transformed image
    coordinates should also be collinear (within numerical tolerance). This validates
    that the homography is a valid projective transformation.

    **Validates: Requirements AC-6.3.2**
    """

    @staticmethod
    def create_known_homography() -> np.ndarray:
        """
        Create a known valid homography matrix for testing.

        This homography represents a realistic camera-to-board transformation
        with perspective distortion.
        """
        # Define corresponding points (image → board)
        # Image points (pixels) - corners of a quadrilateral
        image_points = np.array([
            [100, 100], [700, 100], [700, 500], [100, 500],
            [200, 200], [600, 200], [600, 400], [200, 400],
        ], dtype=np.float32)

        # Board points (mm) - corresponding positions in board coordinates
        board_points = np.array([
            [-200, 200], [200, 200], [200, -200], [-200, -200],
            [-100, 100], [100, 100], [100, -100], [-100, -100],
        ], dtype=np.float32)

        # Compute homography: maps image → board
        homography, _ = cv2.findHomography(image_points, board_points)

        return homography

    @staticmethod
    def transform_board_to_image(
        homography: np.ndarray, board_points: np.ndarray
    ) -> np.ndarray:
        """
        Transform board coordinates to image coordinates using inverse homography.

        Args:
            homography: 3×3 homography matrix (image → board)
            board_points: N×2 array of board coordinates (mm)

        Returns:
            N×2 array of image coordinates (pixels)
        """
        # H maps image → board, so H_inv maps board → image
        H_inv = np.linalg.inv(homography)

        # Reshape for cv2.perspectiveTransform: (N, 1, 2)
        points_reshaped = board_points.reshape(-1, 1, 2).astype(np.float32)

        # Transform
        transformed = cv2.perspectiveTransform(points_reshaped, H_inv)

        return transformed.reshape(-1, 2)

    @staticmethod
    def compute_collinearity_error(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
        """
        Compute collinearity error using cross product.

        For three collinear points, the cross product of vectors (p2-p1) and (p3-p1)
        should be zero. We compute the normalized area of the triangle formed by
        the three points as a measure of collinearity error.

        Args:
            p1, p2, p3: 2D points as numpy arrays

        Returns:
            Collinearity error (0 = perfectly collinear)
        """
        # Vectors from p1 to p2 and p1 to p3
        v1 = p2 - p1
        v2 = p3 - p1

        # Cross product in 2D gives the signed area of the parallelogram
        # Area = |v1.x * v2.y - v1.y * v2.x|
        cross = abs(v1[0] * v2[1] - v1[1] * v2[0])

        # Normalize by the length of the longest vector to get a scale-invariant measure
        max_length = max(np.linalg.norm(v1), np.linalg.norm(v2), 1e-10)

        return cross / max_length

    @given(
        # Generate a random point on the board
        x1=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
        y1=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
        # Generate direction vector components
        dx=st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False),
        dy=st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False),
        # Generate two parameters for points along the line
        t2=st.floats(min_value=0.1, max_value=2.0, allow_nan=False, allow_infinity=False),
        t3=st.floats(min_value=2.1, max_value=4.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_homography_preserves_collinearity(
        self, x1: float, y1: float, dx: float, dy: float, t2: float, t3: float
    ):
        """
        Feature: step-6-coordinate-mapping, Property 3: Homography Preserves Collinearity

        For any three collinear points in board coordinates, their transformed
        image coordinates should also be collinear (within numerical tolerance).

        **Validates: Requirements AC-6.3.2**
        """
        # Skip degenerate cases where direction vector is too small
        direction_magnitude = np.sqrt(dx**2 + dy**2)
        if direction_magnitude < 1.0:
            return  # Skip - direction vector too small

        # Create three collinear points in board coordinates
        # p1 = (x1, y1)
        # p2 = p1 + t2 * direction
        # p3 = p1 + t3 * direction
        p1_board = np.array([x1, y1], dtype=np.float32)
        p2_board = np.array([x1 + t2 * dx, y1 + t2 * dy], dtype=np.float32)
        p3_board = np.array([x1 + t3 * dx, y1 + t3 * dy], dtype=np.float32)

        # Skip if any point is outside reasonable board bounds
        all_points = np.array([p1_board, p2_board, p3_board])
        if np.any(np.abs(all_points) > 300):
            return  # Skip - points too far from board center

        # Verify input points are collinear (sanity check)
        # Use relaxed tolerance for floating-point precision (float32 has ~7 decimal digits)
        input_error = self.compute_collinearity_error(p1_board, p2_board, p3_board)
        assert input_error < 1e-4, f"Input points should be collinear, error={input_error}"

        # Create a known valid homography
        homography = self.create_known_homography()

        # Transform board points to image coordinates
        board_points = np.array([p1_board, p2_board, p3_board])
        image_points = self.transform_board_to_image(homography, board_points)

        p1_image = image_points[0]
        p2_image = image_points[1]
        p3_image = image_points[2]

        # Compute collinearity error in image space
        output_error = self.compute_collinearity_error(p1_image, p2_image, p3_image)

        # Tolerance: allow small numerical error (1e-3 is generous for floating point)
        # The error is normalized by the longest vector, so this is scale-invariant
        tolerance = 1e-3

        assert output_error < tolerance, (
            f"Transformed points should be collinear.\n"
            f"Board points: {p1_board}, {p2_board}, {p3_board}\n"
            f"Image points: {p1_image}, {p2_image}, {p3_image}\n"
            f"Collinearity error: {output_error} (tolerance: {tolerance})"
        )

    @given(
        # Generate random line through origin
        angle=st.floats(min_value=0, max_value=2*np.pi, allow_nan=False, allow_infinity=False),
        # Generate three distances along the line
        d1=st.floats(min_value=10, max_value=50, allow_nan=False, allow_infinity=False),
        d2=st.floats(min_value=60, max_value=100, allow_nan=False, allow_infinity=False),
        d3=st.floats(min_value=110, max_value=150, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_homography_preserves_collinearity_radial_lines(
        self, angle: float, d1: float, d2: float, d3: float
    ):
        """
        Feature: step-6-coordinate-mapping, Property 3: Homography Preserves Collinearity

        Test collinearity preservation for radial lines from board center.
        This is particularly relevant for dartboard scoring where radial
        lines define sector boundaries.

        **Validates: Requirements AC-6.3.2**
        """
        # Create three collinear points along a radial line from origin
        cos_a, sin_a = np.cos(angle), np.sin(angle)

        p1_board = np.array([d1 * cos_a, d1 * sin_a], dtype=np.float32)
        p2_board = np.array([d2 * cos_a, d2 * sin_a], dtype=np.float32)
        p3_board = np.array([d3 * cos_a, d3 * sin_a], dtype=np.float32)

        # Verify input points are collinear (sanity check)
        # Use relaxed tolerance for floating-point precision (float32 has ~7 decimal digits)
        input_error = self.compute_collinearity_error(p1_board, p2_board, p3_board)
        assert input_error < 1e-4, f"Input points should be collinear, error={input_error}"

        # Create a known valid homography
        homography = self.create_known_homography()

        # Transform board points to image coordinates
        board_points = np.array([p1_board, p2_board, p3_board])
        image_points = self.transform_board_to_image(homography, board_points)

        p1_image = image_points[0]
        p2_image = image_points[1]
        p3_image = image_points[2]

        # Compute collinearity error in image space
        output_error = self.compute_collinearity_error(p1_image, p2_image, p3_image)

        # Tolerance for numerical precision
        tolerance = 1e-3

        assert output_error < tolerance, (
            f"Transformed radial points should be collinear.\n"
            f"Angle: {np.degrees(angle):.1f}°\n"
            f"Board points: {p1_board}, {p2_board}, {p3_board}\n"
            f"Image points: {p1_image}, {p2_image}, {p3_image}\n"
            f"Collinearity error: {output_error} (tolerance: {tolerance})"
        )

    def test_collinearity_with_calibrated_homography(self):
        """
        Test collinearity preservation using a homography computed from
        synthetic marker detection (integration test).

        **Validates: Requirements AC-6.3.2**
        """
        # Create image with markers and compute homography
        image, _ = create_calibration_image_with_markers()
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        aruco_detector = ArucoDetector(TEST_CONFIG)
        calibrator = ExtrinsicCalibrator(TEST_CONFIG, aruco_detector)

        result = calibrator.calibrate(camera_id=0, image=image_bgr)
        assert result is not None, "Calibration should succeed"

        homography, _ = result

        # Test with several sets of collinear points
        test_cases = [
            # Horizontal line through center
            [np.array([-100, 0]), np.array([0, 0]), np.array([100, 0])],
            # Vertical line through center
            [np.array([0, -100]), np.array([0, 0]), np.array([0, 100])],
            # Diagonal line
            [np.array([-50, -50]), np.array([0, 0]), np.array([50, 50])],
            # Line not through center
            [np.array([-100, 50]), np.array([0, 50]), np.array([100, 50])],
        ]

        for board_points in test_cases:
            p1_board, p2_board, p3_board = board_points

            # Verify input collinearity
            input_error = self.compute_collinearity_error(p1_board, p2_board, p3_board)
            assert input_error < 1e-6

            # Transform to image coordinates
            points_array = np.array(board_points, dtype=np.float32)
            image_points = self.transform_board_to_image(homography, points_array)

            # Check output collinearity
            output_error = self.compute_collinearity_error(
                image_points[0], image_points[1], image_points[2]
            )

            # Allow slightly larger tolerance for real calibration
            # (synthetic images may have small artifacts)
            tolerance = 0.1

            assert output_error < tolerance, (
                f"Collinearity not preserved for points {board_points}.\n"
                f"Output error: {output_error}"
            )

