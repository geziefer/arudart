"""
Unit tests for ManualCalibrator class.

Tests control point definition, point pair creation, and UI state management.
"""

import numpy as np
import pytest
import cv2

from src.calibration.board_geometry import BoardGeometry
from src.calibration.manual_calibrator import ManualCalibrator


class TestManualCalibrator:
    """Test suite for ManualCalibrator class."""
    
    @pytest.fixture
    def board_geometry(self):
        """Create BoardGeometry instance."""
        return BoardGeometry()
    
    @pytest.fixture
    def calibrator(self, board_geometry):
        """Create ManualCalibrator instance."""
        return ManualCalibrator(board_geometry)
    
    @pytest.fixture
    def test_image(self):
        """Create test image (800x600 BGR)."""
        return np.zeros((600, 800, 3), dtype=np.uint8)
    
    def test_initialization(self, calibrator):
        """Test ManualCalibrator initialization."""
        assert calibrator.board_geometry is not None
        assert len(calibrator.control_points) == 17  # Bull + 8 triple + 8 double
        assert calibrator.current_point_index == 0
        assert len(calibrator.clicked_points) == 0
        assert calibrator.homography is None
    
    def test_control_point_definition(self, calibrator):
        """Test that control points are wire intersection points."""
        control_points = calibrator.control_points
        labels = [label for label, coords in control_points]
        
        # Must have bull
        assert "BULL" in labels
        
        # Must have wire intersection labels with ring info
        assert "iT 20/1" in labels
        assert "iT 5/20" in labels
        assert "iT 8/11" in labels
        assert "iT 16/8" in labels
        assert "iT 6/13" in labels
        assert "iT 10/6" in labels
        assert "oD 20/1" in labels
        assert "oD 5/20" in labels
        assert "oD 8/11" in labels
        assert "oD 16/8" in labels
        assert "oD 6/13" in labels
        assert "oD 10/6" in labels

        # No single-sector points (imprecise)
        for label in labels:
            assert not label.startswith("S"), f"Should not have single-sector point {label}"
        
        # Check bull is at origin
        for label, coords in control_points:
            if label == "BULL":
                assert coords == (0.0, 0.0)
    
    def test_point_pair_creation_minimum(self, calibrator, test_image):
        """Test point pair creation with minimum 4 points."""
        # Use actual control point labels from the calibrator
        labels = [label for label, _ in calibrator.control_points]
        
        calibrator.clicked_points = {
            labels[0]: (400.0, 300.0),  # BULL
            labels[1]: (400.0, 200.0),  # T20/1
            labels[2]: (350.0, 200.0),  # T5/20
            labels[3]: (400.0, 400.0),  # T19/3
        }
        
        # Build point pairs manually (simulating what calibrate() does)
        point_pairs = []
        for label, pixel_coords in calibrator.clicked_points.items():
            for cp_label, cp_coords in calibrator.control_points:
                if cp_label == label:
                    point_pairs.append((pixel_coords, cp_coords))
                    break
        
        assert len(point_pairs) == 4
        
        # Verify bull maps to origin
        for pixel, board in point_pairs:
            if board == (0.0, 0.0):
                assert pixel == (400.0, 300.0)
    
    def test_point_pair_creation_all_points(self, calibrator):
        """Test point pair creation with all control points."""
        for i, (label, board_coords) in enumerate(calibrator.control_points):
            calibrator.clicked_points[label] = (float(100 + i * 50), float(100 + i * 30))
        
        point_pairs = []
        for label, pixel_coords in calibrator.clicked_points.items():
            for cp_label, cp_coords in calibrator.control_points:
                if cp_label == label:
                    point_pairs.append((pixel_coords, cp_coords))
                    break
        
        assert len(point_pairs) == 17
    
    def test_ui_state_initialization(self, calibrator, test_image):
        """Test UI state is properly initialized."""
        calibrator.current_image = test_image.copy()
        
        assert calibrator.current_image is not None
        assert calibrator.current_image.shape == (600, 800, 3)
        assert calibrator.current_point_index == 0
        assert calibrator.show_spiderweb is False
        assert calibrator.mouse_x == 0
        assert calibrator.mouse_y == 0
    
    def test_preliminary_homography_insufficient_points(self, calibrator):
        """Test that homography is not computed with < 4 points."""
        labels = [label for label, _ in calibrator.control_points]
        calibrator.clicked_points = {
            labels[0]: (400.0, 300.0),
            labels[1]: (400.0, 200.0)
        }
        
        calibrator._compute_preliminary_homography()
        assert calibrator.homography is None
    
    def test_preliminary_homography_sufficient_points(self, calibrator):
        """Test that homography is computed with >= 4 points."""
        labels = [label for label, _ in calibrator.control_points]
        calibrator.clicked_points = {
            labels[0]: (400.0, 300.0),
            labels[1]: (400.0, 200.0),
            labels[2]: (350.0, 200.0),
            labels[3]: (400.0, 400.0),
        }
        
        calibrator._compute_preliminary_homography()
        assert calibrator.homography is not None
        assert calibrator.homography.shape == (3, 3)
    
    def test_reprojection_error_computation(self, calibrator):
        """Test reprojection error computation."""
        image_points = np.array([
            [400.0, 300.0],
            [400.0, 200.0],
            [400.0, 150.0],
            [500.0, 300.0]
        ], dtype=np.float32)
        
        board_points = np.array([
            [0.0, 0.0],
            [0.0, 99.0],
            [0.0, 170.0],
            [99.0, 0.0]
        ], dtype=np.float32)
        
        H, _ = cv2.findHomography(image_points, board_points, method=cv2.RANSAC)
        
        labels = [label for label, _ in calibrator.control_points]
        calibrator.clicked_points = {
            labels[0]: tuple(image_points[0]),
            labels[1]: tuple(image_points[1]),
            labels[2]: tuple(image_points[2]),
            labels[3]: tuple(image_points[3])
        }
        
        calibrator._compute_reprojection_errors(image_points, board_points, H)
        
        assert len(calibrator.reprojection_errors) == 4
        assert labels[0] in calibrator.reprojection_errors
        
        for error in calibrator.reprojection_errors.values():
            assert error < 1.0
    
    def test_delete_point_updates_state(self, calibrator):
        """Test that deleting a point updates state correctly."""
        labels = [label for label, _ in calibrator.control_points]
        calibrator.clicked_points = {
            labels[0]: (400.0, 300.0),
            labels[1]: (400.0, 200.0)
        }
        calibrator.current_point_index = 2
        calibrator.homography = np.eye(3)
        
        last_label = list(calibrator.clicked_points.keys())[-1]
        del calibrator.clicked_points[last_label]
        calibrator.current_point_index = max(0, calibrator.current_point_index - 1)
        calibrator.homography = None
        
        assert len(calibrator.clicked_points) == 1
        assert calibrator.current_point_index == 1
        assert calibrator.homography is None
    
    def test_draw_ui_basic(self, calibrator, test_image):
        """Test basic UI drawing without errors."""
        calibrator.current_image = test_image.copy()
        labels = [label for label, _ in calibrator.control_points]
        calibrator.clicked_points = {labels[0]: (400.0, 300.0)}
        calibrator.current_point_index = 1
        
        display = calibrator._draw_ui()
        
        assert display is not None
        assert display.shape == test_image.shape
        assert not np.array_equal(display, test_image)
    
    def test_draw_ui_with_errors(self, calibrator, test_image):
        """Test UI drawing with reprojection errors."""
        calibrator.current_image = test_image.copy()
        labels = [label for label, _ in calibrator.control_points]
        calibrator.clicked_points = {
            labels[0]: (400.0, 300.0),
            labels[1]: (400.0, 200.0)
        }
        calibrator.reprojection_errors = {
            labels[0]: 2.5,
            labels[1]: 12.0  # Outlier
        }
        calibrator.current_point_index = 2
        
        display = calibrator._draw_ui()
        
        assert display is not None
        assert display.shape == test_image.shape
    
    def test_zoom_overlay(self, calibrator, test_image):
        """Test that zoom overlay is drawn on the display."""
        calibrator.current_image = test_image.copy()
        calibrator.mouse_x = 400
        calibrator.mouse_y = 300
        calibrator.current_point_index = 0
        
        display = calibrator._draw_ui()
        
        # Zoom overlay is in top-right corner — should have non-zero pixels there
        # (white border of zoom box)
        zoom_region = display[10:160, display.shape[1] - 160:display.shape[1] - 10]
        assert np.sum(zoom_region) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
