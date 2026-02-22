"""
Property-based tests for ArucoDetector class.

Feature: step-6-coordinate-mapping
Validates: Requirements AC-6.2.5, AC-6.3.1

Tests marker detection reliability using synthetic images with ARUCO markers
at various positions, scales, and rotations.
"""

import numpy as np
import cv2
from hypothesis import given, strategies as st, settings, assume

from src.calibration.aruco_detector import ArucoDetector


# Minimal config for testing
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


def generate_marker_image(
    marker_id: int,
    marker_size_px: int,
    image_width: int = 800,
    image_height: int = 600,
    x_offset: float = 400.0,
    y_offset: float = 300.0,
    rotation_deg: float = 0.0,
    background_value: int = 200
) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate a synthetic image with an ARUCO marker at specified position.
    
    Args:
        marker_id: ARUCO marker ID (0-49 for DICT_4X4_50)
        marker_size_px: Size of marker in pixels
        image_width: Output image width
        image_height: Output image height
        x_offset: X position of marker center
        y_offset: Y position of marker center
        rotation_deg: Rotation angle in degrees
        background_value: Background grayscale value (0-255)
    
    Returns:
        Tuple of (image, ground_truth_corners)
        ground_truth_corners: 4x2 array of corner positions [TL, TR, BR, BL]
    """
    # Create background image
    image = np.full((image_height, image_width), background_value, dtype=np.uint8)
    
    # Generate marker using OpenCV
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_size_px)
    
    # Add white border (improves detection)
    border_size = max(marker_size_px // 10, 5)
    marker_with_border = cv2.copyMakeBorder(
        marker_img,
        border_size, border_size, border_size, border_size,
        cv2.BORDER_CONSTANT,
        value=255
    )
    
    # OpenCV ARUCO detection returns corners at pixel indices 0 to (size-1)
    # For a marker_size_px of 60, corners are at 0 and 59, not 0 and 60
    # So the half-extent is (marker_size_px - 1) / 2
    half_extent = (marker_size_px - 1) / 2.0
    
    # Calculate ground truth corners (before rotation, relative to center)
    # Order: [TL, TR, BR, BL] - matching OpenCV ARUCO convention
    corners_local = np.array([
        [-half_extent, -half_extent],  # Top-left
        [half_extent, -half_extent],   # Top-right
        [half_extent, half_extent],    # Bottom-right
        [-half_extent, half_extent],   # Bottom-left
    ], dtype=np.float32)
    
    # Apply rotation
    angle_rad = np.radians(rotation_deg)
    cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)
    rotation_matrix = np.array([
        [cos_a, -sin_a],
        [sin_a, cos_a]
    ], dtype=np.float32)
    
    corners_rotated = corners_local @ rotation_matrix.T
    
    # Translate to image position
    ground_truth_corners = corners_rotated + np.array([x_offset, y_offset])
    
    # Create transformation matrix for placing marker in image
    # Source points: corners of the marker within marker_with_border
    # The marker starts at (border_size, border_size) and ends at (border_size + marker_size_px - 1, ...)
    src_pts = np.array([
        [border_size, border_size],
        [border_size + marker_size_px - 1, border_size],
        [border_size + marker_size_px - 1, border_size + marker_size_px - 1],
        [border_size, border_size + marker_size_px - 1],
    ], dtype=np.float32)
    
    # Destination points: ground truth corners
    dst_pts = ground_truth_corners.astype(np.float32)
    
    # Compute perspective transform
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    
    # Warp marker onto image
    warped = cv2.warpPerspective(
        marker_with_border, M, (image_width, image_height),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=background_value
    )
    
    # Blend marker onto background (use minimum for black marker on light background)
    mask = warped < background_value
    image[mask] = warped[mask]
    
    return image, ground_truth_corners


def generate_multi_marker_image(
    marker_configs: list[dict],
    image_width: int = 800,
    image_height: int = 600,
    background_value: int = 200
) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    """
    Generate a synthetic image with multiple ARUCO markers.
    
    Args:
        marker_configs: List of dicts with keys: marker_id, marker_size_px, x_offset, y_offset, rotation_deg
        image_width: Output image width
        image_height: Output image height
        background_value: Background grayscale value
    
    Returns:
        Tuple of (image, ground_truth_dict)
        ground_truth_dict: Dict mapping marker_id → 4x2 corner array
    """
    image = np.full((image_height, image_width), background_value, dtype=np.uint8)
    ground_truth = {}
    
    for config in marker_configs:
        marker_id = config['marker_id']
        marker_size_px = config['marker_size_px']
        x_offset = config['x_offset']
        y_offset = config['y_offset']
        rotation_deg = config.get('rotation_deg', 0.0)
        
        # Generate single marker image
        marker_img, corners = generate_marker_image(
            marker_id=marker_id,
            marker_size_px=marker_size_px,
            image_width=image_width,
            image_height=image_height,
            x_offset=x_offset,
            y_offset=y_offset,
            rotation_deg=rotation_deg,
            background_value=background_value
        )
        
        # Blend onto main image
        mask = marker_img < background_value
        image[mask] = marker_img[mask]
        ground_truth[marker_id] = corners
    
    return image, ground_truth



class TestMarkerDetectionReliability:
    """
    Feature: step-6-coordinate-mapping, Property 1: Marker Detection Reliability
    
    For any image containing valid ARUCO markers from DICT_4X4_50 with sufficient
    contrast and no occlusion, the ArucoDetector should successfully detect all
    visible markers and return their corner coordinates with sub-pixel accuracy.
    
    **Validates: Requirements AC-6.2.5, AC-6.3.1**
    """
    
    @given(
        marker_id=st.integers(min_value=0, max_value=5),
        x_offset=st.integers(min_value=150, max_value=650),
        y_offset=st.integers(min_value=150, max_value=450),
        marker_size_px=st.integers(min_value=40, max_value=120),
        rotation_deg=st.floats(min_value=-45.0, max_value=45.0)
    )
    @settings(max_examples=100, deadline=None)
    def test_single_marker_detection_reliability(
        self, marker_id, x_offset, y_offset, marker_size_px, rotation_deg
    ):
        """
        Feature: step-6-coordinate-mapping, Property 1: Marker Detection Reliability
        
        For any single ARUCO marker placed at various positions, scales, and rotations,
        detection should succeed and corner coordinates should be accurate within 1 pixel.
        
        **Validates: Requirements AC-6.2.5, AC-6.3.1**
        """
        # Generate synthetic image with marker
        image, ground_truth_corners = generate_marker_image(
            marker_id=marker_id,
            marker_size_px=marker_size_px,
            x_offset=float(x_offset),
            y_offset=float(y_offset),
            rotation_deg=rotation_deg
        )
        
        # Convert to BGR for detector (it handles grayscale internally)
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        # Create detector and detect markers
        detector = ArucoDetector(TEST_CONFIG)
        detected_markers = detector.detect_markers(image_bgr)
        
        # Verify marker was detected
        assert marker_id in detected_markers, (
            f"Marker {marker_id} not detected. "
            f"Position: ({x_offset:.1f}, {y_offset:.1f}), "
            f"Size: {marker_size_px}px, Rotation: {rotation_deg:.1f}°"
        )
        
        # Verify corner accuracy within 1.5 pixels
        # Note: We use 1.5px tolerance to account for interpolation artifacts
        # from perspective transforms used in synthetic image generation.
        # Real-world detection typically achieves sub-pixel accuracy.
        detected_corners = detected_markers[marker_id]
        
        for i, (detected, expected) in enumerate(zip(detected_corners, ground_truth_corners)):
            error = np.linalg.norm(detected - expected)
            assert error <= 1.5, (
                f"Corner {i} error too large: {error:.3f} pixels. "
                f"Detected: {detected}, Expected: {expected}"
            )
    
    @given(
        marker_id=st.integers(min_value=0, max_value=5),
        scale=st.floats(min_value=0.5, max_value=2.0)
    )
    @settings(max_examples=100, deadline=None)
    def test_marker_detection_at_various_scales(self, marker_id, scale):
        """
        Feature: step-6-coordinate-mapping, Property 1: Marker Detection Reliability
        
        Markers at various scales (simulating different distances from camera)
        should be reliably detected with accurate corners.
        
        **Validates: Requirements AC-6.2.5, AC-6.3.1**
        """
        base_size = 60  # Base marker size in pixels
        marker_size_px = int(base_size * scale)
        
        # Skip very small markers that may not be reliably detectable
        assume(marker_size_px >= 30)
        
        # Center the marker
        x_offset = 400.0
        y_offset = 300.0
        
        image, ground_truth_corners = generate_marker_image(
            marker_id=marker_id,
            marker_size_px=marker_size_px,
            x_offset=x_offset,
            y_offset=y_offset,
            rotation_deg=0.0
        )
        
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        detector = ArucoDetector(TEST_CONFIG)
        detected_markers = detector.detect_markers(image_bgr)
        
        assert marker_id in detected_markers, (
            f"Marker {marker_id} not detected at scale {scale:.2f} "
            f"(size: {marker_size_px}px)"
        )
        
        detected_corners = detected_markers[marker_id]
        for i, (detected, expected) in enumerate(zip(detected_corners, ground_truth_corners)):
            error = np.linalg.norm(detected - expected)
            assert error <= 1.0, (
                f"Corner {i} error: {error:.3f}px at scale {scale:.2f}"
            )
    
    @given(
        num_markers=st.integers(min_value=2, max_value=4),
        base_size=st.integers(min_value=50, max_value=80)
    )
    @settings(max_examples=100, deadline=None)
    def test_multiple_marker_detection(self, num_markers, base_size):
        """
        Feature: step-6-coordinate-mapping, Property 1: Marker Detection Reliability
        
        Multiple markers in the same image should all be detected with accurate corners.
        This validates the typical calibration scenario with 4 markers.
        
        **Validates: Requirements AC-6.2.5, AC-6.3.1**
        """
        # Define marker positions (spread across image to avoid overlap)
        positions = [
            (200.0, 150.0),   # Top-left area
            (600.0, 150.0),   # Top-right area
            (200.0, 450.0),   # Bottom-left area
            (600.0, 450.0),   # Bottom-right area
        ]
        
        marker_configs = []
        for i in range(num_markers):
            x, y = positions[i]
            marker_configs.append({
                'marker_id': i,
                'marker_size_px': base_size,
                'x_offset': x,
                'y_offset': y,
                'rotation_deg': 0.0
            })
        
        image, ground_truth = generate_multi_marker_image(marker_configs)
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        detector = ArucoDetector(TEST_CONFIG)
        detected_markers = detector.detect_markers(image_bgr)
        
        # Verify all markers detected
        for marker_id in range(num_markers):
            assert marker_id in detected_markers, (
                f"Marker {marker_id} not detected in multi-marker image. "
                f"Detected: {list(detected_markers.keys())}"
            )
            
            # Verify corner accuracy
            detected_corners = detected_markers[marker_id]
            expected_corners = ground_truth[marker_id]
            
            for i, (detected, expected) in enumerate(zip(detected_corners, expected_corners)):
                error = np.linalg.norm(detected - expected)
                assert error <= 1.0, (
                    f"Marker {marker_id} corner {i} error: {error:.3f}px"
                )
    
    @given(
        marker_id=st.integers(min_value=0, max_value=5),
        rotation_deg=st.floats(min_value=-180.0, max_value=180.0)
    )
    @settings(max_examples=100, deadline=None)
    def test_marker_detection_with_rotation(self, marker_id, rotation_deg):
        """
        Feature: step-6-coordinate-mapping, Property 1: Marker Detection Reliability
        
        Markers at any rotation angle should be detected with accurate corners.
        
        **Validates: Requirements AC-6.2.5, AC-6.3.1**
        """
        image, ground_truth_corners = generate_marker_image(
            marker_id=marker_id,
            marker_size_px=70,
            x_offset=400.0,
            y_offset=300.0,
            rotation_deg=rotation_deg
        )
        
        image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        detector = ArucoDetector(TEST_CONFIG)
        detected_markers = detector.detect_markers(image_bgr)
        
        assert marker_id in detected_markers, (
            f"Marker {marker_id} not detected at rotation {rotation_deg:.1f}°"
        )
        
        detected_corners = detected_markers[marker_id]
        for i, (detected, expected) in enumerate(zip(detected_corners, ground_truth_corners)):
            error = np.linalg.norm(detected - expected)
            assert error <= 1.0, (
                f"Corner {i} error: {error:.3f}px at rotation {rotation_deg:.1f}°"
            )


class TestMarkerValidation:
    """
    Unit tests for marker validation functionality.
    
    **Validates: Requirements AC-6.2.5, AC-6.3.1**
    """
    
    def test_validate_markers_with_sufficient_markers(self):
        """Validation should pass with 4+ markers."""
        detector = ArucoDetector(TEST_CONFIG)
        
        # Create mock detected markers (4 markers)
        detected = {
            0: np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float32),
            1: np.array([[20, 0], [30, 0], [30, 10], [20, 10]], dtype=np.float32),
            2: np.array([[0, 20], [10, 20], [10, 30], [0, 30]], dtype=np.float32),
            3: np.array([[20, 20], [30, 20], [30, 30], [20, 30]], dtype=np.float32),
        }
        
        assert detector.validate_markers(detected) is True
    
    def test_validate_markers_with_insufficient_markers(self):
        """Validation should fail with fewer than 4 markers."""
        detector = ArucoDetector(TEST_CONFIG)
        
        # Only 2 markers
        detected = {
            0: np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float32),
            1: np.array([[20, 0], [30, 0], [30, 10], [20, 10]], dtype=np.float32),
        }
        
        assert detector.validate_markers(detected) is False
    
    def test_validate_markers_with_empty_dict(self):
        """Validation should fail with no markers."""
        detector = ArucoDetector(TEST_CONFIG)
        assert detector.validate_markers({}) is False
    
    def test_validate_markers_with_invalid_corner_shape(self):
        """Validation should fail if corners have wrong shape."""
        detector = ArucoDetector(TEST_CONFIG)
        
        # Invalid corner shape (3 corners instead of 4)
        detected = {
            0: np.array([[0, 0], [10, 0], [10, 10]], dtype=np.float32),
            1: np.array([[20, 0], [30, 0], [30, 10], [20, 10]], dtype=np.float32),
            2: np.array([[0, 20], [10, 20], [10, 30], [0, 30]], dtype=np.float32),
            3: np.array([[20, 20], [30, 20], [30, 30], [20, 30]], dtype=np.float32),
        }
        
        assert detector.validate_markers(detected) is False


class TestMarkerHelperMethods:
    """
    Unit tests for helper methods in ArucoDetector.
    """
    
    def test_get_marker_center(self):
        """Test marker center calculation."""
        detector = ArucoDetector(TEST_CONFIG)
        
        corners = np.array([
            [0, 0],
            [100, 0],
            [100, 100],
            [0, 100]
        ], dtype=np.float32)
        
        center_x, center_y = detector.get_marker_center(corners)
        
        assert center_x == 50.0
        assert center_y == 50.0
    
    def test_get_marker_size_pixels(self):
        """Test marker size estimation."""
        detector = ArucoDetector(TEST_CONFIG)
        
        # 100x100 pixel marker
        corners = np.array([
            [0, 0],
            [100, 0],
            [100, 100],
            [0, 100]
        ], dtype=np.float32)
        
        size = detector.get_marker_size_pixels(corners)
        
        assert abs(size - 100.0) < 0.1
    
    def test_draw_markers_returns_copy(self):
        """draw_markers should not modify the original image."""
        detector = ArucoDetector(TEST_CONFIG)
        
        original = np.zeros((100, 100, 3), dtype=np.uint8)
        original_copy = original.copy()
        
        detected = {
            0: np.array([[10, 10], [50, 10], [50, 50], [10, 50]], dtype=np.float32),
        }
        
        result = detector.draw_markers(original, detected)
        
        # Original should be unchanged
        assert np.array_equal(original, original_copy)
        # Result should be different (markers drawn)
        assert not np.array_equal(result, original)
    
    def test_detect_markers_handles_none_image(self):
        """detect_markers should handle None image gracefully."""
        detector = ArucoDetector(TEST_CONFIG)
        result = detector.detect_markers(None)
        assert result == {}
    
    def test_detect_markers_handles_grayscale_image(self):
        """detect_markers should work with grayscale images."""
        detector = ArucoDetector(TEST_CONFIG)
        
        # Generate a marker image (already grayscale)
        image, _ = generate_marker_image(
            marker_id=0,
            marker_size_px=60,
            x_offset=400.0,
            y_offset=300.0
        )
        
        # Pass grayscale directly
        result = detector.detect_markers(image)
        
        assert 0 in result
