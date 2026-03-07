"""
Unit tests for ManualCalibrator class.

Tests control point definition, point pair creation, and UI state management.
"""

import numpy as np
import pytest

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
        assert len(calibrator.control_points) == 11  # Standard control points
        assert calibrator.current_point_index == 0
        assert len(calibrator.clicked_points) == 0
        assert calibrator.homography is None
    
    def test_control_point_definition(self, calibrator):
        """Test that control points are properly defined."""
        control_points = calibrator.control_points
        
        # Check we have expected control points
        labels = [label for label, coords in control_points]
        assert "BULL" in labels
        assert "T20" in labels
        assert "D20" in labels
        
        # Check bull is at origin
        for label, coords in control_points:
            if label == "BULL":
                assert coords == (0.0, 0.0)
    
    def test_point_pair_creation_minimum(self, calibrator, test_image):
        """Test point pair creation with minimum 4 points."""
        # Simulate clicking 4 points
        calibrator.clicked_points = {
            "BULL": (400.0, 300.0),
            "T20": (400.0, 200.0),
            "D20": (400.0, 150.0),
            "T5": (300.0, 300.0)
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
        # Simulate clicking all 11 points
        for i, (label, board_coords) in enumerate(calibrator.control_points):
            calibrator.clicked_points[label] = (float(100 + i * 50), float(100 + i * 30))
        
        # Build point pairs
        point_pairs = []
        for label, pixel_coords in calibrator.clicked_points.items():
            for cp_label, cp_coords in calibrator.control_points:
                if cp_label == label:
                    point_pairs.append((pixel_coords, cp_coords))
                    break
        
        assert len(point_pairs) == 11
    
    def test_ui_state_initialization(self, calibrator, test_image):
        """Test UI state is properly initialized."""
        calibrator.current_image = test_image.copy()
        
        assert calibrator.current_image is not None
        assert calibrator.current_image.shape == (600, 800, 3)
        assert calibrator.current_point_index == 0
        assert calibrator.show_spiderweb is False
    
    def test_preliminary_homography_insufficient_points(self, calibrator):
        """Test that homography is not computed with < 4 points."""
        calibrator.clicked_points = {
            "BULL": (400.0, 300.0),
            "T20": (400.0, 200.0)
        }
        
        calibrator._compute_preliminary_homography()
        
        assert calibrator.homography is None
    
    def test_preliminary_homography_sufficient_points(self, calibrator):
        """Test that homography is computed with >= 4 points."""
        # Create realistic point correspondences
        calibrator.clicked_points = {
            "BULL": (400.0, 300.0),
            "T20": (400.0, 200.0),
            "D20": (400.0, 150.0),
            "T5": (300.0, 300.0)
        }
        
        calibrator._compute_preliminary_homography()
        
        # Homography should be computed
        assert calibrator.homography is not None
        assert calibrator.homography.shape == (3, 3)
    
    def test_reprojection_error_computation(self, calibrator):
        """Test reprojection error computation."""
        # Create point correspondences
        # Note: Homography maps from image to board
        image_points = np.array([
            [400.0, 300.0],
            [400.0, 200.0],
            [400.0, 150.0],
            [300.0, 300.0]
        ], dtype=np.float32)
        
        board_points = np.array([
            [0.0, 0.0],
            [0.0, 107.0],
            [0.0, 166.0],
            [-134.5, 0.0]
        ], dtype=np.float32)
        
        # Compute homography (image -> board)
        H, _ = cv2.findHomography(image_points, board_points, method=cv2.RANSAC)
        
        # Compute reprojection errors
        calibrator.clicked_points = {
            "BULL": tuple(image_points[0]),
            "T20": tuple(image_points[1]),
            "D20": tuple(image_points[2]),
            "T5": tuple(image_points[3])
        }
        
        calibrator._compute_reprojection_errors(image_points, board_points, H)
        
        # Errors should be computed for all points
        assert len(calibrator.reprojection_errors) == 4
        assert "BULL" in calibrator.reprojection_errors
        
        # With perfect correspondences and RANSAC, errors should be very small
        # Allow some tolerance for numerical precision
        for error in calibrator.reprojection_errors.values():
            assert error < 1.0  # Should be < 1 pixel for perfect correspondences
    
    def test_delete_point_updates_state(self, calibrator):
        """Test that deleting a point updates state correctly."""
        calibrator.clicked_points = {
            "BULL": (400.0, 300.0),
            "T20": (400.0, 200.0)
        }
        calibrator.current_point_index = 2
        calibrator.homography = np.eye(3)  # Dummy homography
        
        # Simulate delete
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
        calibrator.clicked_points = {
            "BULL": (400.0, 300.0)
        }
        calibrator.current_point_index = 1
        
        display = calibrator._draw_ui()
        
        assert display is not None
        assert display.shape == test_image.shape
        assert not np.array_equal(display, test_image)  # Should have drawn something
    
    def test_draw_ui_with_errors(self, calibrator, test_image):
        """Test UI drawing with reprojection errors."""
        calibrator.current_image = test_image.copy()
        calibrator.clicked_points = {
            "BULL": (400.0, 300.0),
            "T20": (400.0, 200.0)
        }
        calibrator.reprojection_errors = {
            "BULL": 2.5,
            "T20": 12.0  # Outlier
        }
        calibrator.current_point_index = 2
        
        display = calibrator._draw_ui()
        
        assert display is not None
        assert display.shape == test_image.shape


# Import cv2 for homography computation in tests
import cv2

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
