"""
Unit tests for IntrinsicCalibrator class.

Feature: step-6-coordinate-mapping
Validates: Requirements AC-6.1.2, AC-6.1.3, AC-6.1.4

Tests intrinsic calibration functionality including:
- Chessboard detection with synthetic images
- Calibration computation with known geometry
- JSON serialization/deserialization
- Error handling for insufficient images
"""

import json
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.calibration.intrinsic_calibrator import IntrinsicCalibrator


# Test configuration matching the design spec
TEST_CONFIG = {
    'calibration': {
        'chessboard': {
            'inner_corners': [9, 6],
            'square_size_mm': 25.0
        }
    },
    'camera_settings': {
        'width': 800,
        'height': 600
    }
}


def generate_chessboard_image(
    chessboard_size: tuple[int, int] = (9, 6),
    square_size_px: int = 30,
    image_width: int = 800,
    image_height: int = 600,
    x_offset: float = 100.0,
    y_offset: float = 100.0,
    rotation_deg: float = 0.0,
    perspective_strength: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate a synthetic chessboard image for testing.
    
    Args:
        chessboard_size: Inner corners (width, height)
        square_size_px: Size of each square in pixels
        image_width: Output image width
        image_height: Output image height
        x_offset: X position of top-left corner
        y_offset: Y position of top-left corner
        rotation_deg: Rotation angle in degrees
        perspective_strength: Amount of perspective distortion (0-1)
    
    Returns:
        Tuple of (image, ground_truth_corners)
        ground_truth_corners: (N×1×2) array of inner corner positions
    """
    cols, rows = chessboard_size
    board_width = (cols + 1) * square_size_px
    board_height = (rows + 1) * square_size_px
    
    # Create chessboard pattern
    chessboard = np.zeros((board_height, board_width), dtype=np.uint8)
    
    for i in range(rows + 1):
        for j in range(cols + 1):
            if (i + j) % 2 == 0:
                x1 = j * square_size_px
                y1 = i * square_size_px
                x2 = x1 + square_size_px
                y2 = y1 + square_size_px
                chessboard[y1:y2, x1:x2] = 255
    
    # Calculate inner corner positions (ground truth)
    corners = []
    for i in range(rows):
        for j in range(cols):
            x = (j + 1) * square_size_px
            y = (i + 1) * square_size_px
            corners.append([x, y])
    
    corners = np.array(corners, dtype=np.float32)
    
    # Source points (corners of chessboard)
    src_pts = np.array([
        [0, 0],
        [board_width, 0],
        [board_width, board_height],
        [0, board_height]
    ], dtype=np.float32)
    
    # Apply rotation
    angle_rad = np.radians(rotation_deg)
    cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)
    
    # Center of chessboard
    cx, cy = board_width / 2, board_height / 2
    
    # Rotate source points around center
    rotated_pts = []
    for pt in src_pts:
        px, py = pt[0] - cx, pt[1] - cy
        rx = px * cos_a - py * sin_a + cx
        ry = px * sin_a + py * cos_a + cy
        rotated_pts.append([rx, ry])
    
    # Destination points with offset and optional perspective
    dst_pts = np.array([
        [x_offset + rotated_pts[0][0], y_offset + rotated_pts[0][1]],
        [x_offset + rotated_pts[1][0], y_offset + rotated_pts[1][1]],
        [x_offset + rotated_pts[2][0], y_offset + rotated_pts[2][1]],
        [x_offset + rotated_pts[3][0], y_offset + rotated_pts[3][1]]
    ], dtype=np.float32)
    
    # Apply perspective distortion
    if perspective_strength > 0:
        # Shrink top edge to simulate viewing from below
        shrink = perspective_strength * 50
        dst_pts[0][0] += shrink
        dst_pts[1][0] -= shrink
    
    # Compute perspective transform
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    
    # Create output image
    image = np.full((image_height, image_width), 128, dtype=np.uint8)
    
    # Warp chessboard onto image
    warped = cv2.warpPerspective(
        chessboard, M, (image_width, image_height),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=128
    )
    
    # Blend onto background
    mask = (warped != 128)
    image[mask] = warped[mask]
    
    # Transform ground truth corners
    corners_homogeneous = np.hstack([corners, np.ones((len(corners), 1))])
    transformed = (M @ corners_homogeneous.T).T
    transformed_corners = transformed[:, :2] / transformed[:, 2:3]
    
    # Reshape to match OpenCV format (N×1×2)
    ground_truth = transformed_corners.reshape(-1, 1, 2).astype(np.float32)
    
    return image, ground_truth


def generate_calibration_image_set(
    num_images: int = 15,
    chessboard_size: tuple[int, int] = (9, 6),
    square_size_px: int = 25
) -> list[np.ndarray]:
    """
    Generate a set of chessboard images at various positions and angles.
    
    Args:
        num_images: Number of images to generate
        chessboard_size: Inner corners (width, height)
        square_size_px: Size of each square in pixels
    
    Returns:
        List of grayscale images with chessboard patterns
    """
    images = []
    
    # Generate images at different positions and rotations
    positions = [
        (50, 50, 0),
        (150, 100, 5),
        (100, 150, -5),
        (200, 50, 10),
        (50, 200, -10),
        (100, 100, 15),
        (150, 150, -15),
        (75, 75, 3),
        (125, 125, -3),
        (175, 75, 8),
        (75, 175, -8),
        (100, 50, 12),
        (50, 100, -12),
        (150, 50, 7),
        (50, 150, -7),
        (125, 75, 4),
        (75, 125, -4),
        (175, 125, 6),
        (125, 175, -6),
        (100, 100, 0),
    ]
    
    for i in range(min(num_images, len(positions))):
        x_off, y_off, rot = positions[i]
        image, _ = generate_chessboard_image(
            chessboard_size=chessboard_size,
            square_size_px=square_size_px,
            x_offset=float(x_off),
            y_offset=float(y_off),
            rotation_deg=float(rot)
        )
        images.append(image)
    
    return images


class TestChessboardDetection:
    """
    Unit tests for chessboard detection functionality.
    
    **Validates: Requirements AC-6.1.2**
    """
    
    def test_find_chessboard_corners_valid_image(self):
        """Chessboard corners should be detected in a valid synthetic image."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Generate a clear chessboard image
        image, expected_corners = generate_chessboard_image(
            chessboard_size=(9, 6),
            square_size_px=30,
            x_offset=100.0,
            y_offset=100.0,
            rotation_deg=0.0
        )
        
        found, corners = calibrator.find_chessboard_corners(image)
        
        assert found is True, "Chessboard should be detected"
        assert corners is not None, "Corners should not be None"
        assert corners.shape == (54, 1, 2), f"Expected shape (54, 1, 2), got {corners.shape}"
    
    def test_find_chessboard_corners_rotated_image(self):
        """Chessboard corners should be detected in a rotated image."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        image, _ = generate_chessboard_image(
            chessboard_size=(9, 6),
            square_size_px=30,
            x_offset=150.0,
            y_offset=100.0,
            rotation_deg=15.0
        )
        
        found, corners = calibrator.find_chessboard_corners(image)
        
        assert found is True, "Rotated chessboard should be detected"
        assert corners is not None
    
    def test_find_chessboard_corners_bgr_image(self):
        """Chessboard detection should work with BGR images."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Generate grayscale and convert to BGR
        gray_image, _ = generate_chessboard_image()
        bgr_image = cv2.cvtColor(gray_image, cv2.COLOR_GRAY2BGR)
        
        found, corners = calibrator.find_chessboard_corners(bgr_image)
        
        assert found is True, "BGR image should be handled correctly"
    
    def test_find_chessboard_corners_no_pattern(self):
        """Detection should fail gracefully when no chessboard is present."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Create blank image
        blank_image = np.full((600, 800), 128, dtype=np.uint8)
        
        found, corners = calibrator.find_chessboard_corners(blank_image)
        
        assert found is False, "Should not detect chessboard in blank image"
        assert corners is None, "Corners should be None when not found"
    
    def test_find_chessboard_corners_partial_pattern(self):
        """Detection should fail when chessboard is partially visible."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Generate chessboard that extends beyond image bounds
        image, _ = generate_chessboard_image(
            chessboard_size=(9, 6),
            square_size_px=50,  # Large squares
            x_offset=-100.0,   # Partially off-screen
            y_offset=100.0
        )
        
        found, corners = calibrator.find_chessboard_corners(image)
        
        # Should fail because not all corners are visible
        assert found is False, "Partial chessboard should not be detected"


class TestCalibrationComputation:
    """
    Unit tests for calibration computation.
    
    **Validates: Requirements AC-6.1.2, AC-6.1.3**
    """
    
    def test_calibrate_with_valid_images(self):
        """Calibration should succeed with sufficient valid images."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Generate calibration images
        images = generate_calibration_image_set(num_images=15)
        
        camera_matrix, distortion_coeffs, reprojection_error = calibrator.calibrate(images)
        
        # Verify camera matrix shape and properties
        assert camera_matrix.shape == (3, 3), "Camera matrix should be 3x3"
        assert camera_matrix[2, 2] == 1.0, "Camera matrix [2,2] should be 1"
        assert camera_matrix[0, 0] > 0, "fx should be positive"
        assert camera_matrix[1, 1] > 0, "fy should be positive"
        
        # Verify distortion coefficients
        assert len(distortion_coeffs) >= 5, "Should have at least 5 distortion coefficients"
        
        # Verify reprojection error is reasonable
        assert reprojection_error >= 0, "Reprojection error should be non-negative"
        assert reprojection_error < 5.0, "Reprojection error should be reasonable"
    
    def test_calibrate_reprojection_error_threshold(self):
        """Calibration with good images should achieve low reprojection error."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Generate many images for better calibration
        images = generate_calibration_image_set(num_images=20)
        
        _, _, reprojection_error = calibrator.calibrate(images)
        
        # For synthetic images, error should be very low
        # Real-world threshold is 0.5 pixels per AC-6.1.3
        assert reprojection_error < 2.0, (
            f"Reprojection error {reprojection_error:.4f} should be low for synthetic images"
        )
    
    def test_calibrate_camera_matrix_principal_point(self):
        """Principal point should be near image center."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        images = generate_calibration_image_set(num_images=15)
        camera_matrix, _, _ = calibrator.calibrate(images)
        
        cx = camera_matrix[0, 2]
        cy = camera_matrix[1, 2]
        
        # Principal point should be within reasonable range of image center
        image_center_x = 400  # 800 / 2
        image_center_y = 300  # 600 / 2
        
        assert abs(cx - image_center_x) < 200, f"cx={cx} should be near image center"
        assert abs(cy - image_center_y) < 200, f"cy={cy} should be near image center"
    
    def test_calibrate_insufficient_images_raises_error(self):
        """Calibration should raise ValueError with too few images."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Only 5 images (minimum is 10)
        images = generate_calibration_image_set(num_images=5)
        
        with pytest.raises(ValueError) as exc_info:
            calibrator.calibrate(images)
        
        assert "Insufficient images" in str(exc_info.value)
    
    def test_calibrate_empty_image_list_raises_error(self):
        """Calibration should raise ValueError with empty image list."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        with pytest.raises(ValueError) as exc_info:
            calibrator.calibrate([])
        
        assert "Insufficient images" in str(exc_info.value)
    
    def test_calibrate_images_without_chessboard_raises_error(self):
        """Calibration should raise ValueError when no chessboards detected."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Create 15 blank images (no chessboard)
        blank_images = [np.full((600, 800), 128, dtype=np.uint8) for _ in range(15)]
        
        with pytest.raises(ValueError) as exc_info:
            calibrator.calibrate(blank_images)
        
        assert "Too few valid images" in str(exc_info.value)


class TestJSONSerialization:
    """
    Unit tests for calibration data serialization/deserialization.
    
    **Validates: Requirements AC-6.1.4**
    """
    
    def test_save_calibration_creates_file(self):
        """save_calibration should create a JSON file with correct format."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Create test calibration data
        camera_matrix = np.array([
            [800.0, 0.0, 400.0],
            [0.0, 800.0, 300.0],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)
        distortion_coeffs = np.array([0.1, -0.2, 0.001, 0.002, 0.05], dtype=np.float64)
        reprojection_error = 0.35
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = calibrator.save_calibration(
                camera_id=0,
                camera_matrix=camera_matrix,
                distortion_coeffs=distortion_coeffs,
                reprojection_error=reprojection_error,
                output_dir=tmpdir
            )
            
            # Verify file exists
            assert output_file.exists(), "Calibration file should be created"
            assert output_file.name == "intrinsic_cam0.json"
            
            # Verify JSON content
            with open(output_file, 'r') as f:
                data = json.load(f)
            
            assert data['camera_id'] == 0
            assert 'camera_matrix' in data
            assert 'distortion_coeffs' in data
            assert data['reprojection_error'] == reprojection_error
            assert 'calibration_date' in data
            assert data['image_size'] == [800, 600]
            assert data['chessboard_size'] == [9, 6]
            assert data['square_size_mm'] == 25.0
    
    def test_save_calibration_different_camera_ids(self):
        """save_calibration should create files for different camera IDs."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        camera_matrix = np.eye(3, dtype=np.float64)
        distortion_coeffs = np.zeros(5, dtype=np.float64)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            for camera_id in [0, 1, 2]:
                output_file = calibrator.save_calibration(
                    camera_id=camera_id,
                    camera_matrix=camera_matrix,
                    distortion_coeffs=distortion_coeffs,
                    reprojection_error=0.3,
                    output_dir=tmpdir
                )
                
                assert output_file.name == f"intrinsic_cam{camera_id}.json"
                assert output_file.exists()
    
    def test_load_calibration_valid_file(self):
        """load_calibration should correctly load saved calibration data."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Create and save calibration data
        original_matrix = np.array([
            [850.5, 0.0, 412.3],
            [0.0, 851.2, 298.7],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)
        original_distortion = np.array([0.12, -0.25, 0.0015, 0.0022, 0.08], dtype=np.float64)
        original_error = 0.42
        
        with tempfile.TemporaryDirectory() as tmpdir:
            calibrator.save_calibration(
                camera_id=1,
                camera_matrix=original_matrix,
                distortion_coeffs=original_distortion,
                reprojection_error=original_error,
                output_dir=tmpdir
            )
            
            # Load calibration
            result = IntrinsicCalibrator.load_calibration(camera_id=1, calibration_dir=tmpdir)
            
            assert result is not None, "Should load calibration successfully"
            
            loaded_matrix, loaded_distortion, loaded_error = result
            
            # Verify data matches
            np.testing.assert_array_almost_equal(
                loaded_matrix, original_matrix, decimal=6,
                err_msg="Camera matrix should match"
            )
            np.testing.assert_array_almost_equal(
                loaded_distortion, original_distortion, decimal=6,
                err_msg="Distortion coefficients should match"
            )
            assert loaded_error == original_error, "Reprojection error should match"
    
    def test_load_calibration_missing_file(self):
        """load_calibration should return None for missing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = IntrinsicCalibrator.load_calibration(
                camera_id=99,  # Non-existent camera
                calibration_dir=tmpdir
            )
            
            assert result is None, "Should return None for missing file"
    
    def test_load_calibration_nonexistent_directory(self):
        """load_calibration should return None for non-existent directory."""
        result = IntrinsicCalibrator.load_calibration(
            camera_id=0,
            calibration_dir="/nonexistent/path/to/calibration"
        )
        
        assert result is None, "Should return None for non-existent directory"
    
    def test_serialization_round_trip_preserves_precision(self):
        """Saving and loading should preserve numerical precision."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Use values with many decimal places
        original_matrix = np.array([
            [823.456789012345, 0.0, 401.234567890123],
            [0.0, 824.567890123456, 299.876543210987],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)
        original_distortion = np.array(
            [0.123456789, -0.234567890, 0.001234567, 0.002345678, 0.056789012],
            dtype=np.float64
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            calibrator.save_calibration(
                camera_id=0,
                camera_matrix=original_matrix,
                distortion_coeffs=original_distortion,
                reprojection_error=0.4567,
                output_dir=tmpdir
            )
            
            loaded_matrix, loaded_distortion, _ = IntrinsicCalibrator.load_calibration(
                camera_id=0, calibration_dir=tmpdir
            )
            
            # JSON preserves ~15 significant digits for float64
            np.testing.assert_array_almost_equal(
                loaded_matrix, original_matrix, decimal=10,
                err_msg="Matrix precision should be preserved"
            )
            np.testing.assert_array_almost_equal(
                loaded_distortion, original_distortion, decimal=10,
                err_msg="Distortion precision should be preserved"
            )


class TestErrorHandling:
    """
    Unit tests for error handling in IntrinsicCalibrator.
    
    **Validates: Requirements AC-6.1.2, AC-6.1.3, AC-6.1.4**
    """
    
    def test_init_with_custom_chessboard_size(self):
        """Calibrator should accept custom chessboard size."""
        calibrator = IntrinsicCalibrator(
            TEST_CONFIG,
            chessboard_size=(7, 5),
            square_size_mm=30.0
        )
        
        assert calibrator.chessboard_size == (7, 5)
        assert calibrator.square_size_mm == 30.0
    
    def test_init_with_config_defaults(self):
        """Calibrator should use config values when not overridden."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        assert calibrator.chessboard_size == (9, 6)
        assert calibrator.square_size_mm == 25.0
    
    def test_init_with_empty_config(self):
        """Calibrator should use defaults with empty config."""
        calibrator = IntrinsicCalibrator({})
        
        # Should use hardcoded defaults
        assert calibrator.chessboard_size == (9, 6)
        assert calibrator.square_size_mm == 25.0
        assert calibrator.image_width == 800
        assert calibrator.image_height == 600
    
    def test_calibrate_mixed_valid_invalid_images(self):
        """Calibration should succeed if enough valid images exist."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Generate 12 valid images
        valid_images = generate_calibration_image_set(num_images=12)
        
        # Add 3 invalid (blank) images
        invalid_images = [np.full((600, 800), 128, dtype=np.uint8) for _ in range(3)]
        
        # Mix them together
        all_images = valid_images + invalid_images
        
        # Should still succeed (12 valid >= 10 minimum)
        camera_matrix, distortion_coeffs, error = calibrator.calibrate(all_images)
        
        assert camera_matrix is not None
        assert distortion_coeffs is not None
    
    def test_calibrate_too_few_valid_images_raises_error(self):
        """Calibration should fail if too few valid images after filtering."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # Generate only 5 valid images
        valid_images = generate_calibration_image_set(num_images=5)
        
        # Add 10 invalid images to meet minimum count
        invalid_images = [np.full((600, 800), 128, dtype=np.uint8) for _ in range(10)]
        
        all_images = valid_images + invalid_images
        
        # Should fail because only 5 valid images
        with pytest.raises(ValueError) as exc_info:
            calibrator.calibrate(all_images)
        
        assert "Too few valid images" in str(exc_info.value)
    
    def test_save_calibration_creates_directory(self):
        """save_calibration should create output directory if needed."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        camera_matrix = np.eye(3, dtype=np.float64)
        distortion_coeffs = np.zeros(5, dtype=np.float64)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = Path(tmpdir) / "nested" / "calibration" / "dir"
            
            output_file = calibrator.save_calibration(
                camera_id=0,
                camera_matrix=camera_matrix,
                distortion_coeffs=distortion_coeffs,
                reprojection_error=0.3,
                output_dir=str(nested_dir)
            )
            
            assert nested_dir.exists(), "Nested directory should be created"
            assert output_file.exists(), "Calibration file should be created"


class TestObjectPointGeneration:
    """
    Unit tests for 3D object point generation.
    
    **Validates: Requirements AC-6.1.2**
    """
    
    def test_object_points_shape(self):
        """Object points should have correct shape for chessboard."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # 9x6 inner corners = 54 points
        expected_points = 9 * 6
        
        assert calibrator.objp.shape == (expected_points, 3)
    
    def test_object_points_z_coordinate(self):
        """All object points should have z=0 (planar chessboard)."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        z_coords = calibrator.objp[:, 2]
        
        assert np.all(z_coords == 0), "All z coordinates should be 0"
    
    def test_object_points_spacing(self):
        """Object points should be spaced by square_size_mm."""
        calibrator = IntrinsicCalibrator(TEST_CONFIG)
        
        # First row of points
        first_row = calibrator.objp[:9]  # First 9 points (first row)
        
        # Check x spacing
        x_diffs = np.diff(first_row[:, 0])
        expected_spacing = 25.0  # square_size_mm
        
        np.testing.assert_array_almost_equal(
            x_diffs, np.full(8, expected_spacing),
            err_msg="X spacing should equal square_size_mm"
        )
    
    def test_object_points_custom_square_size(self):
        """Object points should use custom square size."""
        calibrator = IntrinsicCalibrator(
            TEST_CONFIG,
            square_size_mm=30.0
        )
        
        # Check spacing
        first_row = calibrator.objp[:9]
        x_diffs = np.diff(first_row[:, 0])
        
        np.testing.assert_array_almost_equal(
            x_diffs, np.full(8, 30.0),
            err_msg="X spacing should equal custom square_size_mm"
        )


# =============================================================================
# Property-Based Tests
# =============================================================================

from hypothesis import given, strategies as st, settings


class TestCalibrationSerializationRoundTrip:
    """
    Property-based tests for calibration serialization round trip.

    Feature: step-6-coordinate-mapping, Property 5: Calibration Serialization Round Trip

    For any valid calibration data (camera matrix, distortion coefficients),
    saving to JSON then loading should produce numerically equivalent matrices
    (within floating-point tolerance of 1e-6).

    **Validates: Requirements AC-6.1.4**
    """

    @given(
        fx=st.floats(min_value=500.0, max_value=1500.0, allow_nan=False, allow_infinity=False),
        fy=st.floats(min_value=500.0, max_value=1500.0, allow_nan=False, allow_infinity=False),
        cx=st.floats(min_value=200.0, max_value=600.0, allow_nan=False, allow_infinity=False),
        cy=st.floats(min_value=150.0, max_value=450.0, allow_nan=False, allow_infinity=False),
        k1=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
        k2=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
        p1=st.floats(min_value=-0.01, max_value=0.01, allow_nan=False, allow_infinity=False),
        p2=st.floats(min_value=-0.01, max_value=0.01, allow_nan=False, allow_infinity=False),
        k3=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
        reprojection_error=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
        camera_id=st.integers(min_value=0, max_value=2)
    )
    @settings(max_examples=100)
    def test_camera_matrix_round_trip(self, fx, fy, cx, cy, k1, k2, p1, p2, k3,
                                       reprojection_error, camera_id):
        """
        Feature: step-6-coordinate-mapping, Property 5: Calibration Serialization Round Trip

        For any valid camera matrix and distortion coefficients, saving to JSON
        then loading should produce numerically equivalent matrices within 1e-6 tolerance.

        **Validates: Requirements AC-6.1.4**
        """
        calibrator = IntrinsicCalibrator(TEST_CONFIG)

        # Create camera matrix with generated values
        original_matrix = np.array([
            [fx, 0.0, cx],
            [0.0, fy, cy],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)

        # Create distortion coefficients with generated values
        original_distortion = np.array([k1, k2, p1, p2, k3], dtype=np.float64)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Save calibration
            calibrator.save_calibration(
                camera_id=camera_id,
                camera_matrix=original_matrix,
                distortion_coeffs=original_distortion,
                reprojection_error=reprojection_error,
                output_dir=tmpdir
            )

            # Load calibration
            result = IntrinsicCalibrator.load_calibration(
                camera_id=camera_id,
                calibration_dir=tmpdir
            )

            assert result is not None, "Should load calibration successfully"

            loaded_matrix, loaded_distortion, loaded_error = result

            # Verify camera matrix round trip within 1e-6 tolerance
            np.testing.assert_allclose(
                loaded_matrix, original_matrix, rtol=1e-6, atol=1e-6,
                err_msg="Camera matrix should be numerically equivalent after round trip"
            )

            # Verify distortion coefficients round trip within 1e-6 tolerance
            np.testing.assert_allclose(
                loaded_distortion, original_distortion, rtol=1e-6, atol=1e-6,
                err_msg="Distortion coefficients should be numerically equivalent after round trip"
            )

            # Verify reprojection error round trip
            assert abs(loaded_error - reprojection_error) < 1e-6, (
                f"Reprojection error should be preserved: "
                f"original={reprojection_error}, loaded={loaded_error}"
            )

    @given(
        # Generate random 3x3 matrix elements for homography-like matrices
        h11=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        h12=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        h13=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        h21=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        h22=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        h23=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        h31=st.floats(min_value=-0.01, max_value=0.01, allow_nan=False, allow_infinity=False),
        h32=st.floats(min_value=-0.01, max_value=0.01, allow_nan=False, allow_infinity=False),
        h33=st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_matrix_json_serialization_precision(self, h11, h12, h13, h21, h22, h23,
                                                   h31, h32, h33):
        """
        Feature: step-6-coordinate-mapping, Property 5: Calibration Serialization Round Trip

        For any valid 3x3 matrix (representing camera matrix or homography),
        JSON serialization should preserve numerical precision within 1e-6 tolerance.

        **Validates: Requirements AC-6.1.4**
        """
        # Create a general 3x3 matrix
        original_matrix = np.array([
            [h11, h12, h13],
            [h21, h22, h23],
            [h31, h32, h33]
        ], dtype=np.float64)

        # Serialize to JSON format (as list of lists)
        json_data = json.dumps({"matrix": original_matrix.tolist()})

        # Deserialize back
        loaded_data = json.loads(json_data)
        loaded_matrix = np.array(loaded_data["matrix"], dtype=np.float64)

        # Verify round trip within 1e-6 tolerance
        np.testing.assert_allclose(
            loaded_matrix, original_matrix, rtol=1e-6, atol=1e-6,
            err_msg="Matrix should be numerically equivalent after JSON round trip"
        )

    @given(
        # Generate random distortion coefficients with varying number of elements
        num_coeffs=st.integers(min_value=4, max_value=14),
        base_k1=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
        base_k2=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
        base_p1=st.floats(min_value=-0.01, max_value=0.01, allow_nan=False, allow_infinity=False),
        base_p2=st.floats(min_value=-0.01, max_value=0.01, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_distortion_coefficients_variable_length(self, num_coeffs, base_k1, base_k2,
                                                       base_p1, base_p2):
        """
        Feature: step-6-coordinate-mapping, Property 5: Calibration Serialization Round Trip

        For distortion coefficient arrays of varying lengths (4-14 elements),
        JSON serialization should preserve all values within 1e-6 tolerance.

        **Validates: Requirements AC-6.1.4**
        """
        # Create distortion coefficients with variable length
        # OpenCV supports 4, 5, 8, 12, or 14 distortion coefficients
        base_coeffs = [base_k1, base_k2, base_p1, base_p2]

        # Extend with additional coefficients (scaled down for higher-order terms)
        additional_coeffs = [base_k1 * 0.1 * (i + 1) for i in range(num_coeffs - 4)]
        original_distortion = np.array(base_coeffs + additional_coeffs, dtype=np.float64)

        # Serialize to JSON format
        json_data = json.dumps({"distortion_coeffs": original_distortion.tolist()})

        # Deserialize back
        loaded_data = json.loads(json_data)
        loaded_distortion = np.array(loaded_data["distortion_coeffs"], dtype=np.float64)

        # Verify round trip within 1e-6 tolerance
        np.testing.assert_allclose(
            loaded_distortion, original_distortion, rtol=1e-6, atol=1e-6,
            err_msg="Distortion coefficients should be numerically equivalent after JSON round trip"
        )

        # Verify length is preserved
        assert len(loaded_distortion) == len(original_distortion), (
            f"Distortion coefficient length should be preserved: "
            f"original={len(original_distortion)}, loaded={len(loaded_distortion)}"
        )

    @given(
        # Generate extreme but valid floating point values
        value=st.floats(
            min_value=-1e10, max_value=1e10,
            allow_nan=False, allow_infinity=False,
            allow_subnormal=False
        )
    )
    @settings(max_examples=100)
    def test_extreme_values_serialization(self, value):
        """
        Feature: step-6-coordinate-mapping, Property 5: Calibration Serialization Round Trip

        For extreme but valid floating point values, JSON serialization should
        preserve numerical precision within relative tolerance of 1e-6.

        **Validates: Requirements AC-6.1.4**
        """
        # Create a simple matrix with the extreme value
        original_matrix = np.array([
            [value, 0.0, 400.0],
            [0.0, value, 300.0],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)

        # Serialize to JSON format
        json_data = json.dumps({"matrix": original_matrix.tolist()})

        # Deserialize back
        loaded_data = json.loads(json_data)
        loaded_matrix = np.array(loaded_data["matrix"], dtype=np.float64)

        # Verify round trip - use relative tolerance for large values
        np.testing.assert_allclose(
            loaded_matrix, original_matrix, rtol=1e-6, atol=1e-10,
            err_msg=f"Matrix with extreme value {value} should be preserved after JSON round trip"
        )

    @given(
        camera_id=st.integers(min_value=0, max_value=2),
        fx=st.floats(min_value=500.0, max_value=1500.0, allow_nan=False, allow_infinity=False),
        fy=st.floats(min_value=500.0, max_value=1500.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_multiple_save_load_cycles(self, camera_id, fx, fy):
        """
        Feature: step-6-coordinate-mapping, Property 5: Calibration Serialization Round Trip

        Multiple save/load cycles should not accumulate numerical errors.
        After N cycles, the data should still be within 1e-6 tolerance of original.

        **Validates: Requirements AC-6.1.4**
        """
        calibrator = IntrinsicCalibrator(TEST_CONFIG)

        # Create original calibration data
        original_matrix = np.array([
            [fx, 0.0, 400.0],
            [0.0, fy, 300.0],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)
        original_distortion = np.array([0.1, -0.2, 0.001, 0.002, 0.05], dtype=np.float64)
        original_error = 0.35

        with tempfile.TemporaryDirectory() as tmpdir:
            current_matrix = original_matrix.copy()
            current_distortion = original_distortion.copy()
            current_error = original_error

            # Perform 5 save/load cycles
            for cycle in range(5):
                # Save
                calibrator.save_calibration(
                    camera_id=camera_id,
                    camera_matrix=current_matrix,
                    distortion_coeffs=current_distortion,
                    reprojection_error=current_error,
                    output_dir=tmpdir
                )

                # Load
                result = IntrinsicCalibrator.load_calibration(
                    camera_id=camera_id,
                    calibration_dir=tmpdir
                )

                assert result is not None, f"Should load calibration in cycle {cycle}"
                current_matrix, current_distortion, current_error = result

            # After 5 cycles, should still match original within tolerance
            np.testing.assert_allclose(
                current_matrix, original_matrix, rtol=1e-6, atol=1e-6,
                err_msg="Camera matrix should be stable after multiple save/load cycles"
            )
            np.testing.assert_allclose(
                current_distortion, original_distortion, rtol=1e-6, atol=1e-6,
                err_msg="Distortion coefficients should be stable after multiple save/load cycles"
            )

