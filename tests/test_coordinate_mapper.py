"""
Unit tests for CoordinateMapper class.

Tests coordinate transformation, calibration loading, and error handling
using synthetic calibration data.
"""

import json
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.calibration.coordinate_mapper import CoordinateMapper


class TestCoordinateMapper:
    """Test suite for CoordinateMapper class."""
    
    @pytest.fixture
    def temp_calibration_dir(self):
        """Create temporary calibration directory with synthetic data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create synthetic intrinsic calibration for cam0
            intrinsic_data = {
                'camera_id': 0,
                'camera_matrix': [
                    [800.0, 0.0, 400.0],
                    [0.0, 800.0, 300.0],
                    [0.0, 0.0, 1.0]
                ],
                'distortion_coeffs': [0.0, 0.0, 0.0, 0.0, 0.0],
                'reprojection_error': 0.3,
                'image_size': [800, 600],
                'calibration_date': '2024-01-15T10:30:00'
            }
            
            with open(tmpdir_path / 'intrinsic_cam0.json', 'w') as f:
                json.dump(intrinsic_data, f)
            
            # Create synthetic homography for cam0
            # Simple identity-like homography for testing
            # Maps image center (400, 300) to board origin (0, 0)
            # Scale: 1 pixel ≈ 0.5mm
            H = np.array([
                [0.5, 0.0, -200.0],
                [0.0, 0.5, -150.0],
                [0.0, 0.0, 1.0]
            ])
            
            homography_data = {
                'camera_id': 0,
                'homography': H.tolist(),
                'num_points': 8,
                'num_inliers': 8,
                'reprojection_error_mm': 2.5,
                'timestamp': '2024-01-15T10:35:00'
            }
            
            with open(tmpdir_path / 'homography_cam0.json', 'w') as f:
                json.dump(homography_data, f)
            
            yield tmpdir_path
    
    @pytest.fixture
    def coordinate_mapper(self, temp_calibration_dir):
        """Create CoordinateMapper instance with synthetic data."""
        config = {}
        return CoordinateMapper(config, str(temp_calibration_dir))
    
    def test_initialization(self, coordinate_mapper):
        """Test CoordinateMapper initialization."""
        assert coordinate_mapper is not None
        assert coordinate_mapper.calibration_dir is not None
    
    def test_load_valid_calibration(self, coordinate_mapper):
        """Test loading valid calibration files."""
        # cam0 should be calibrated (we created files for it)
        assert coordinate_mapper.is_calibrated(0)
        
        # cam1 and cam2 should not be calibrated (no files)
        assert not coordinate_mapper.is_calibrated(1)
        assert not coordinate_mapper.is_calibrated(2)
    
    def test_get_calibrated_cameras(self, coordinate_mapper):
        """Test getting list of calibrated cameras."""
        calibrated = coordinate_mapper.get_calibrated_cameras()
        assert 0 in calibrated
        assert 1 not in calibrated
        assert 2 not in calibrated
    
    def test_map_to_board_center(self, coordinate_mapper):
        """Test mapping image center to board origin."""
        # Image center (400, 300) should map to board origin (0, 0)
        result = coordinate_mapper.map_to_board(0, 400.0, 300.0)
        
        assert result is not None
        x, y = result
        
        # Should be very close to origin
        assert abs(x) < 1.0  # Within 1mm
        assert abs(y) < 1.0
    
    def test_map_to_board_offset(self, coordinate_mapper):
        """Test mapping offset pixel to board coordinates."""
        # Pixel (600, 300) should map to (100, 0) with our synthetic homography
        # (600 - 400) * 0.5 = 100mm
        result = coordinate_mapper.map_to_board(0, 600.0, 300.0)
        
        assert result is not None
        x, y = result
        
        # Should be at (100, 0)
        assert abs(x - 100.0) < 1.0
        assert abs(y) < 1.0
    
    def test_map_to_board_uncalibrated_camera(self, coordinate_mapper):
        """Test mapping with uncalibrated camera returns None."""
        result = coordinate_mapper.map_to_board(1, 400.0, 300.0)
        assert result is None
    
    def test_map_to_board_out_of_bounds(self, coordinate_mapper):
        """Test mapping point outside board bounds returns None."""
        # Map a point far from center that would be > 200mm radius
        # Pixel (1200, 300) -> (400, 0) which is > 200mm radius
        result = coordinate_mapper.map_to_board(0, 1200.0, 300.0)
        assert result is None
    
    def test_map_to_image(self, coordinate_mapper):
        """Test inverse mapping from board to image coordinates."""
        # Board origin (0, 0) should map to image center (400, 300)
        result = coordinate_mapper.map_to_image(0, 0.0, 0.0)
        
        assert result is not None
        u, v = result
        
        # Should be at image center
        assert abs(u - 400.0) < 1.0
        assert abs(v - 300.0) < 1.0
    
    def test_map_to_image_uncalibrated_camera(self, coordinate_mapper):
        """Test inverse mapping with uncalibrated camera returns None."""
        result = coordinate_mapper.map_to_image(1, 0.0, 0.0)
        assert result is None
    
    def test_coordinate_system_convention(self, coordinate_mapper):
        """Test coordinate system convention (origin, axes)."""
        # Test that +X is right, +Y is up in board coordinates
        
        # Right of center in image (u increases)
        result_right = coordinate_mapper.map_to_board(0, 500.0, 300.0)
        assert result_right is not None
        x_right, y_right = result_right
        assert x_right > 0  # +X is right
        
        # Down from center in image (v increases)
        # Our synthetic homography maps v increase to y decrease
        # This is correct: image v down = board y down (both increase downward in our setup)
        result_down = coordinate_mapper.map_to_board(0, 400.0, 400.0)
        assert result_down is not None
        x_down, y_down = result_down
        
        # With our synthetic H, v increase should give y increase
        # H[1,1] = 0.5, H[1,2] = -150
        # y = 0.5 * 400 - 150 = 50
        assert y_down > 0  # y increases when v increases
    
    def test_reload_calibration(self, coordinate_mapper, temp_calibration_dir):
        """Test reloading calibration from disk."""
        # Initially cam0 is calibrated
        assert coordinate_mapper.is_calibrated(0)
        
        # Create calibration for cam1
        H = np.eye(3)
        homography_data = {
            'camera_id': 1,
            'homography': H.tolist(),
            'num_points': 4,
            'num_inliers': 4,
            'reprojection_error_mm': 3.0,
            'timestamp': '2024-01-15T11:00:00'
        }
        
        with open(temp_calibration_dir / 'homography_cam1.json', 'w') as f:
            json.dump(homography_data, f)
        
        # Reload calibration
        coordinate_mapper.reload_calibration(1)
        
        # Now cam1 should be calibrated
        assert coordinate_mapper.is_calibrated(1)
    
    def test_reload_all_calibrations(self, coordinate_mapper):
        """Test reloading all calibrations."""
        # This should not crash even if some files don't exist
        coordinate_mapper.reload_calibration(None)
        
        # cam0 should still be calibrated
        assert coordinate_mapper.is_calibrated(0)
    
    def test_missing_calibration_files_graceful(self):
        """Test handling missing calibration files gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {}
            mapper = CoordinateMapper(config, tmpdir)
            
            # Should initialize without errors
            assert mapper is not None
            
            # No cameras should be calibrated
            assert len(mapper.get_calibrated_cameras()) == 0
    
    def test_thread_safety_basic(self, coordinate_mapper):
        """Test basic thread safety (no crashes with concurrent access)."""
        import threading
        
        results = []
        errors = []
        
        def worker():
            try:
                for _ in range(100):
                    result = coordinate_mapper.map_to_board(0, 400.0, 300.0)
                    results.append(result)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = [threading.Thread(target=worker) for _ in range(4)]
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Should have no errors
        assert len(errors) == 0
        
        # All results should be consistent
        assert len(results) == 400
        for result in results:
            assert result is not None
            x, y = result
            assert abs(x) < 1.0
            assert abs(y) < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
