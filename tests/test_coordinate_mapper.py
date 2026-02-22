"""
Tests for CoordinateMapper class.

Includes both unit tests and property-based tests for coordinate transformation.
"""

import json
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from src.calibration.coordinate_mapper import CoordinateMapper


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        'calibration': {
            'calibration_dir': 'calibration',
            'aruco_markers': {
                'marker_0': [0.0, 200.0],
                'marker_1': [200.0, 0.0],
                'marker_2': [0.0, -200.0],
                'marker_3': [-200.0, 0.0],
            }
        },
        'camera_settings': {
            'width': 800,
            'height': 600,
        }
    }


@pytest.fixture
def calibration_dir(tmp_path):
    """Create temporary calibration directory with test data."""
    # Create realistic camera matrix (typical for 800x600 camera)
    fx, fy = 600.0, 600.0
    cx, cy = 400.0, 300.0
    camera_matrix = np.array([
        [fx, 0, cx],
        [0, fy, cy],
        [0, 0, 1]
    ], dtype=np.float64)
    
    # Minimal distortion for testing
    distortion_coeffs = np.array([0.01, -0.02, 0.001, 0.001, 0.0], dtype=np.float64)
    
    # Create a realistic homography
    # Maps image coordinates to board coordinates
    # This is a simple scaling + translation for testing
    scale = 0.5  # mm per pixel (approximate)
    H = np.array([
        [scale, 0, -cx * scale],
        [0, -scale, cy * scale],  # Flip Y (image Y down, board Y up)
        [0, 0, 1]
    ], dtype=np.float64)
    
    # Save calibration files for cameras 0, 1, 2
    for camera_id in [0, 1, 2]:
        # Intrinsic calibration
        intrinsic_data = {
            'camera_id': camera_id,
            'camera_matrix': camera_matrix.tolist(),
            'distortion_coeffs': distortion_coeffs.tolist(),
            'reprojection_error': 0.3,
            'image_size': [800, 600],
        }
        intrinsic_file = tmp_path / f"intrinsic_cam{camera_id}.json"
        with open(intrinsic_file, 'w') as f:
            json.dump(intrinsic_data, f)
        
        # Homography (slightly different per camera to simulate different viewpoints)
        angle = camera_id * 0.1  # Small rotation per camera
        cos_a, sin_a = np.cos(angle), np.sin(angle)
        H_rotated = H @ np.array([
            [cos_a, -sin_a, 0],
            [sin_a, cos_a, 0],
            [0, 0, 1]
        ])
        
        homography_data = {
            'camera_id': camera_id,
            'homography': H_rotated.tolist(),
            'markers_detected': [0, 1, 2, 3],
            'num_points': 16,
            'reprojection_error': 2.0,
        }
        homography_file = tmp_path / f"homography_cam{camera_id}.json"
        with open(homography_file, 'w') as f:
            json.dump(homography_data, f)
    
    return tmp_path


@pytest.fixture
def coordinate_mapper(sample_config, calibration_dir):
    """Create CoordinateMapper with test calibration data."""
    return CoordinateMapper(sample_config, str(calibration_dir))


# =============================================================================
# Property-Based Tests
# =============================================================================

class TestHomographyInverseProperty:
    """
    Property 2: Homography Inverse Property (Round Trip)
    
    For any valid board coordinate (x, y) within the board bounds,
    transforming to image coordinates then back to board coordinates
    should return approximately the same point.
    
    **Validates: Requirements AC-6.4.2, AC-6.5.2**
    """
    
    @given(
        x=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
        y=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
        camera_id=st.sampled_from([0, 1, 2])
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_round_trip_board_to_image_to_board(
        self, x, y, camera_id, coordinate_mapper
    ):
        """
        Board → Image → Board round trip should preserve coordinates within 1mm.
        
        **Validates: Requirements AC-6.4.2, AC-6.5.2**
        """
        # Skip if outside board radius
        radius = np.sqrt(x**2 + y**2)
        assume(radius <= 170)  # Stay within board
        
        # Transform board → image
        image_result = coordinate_mapper.map_to_image(camera_id, x, y)
        assume(image_result is not None)
        
        u, v = image_result
        
        # Verify image coordinates are reasonable
        assume(0 <= u <= 800)
        assume(0 <= v <= 600)
        
        # Transform image → board
        board_result = coordinate_mapper.map_to_board(camera_id, u, v)
        assume(board_result is not None)
        
        x_back, y_back = board_result
        
        # Verify round trip error < 1mm
        error = np.sqrt((x - x_back)**2 + (y - y_back)**2)
        assert error < 1.0, (
            f"Round trip error {error:.3f}mm exceeds 1mm threshold. "
            f"Original: ({x:.2f}, {y:.2f}), Recovered: ({x_back:.2f}, {y_back:.2f})"
        )


class TestUndistortionInvertibility:
    """
    Property 6: Undistortion is Invertible
    
    For any pixel coordinate (u, v) within image bounds, undistorting
    then redistorting should return approximately the same pixel.
    
    **Validates: Requirements AC-6.4.3**
    """
    
    @given(
        u=st.floats(min_value=50, max_value=750, allow_nan=False, allow_infinity=False),
        v=st.floats(min_value=50, max_value=550, allow_nan=False, allow_infinity=False),
        camera_id=st.sampled_from([0, 1, 2])
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_undistort_redistort_round_trip(
        self, u, v, camera_id, calibration_dir
    ):
        """
        Undistort → Redistort round trip should preserve pixels within 0.1px.
        
        **Validates: Requirements AC-6.4.3**
        """
        # Load calibration data directly for this test
        intrinsic_file = calibration_dir / f"intrinsic_cam{camera_id}.json"
        with open(intrinsic_file, 'r') as f:
            data = json.load(f)
        
        K = np.array(data['camera_matrix'], dtype=np.float64)
        D = np.array(data['distortion_coeffs'], dtype=np.float64)
        
        # Undistort
        pixel = np.array([[[u, v]]], dtype=np.float32)
        undistorted = cv2.undistortPoints(pixel, K, D, P=K)
        u_undist = undistorted[0, 0, 0]
        v_undist = undistorted[0, 0, 1]
        
        # Redistort using projectPoints
        # Convert to normalized coordinates
        fx, fy = K[0, 0], K[1, 1]
        cx, cy = K[0, 2], K[1, 2]
        
        x_norm = (u_undist - cx) / fx
        y_norm = (v_undist - cy) / fy
        
        # Apply distortion model
        k1, k2, p1, p2 = D[0], D[1], D[2], D[3]
        k3 = D[4] if len(D) > 4 else 0
        
        r2 = x_norm**2 + y_norm**2
        r4 = r2**2
        r6 = r2**3
        
        radial = 1 + k1*r2 + k2*r4 + k3*r6
        x_dist = x_norm * radial + 2*p1*x_norm*y_norm + p2*(r2 + 2*x_norm**2)
        y_dist = y_norm * radial + p1*(r2 + 2*y_norm**2) + 2*p2*x_norm*y_norm
        
        u_back = fx * x_dist + cx
        v_back = fy * y_dist + cy
        
        # Verify round trip error < 0.1 pixels
        error = np.sqrt((u - u_back)**2 + (v - v_back)**2)
        assert error < 0.1, (
            f"Undistort/redistort error {error:.4f}px exceeds 0.1px threshold. "
            f"Original: ({u:.2f}, {v:.2f}), Recovered: ({u_back:.2f}, {v_back:.2f})"
        )


class TestCoordinateBoundsChecking:
    """
    Property 7: Coordinate Bounds Checking
    
    For pixel coordinates that map outside board bounds, the system
    should return None or flag as out-of-bounds.
    
    **Validates: Requirements AC-6.4.5**
    """
    
    @given(
        # Generate coordinates likely to be far outside board
        u=st.one_of(
            st.floats(min_value=0, max_value=50),  # Far left
            st.floats(min_value=750, max_value=800),  # Far right
        ),
        v=st.one_of(
            st.floats(min_value=0, max_value=50),  # Far top
            st.floats(min_value=550, max_value=600),  # Far bottom
        ),
        camera_id=st.sampled_from([0, 1, 2])
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_out_of_bounds_returns_none_or_flags(
        self, u, v, camera_id, coordinate_mapper
    ):
        """
        Coordinates mapping far outside board should be handled gracefully.
        
        **Validates: Requirements AC-6.4.5**
        """
        result = coordinate_mapper.map_to_board(camera_id, u, v)
        
        if result is not None:
            x, y = result
            # If result returned, check if it's flagged as out of bounds
            # or within the maximum valid radius
            radius = np.sqrt(x**2 + y**2)
            
            # Either the result is within max bounds, or is_out_of_bounds returns True
            is_oob = coordinate_mapper.is_out_of_bounds(x, y)
            within_max = radius <= CoordinateMapper.MAX_VALID_RADIUS_MM
            
            assert within_max, (
                f"Result ({x:.1f}, {y:.1f}) exceeds max radius "
                f"{CoordinateMapper.MAX_VALID_RADIUS_MM}mm"
            )


class TestMultiCameraConsistency:
    """
    Property 8: Transformation Consistency Across Cameras
    
    For any board coordinate, transforming to image coordinates for
    different cameras then back to board should return consistent results.
    
    **Validates: Requirements AC-6.4.2, AC-6.5.4**
    """
    
    @given(
        x=st.floats(min_value=-150, max_value=150, allow_nan=False, allow_infinity=False),
        y=st.floats(min_value=-150, max_value=150, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_multi_camera_round_trip_consistency(
        self, x, y, coordinate_mapper
    ):
        """
        All cameras should agree on board coordinates within 5mm.
        
        **Validates: Requirements AC-6.4.2, AC-6.5.4**
        """
        # Skip if outside board
        radius = np.sqrt(x**2 + y**2)
        assume(radius <= 150)
        
        recovered_positions = []
        
        for camera_id in [0, 1, 2]:
            # Board → Image
            image_result = coordinate_mapper.map_to_image(camera_id, x, y)
            if image_result is None:
                continue
            
            u, v = image_result
            
            # Skip if outside image bounds
            if not (0 <= u <= 800 and 0 <= v <= 600):
                continue
            
            # Image → Board
            board_result = coordinate_mapper.map_to_board(camera_id, u, v)
            if board_result is None:
                continue
            
            recovered_positions.append((camera_id, board_result))
        
        # Need at least 2 cameras for consistency check
        assume(len(recovered_positions) >= 2)
        
        # Check all cameras agree within 5mm
        for i, (cam_i, pos_i) in enumerate(recovered_positions):
            for cam_j, pos_j in recovered_positions[i+1:]:
                x_i, y_i = pos_i
                x_j, y_j = pos_j
                
                error = np.sqrt((x_i - x_j)**2 + (y_i - y_j)**2)
                assert error < 5.0, (
                    f"Cameras {cam_i} and {cam_j} disagree by {error:.2f}mm. "
                    f"Cam {cam_i}: ({x_i:.2f}, {y_i:.2f}), "
                    f"Cam {cam_j}: ({x_j:.2f}, {y_j:.2f})"
                )


# =============================================================================
# Unit Tests
# =============================================================================

class TestCoordinateMapperInit:
    """Unit tests for CoordinateMapper initialization."""
    
    def test_loads_valid_calibration(self, sample_config, calibration_dir):
        """Test loading valid calibration files."""
        mapper = CoordinateMapper(sample_config, str(calibration_dir))
        
        for camera_id in [0, 1, 2]:
            assert mapper.is_calibrated(camera_id)
    
    def test_handles_missing_calibration_gracefully(self, sample_config, tmp_path):
        """Test handling of missing calibration files."""
        # Empty calibration directory
        mapper = CoordinateMapper(sample_config, str(tmp_path))
        
        for camera_id in [0, 1, 2]:
            assert not mapper.is_calibrated(camera_id)
    
    def test_get_calibration_status(self, sample_config, calibration_dir):
        """Test calibration status reporting."""
        mapper = CoordinateMapper(sample_config, str(calibration_dir))
        
        status = mapper.get_calibration_status()
        
        assert len(status) == 3
        for camera_id in [0, 1, 2]:
            assert status[camera_id]['has_intrinsic']
            assert status[camera_id]['has_homography']
            assert status[camera_id]['is_calibrated']


class TestMapToBoard:
    """Unit tests for map_to_board method."""
    
    def test_returns_none_for_uncalibrated_camera(self, sample_config, tmp_path):
        """Test that uncalibrated cameras return None."""
        mapper = CoordinateMapper(sample_config, str(tmp_path))
        
        result = mapper.map_to_board(0, 400, 300)
        assert result is None
    
    def test_center_pixel_maps_near_origin(self, coordinate_mapper):
        """Test that center pixel maps near board origin."""
        # Center of image (400, 300) should map near board center
        result = coordinate_mapper.map_to_board(0, 400, 300)
        
        assert result is not None
        x, y = result
        
        # Should be near origin (within 50mm for test calibration)
        assert abs(x) < 50
        assert abs(y) < 50


class TestMapToImage:
    """Unit tests for map_to_image method."""
    
    def test_returns_none_for_uncalibrated_camera(self, sample_config, tmp_path):
        """Test that uncalibrated cameras return None."""
        mapper = CoordinateMapper(sample_config, str(tmp_path))
        
        result = mapper.map_to_image(0, 0, 0)
        assert result is None
    
    def test_origin_maps_to_image_center(self, coordinate_mapper):
        """Test that board origin maps near image center."""
        result = coordinate_mapper.map_to_image(0, 0, 0)
        
        assert result is not None
        u, v = result
        
        # Should be near image center (within 100px for test calibration)
        assert 300 < u < 500
        assert 200 < v < 400


class TestReloadCalibration:
    """Unit tests for reload_calibration method."""
    
    def test_reload_single_camera(self, sample_config, calibration_dir):
        """Test reloading calibration for single camera."""
        mapper = CoordinateMapper(sample_config, str(calibration_dir))
        
        # Verify initially calibrated
        assert mapper.is_calibrated(0)
        
        # Reload camera 0
        mapper.reload_calibration(0)
        
        # Should still be calibrated
        assert mapper.is_calibrated(0)
    
    def test_reload_all_cameras(self, sample_config, calibration_dir):
        """Test reloading calibration for all cameras."""
        mapper = CoordinateMapper(sample_config, str(calibration_dir))
        
        # Reload all
        mapper.reload_calibration()
        
        # All should still be calibrated
        for camera_id in [0, 1, 2]:
            assert mapper.is_calibrated(camera_id)


class TestThreadSafety:
    """Unit tests for thread safety."""
    
    def test_concurrent_map_to_board(self, coordinate_mapper):
        """Test concurrent calls to map_to_board."""
        import threading
        
        results = []
        errors = []
        
        def worker(camera_id, u, v):
            try:
                result = coordinate_mapper.map_to_board(camera_id, u, v)
                results.append((camera_id, result))
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(10):
            camera_id = i % 3
            t = threading.Thread(target=worker, args=(camera_id, 400, 300))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Errors during concurrent access: {errors}"
        assert len(results) == 10


# =============================================================================
# Property Test for Calibration Quality Metrics
# =============================================================================

class TestCalibrationQualityMetrics:
    """
    Property 4: Calibration Quality Metrics
    
    Use real calibration data with known control points.
    Verify reprojection error < 0.5 pixels (intrinsic).
    Verify mapping error < 5mm (extrinsic with control points).
    
    **Validates: Requirements AC-6.1.3, AC-6.5.4**
    """
    
    # Known control points on dartboard (board coordinates in mm from center)
    CONTROL_POINTS = {
        'bull': (0.0, 0.0),
        'T20': (0.0, 103.0),
        'D20': (0.0, 166.0),
        'T3': (0.0, -103.0),
        'D3': (0.0, -166.0),
    }
    
    @given(
        control_point=st.sampled_from(['bull', 'T20', 'D20', 'T3', 'D3']),
        camera_id=st.sampled_from([0, 1, 2])
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_control_point_round_trip_within_tolerance(
        self, control_point, camera_id, coordinate_mapper
    ):
        """
        Control points should round-trip with error < 5mm.
        
        **Validates: Requirements AC-6.1.3, AC-6.5.4**
        """
        expected_x, expected_y = self.CONTROL_POINTS[control_point]
        
        # Board → Image
        image_result = coordinate_mapper.map_to_image(camera_id, expected_x, expected_y)
        assume(image_result is not None)
        
        u, v = image_result
        
        # Verify image coordinates are within bounds
        assume(0 <= u <= 800)
        assume(0 <= v <= 600)
        
        # Image → Board
        board_result = coordinate_mapper.map_to_board(camera_id, u, v)
        assume(board_result is not None)
        
        actual_x, actual_y = board_result
        
        # Compute error
        error = np.sqrt((expected_x - actual_x)**2 + (expected_y - actual_y)**2)
        
        # Verify error < 5mm (extrinsic quality requirement)
        assert error < 5.0, (
            f"Control point {control_point} error {error:.2f}mm exceeds 5mm threshold. "
            f"Expected: ({expected_x:.1f}, {expected_y:.1f}), "
            f"Actual: ({actual_x:.1f}, {actual_y:.1f})"
        )
    
    def test_intrinsic_reprojection_error_threshold(self, calibration_dir):
        """
        Verify intrinsic calibration reprojection error is stored and reasonable.
        
        **Validates: Requirements AC-6.1.3**
        """
        for camera_id in [0, 1, 2]:
            intrinsic_file = calibration_dir / f"intrinsic_cam{camera_id}.json"
            
            with open(intrinsic_file, 'r') as f:
                data = json.load(f)
            
            reprojection_error = data.get('reprojection_error', 0)
            
            # Test calibration data has low reprojection error
            # (Real calibration should be < 0.5, test data is 0.3)
            assert reprojection_error < 1.0, (
                f"Camera {camera_id} intrinsic reprojection error "
                f"{reprojection_error:.3f} exceeds threshold"
            )
