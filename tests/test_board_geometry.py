"""
Unit tests for BoardGeometry class.

Tests the dartboard geometry calculations, control point definitions,
and spiderweb projection functionality.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pytest

from src.calibration.board_geometry import BoardGeometry


class TestBoardGeometry:
    """Test BoardGeometry class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.geometry = BoardGeometry()
    
    def test_initialization(self):
        """Test BoardGeometry initialization."""
        assert self.geometry is not None
        assert len(self.geometry.SECTOR_ORDER) == 20
        assert self.geometry.SECTOR_ORDER[0] == 20  # Sector 20 at top
    
    def test_control_point_coords(self):
        """Test control point coordinate generation."""
        control_points = self.geometry.get_control_point_coords()
        
        # Should have 11 standard control points
        assert len(control_points) == 11
        
        # Check bull center
        bull_points = [cp for cp in control_points if cp[0] == "BULL"]
        assert len(bull_points) == 1
        assert bull_points[0][1] == (0.0, 0.0)
        
        # Check T20 is at top (positive Y)
        t20_points = [cp for cp in control_points if cp[0] == "T20"]
        assert len(t20_points) == 1
        x, y = t20_points[0][1]
        assert abs(x) < 1.0  # Should be near X=0 (top of board)
        assert y > 100.0  # Should be positive Y (up)
    
    def test_sector_angle_sector_20(self):
        """Test sector angle calculation for sector 20 (top)."""
        angle = self.geometry.get_sector_angle(20)
        
        # Sector 20 should be at 90° (π/2 radians)
        expected = np.pi / 2
        assert abs(angle - expected) < 0.01
    
    def test_sector_angle_sector_order(self):
        """Test sector angles follow clockwise order."""
        # Sector 20 at 90°, sector 1 at 72° (18° clockwise), etc.
        angle_20 = self.geometry.get_sector_angle(20)
        angle_1 = self.geometry.get_sector_angle(1)
        
        # Sector 1 should be 18° clockwise from sector 20
        # In standard math convention, clockwise is negative
        expected_diff = -np.deg2rad(18)
        actual_diff = angle_1 - angle_20
        
        assert abs(actual_diff - expected_diff) < 0.01
    
    def test_sector_angle_all_sectors(self):
        """Test all 20 sectors have valid angles."""
        for sector in self.geometry.SECTOR_ORDER:
            angle = self.geometry.get_sector_angle(sector)
            
            # Angle should be in valid range [0, 2π)
            assert 0 <= angle < 2 * np.pi
    
    def test_board_coords_bull(self):
        """Test board coordinates for bull center."""
        coords = self.geometry.get_board_coords(None, "bull")
        
        assert coords == (0.0, 0.0)
    
    def test_board_coords_triple_20(self):
        """Test board coordinates for T20."""
        coords = self.geometry.get_board_coords(20, "triple")
        
        assert coords is not None
        x, y = coords
        
        # T20 should be at top (near X=0, positive Y)
        assert abs(x) < 1.0
        assert y > 100.0
        
        # Radius should be middle of triple ring
        radius = np.sqrt(x**2 + y**2)
        expected_radius = (self.geometry.TRIPLE_RING_INNER_RADIUS + 
                          self.geometry.TRIPLE_RING_OUTER_RADIUS) / 2
        assert abs(radius - expected_radius) < 0.1
    
    def test_board_coords_double_20(self):
        """Test board coordinates for D20."""
        coords = self.geometry.get_board_coords(20, "double")
        
        assert coords is not None
        x, y = coords
        
        # D20 should be at top (near X=0, positive Y)
        assert abs(x) < 1.0
        assert y > 160.0
        
        # Radius should be middle of double ring
        radius = np.sqrt(x**2 + y**2)
        expected_radius = (self.geometry.DOUBLE_RING_INNER_RADIUS + 
                          self.geometry.DOUBLE_RING_OUTER_RADIUS) / 2
        assert abs(radius - expected_radius) < 0.1
    
    def test_board_coords_single(self):
        """Test board coordinates for single ring."""
        coords = self.geometry.get_board_coords(20, "single")
        
        assert coords is not None
        x, y = coords
        
        # Radius should be middle of single ring (between triple and double)
        radius = np.sqrt(x**2 + y**2)
        expected_radius = (self.geometry.SINGLE_RING_INNER_RADIUS + 
                          self.geometry.SINGLE_RING_OUTER_RADIUS) / 2
        assert abs(radius - expected_radius) < 0.1
    
    def test_board_coords_invalid_sector(self):
        """Test board coordinates with invalid sector."""
        coords = self.geometry.get_board_coords(99, "triple")
        
        assert coords is None
    
    def test_board_coords_invalid_ring(self):
        """Test board coordinates with invalid ring type."""
        coords = self.geometry.get_board_coords(20, "invalid")
        
        assert coords is None
    
    def test_project_point_identity(self):
        """Test point projection with identity homography."""
        # Identity homography (no transformation)
        H = np.eye(3, dtype=np.float32)
        
        board_coords = (100.0, 50.0)
        pixel_coords = self.geometry.project_point(board_coords, H)
        
        # With identity, pixel coords should equal board coords
        assert abs(pixel_coords[0] - board_coords[0]) < 0.01
        assert abs(pixel_coords[1] - board_coords[1]) < 0.01
    
    def test_project_point_translation(self):
        """Test point projection with translation."""
        # Translation homography (shift by 100, 200)
        H = np.array([
            [1, 0, 100],
            [0, 1, 200],
            [0, 0, 1]
        ], dtype=np.float32)
        
        board_coords = (50.0, 30.0)
        pixel_coords = self.geometry.project_point(board_coords, H)
        
        # Should be translated
        assert abs(pixel_coords[0] - 150.0) < 0.01  # 50 + 100
        assert abs(pixel_coords[1] - 230.0) < 0.01  # 30 + 200
    
    def test_generate_spiderweb_structure(self):
        """Test spiderweb generation structure."""
        # Use identity homography for simplicity
        H = np.eye(3, dtype=np.float32)
        
        spiderweb = self.geometry.generate_spiderweb(H, num_ring_samples=36)
        
        # Check structure
        assert 'sector_boundaries' in spiderweb
        assert 'rings' in spiderweb
        
        # Should have 20 sector boundaries
        assert len(spiderweb['sector_boundaries']) == 20
        
        # Each boundary should be a line (2 points)
        for boundary in spiderweb['sector_boundaries']:
            assert len(boundary) == 2
            assert len(boundary[0]) == 2  # (u, v)
            assert len(boundary[1]) == 2  # (u, v)
        
        # Should have 6 rings
        assert len(spiderweb['rings']) == 6
        
        # Each ring should have num_ring_samples points
        for ring_name, points in spiderweb['rings'].items():
            assert len(points) == 36
    
    def test_generate_spiderweb_bull_center(self):
        """Test that sector boundaries start at bull center."""
        # Use identity homography
        H = np.eye(3, dtype=np.float32)
        
        spiderweb = self.geometry.generate_spiderweb(H)
        
        # All sector boundaries should start at (0, 0)
        for boundary in spiderweb['sector_boundaries']:
            start = boundary[0]
            assert abs(start[0]) < 0.01
            assert abs(start[1]) < 0.01
    
    def test_generate_spiderweb_ring_radii(self):
        """Test that rings have correct radii."""
        # Use identity homography
        H = np.eye(3, dtype=np.float32)
        
        spiderweb = self.geometry.generate_spiderweb(H)
        
        # Check double_bull ring radius
        double_bull_points = spiderweb['rings']['double_bull']
        for point in double_bull_points:
            radius = np.sqrt(point[0]**2 + point[1]**2)
            assert abs(radius - self.geometry.DOUBLE_BULL_RADIUS) < 0.1
        
        # Check triple_outer ring radius
        triple_outer_points = spiderweb['rings']['triple_outer']
        for point in triple_outer_points:
            radius = np.sqrt(point[0]**2 + point[1]**2)
            assert abs(radius - self.geometry.TRIPLE_RING_OUTER_RADIUS) < 0.1
    
    def test_draw_spiderweb(self):
        """Test spiderweb drawing on image."""
        # Create blank image
        image = np.zeros((600, 800, 3), dtype=np.uint8)
        
        # Use identity homography centered in image
        H = np.array([
            [1, 0, 400],  # Translate to center X
            [0, 1, 300],  # Translate to center Y
            [0, 0, 1]
        ], dtype=np.float32)
        
        spiderweb = self.geometry.generate_spiderweb(H, num_ring_samples=36)
        overlay = self.geometry.draw_spiderweb(image, spiderweb)
        
        # Check that overlay is not all black (something was drawn)
        assert np.sum(overlay) > 0
        
        # Check that overlay has same shape as input
        assert overlay.shape == image.shape


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
