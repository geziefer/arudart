"""
Board geometry for Winmau Blade 6 dartboard.

This module defines the physical dimensions and coordinate system of the
dartboard, and provides utilities for computing board coordinates and
projecting the spiderweb overlay.
"""

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class BoardGeometry:
    """
    Winmau Blade 6 dartboard geometry and coordinate system.
    
    Board coordinate system:
    - Origin (0, 0) at bull center
    - +X axis points right
    - +Y axis points up
    - Sector 20 at top (12 o'clock, 90° in standard math convention)
    - Sectors numbered clockwise: 20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5
    
    All dimensions in millimeters.
    """
    
    # Winmau Blade 6 dartboard dimensions (in millimeters)
    DOUBLE_BULL_RADIUS = 6.35
    SINGLE_BULL_RADIUS = 15.9
    TRIPLE_RING_INNER_RADIUS = 99.0
    TRIPLE_RING_OUTER_RADIUS = 107.0
    SINGLE_RING_INNER_RADIUS = 107.0  # Same as triple outer
    SINGLE_RING_OUTER_RADIUS = 162.0  # Same as double inner
    DOUBLE_RING_INNER_RADIUS = 162.0
    DOUBLE_RING_OUTER_RADIUS = 170.0
    BOARD_RADIUS = 225.5  # Total board radius (including number ring)
    
    # Sector configuration
    SECTOR_WIDTH_DEGREES = 18.0  # 360° / 20 sectors
    SECTOR_ORDER = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
    
    # Standard control points for manual calibration
    # Format: (label, sector, ring_type, description)
    CONTROL_POINTS = [
        ("BULL", None, "bull", "Bull center"),
        ("T20", 20, "triple", "Triple 20 (top)"),
        ("T5", 5, "triple", "Triple 5 (left)"),
        ("T1", 1, "triple", "Triple 1 (right)"),
        ("D20", 20, "double", "Double 20 (top)"),
        ("D5", 5, "double", "Double 5 (left)"),
        ("D1", 1, "double", "Double 1 (right)"),
        ("S18", 18, "single", "Single 18 (upper right)"),
        ("S4", 4, "single", "Single 4 (upper left)"),
        ("S13", 13, "single", "Single 13 (lower left)"),
        ("S6", 6, "single", "Single 6 (lower right)"),
    ]
    
    def __init__(self):
        """Initialize board geometry."""
        logger.info("BoardGeometry initialized with Winmau Blade 6 dimensions")
    
    def get_control_point_coords(self) -> list[tuple[str, tuple[float, float]]]:
        """
        Get standard control points with their board coordinates.
        
        Returns:
            List of (label, (x, y)) tuples where x, y are in millimeters
        """
        control_points = []
        
        for label, sector, ring_type, description in self.CONTROL_POINTS:
            coords = self.get_board_coords(sector, ring_type)
            if coords is not None:
                control_points.append((label, coords))
                logger.debug(f"Control point {label}: {coords}")
        
        return control_points
    
    def get_sector_angle(self, sector: int) -> float:
        """
        Convert sector number to angle in radians.
        
        Sector 20 is at 90° (top of board), sectors increase clockwise.
        
        Args:
            sector: Sector number (1-20)
        
        Returns:
            Angle in radians (0 = right, π/2 = up, π = left, 3π/2 = down)
        """
        if sector not in self.SECTOR_ORDER:
            logger.warning(f"Invalid sector number: {sector}")
            return 0.0
        
        # Find sector index in sector order
        sector_index = self.SECTOR_ORDER.index(sector)
        
        # Sector 20 (index 0) is at top (90° in standard math convention)
        # Sectors increase clockwise, so we subtract from 90°
        angle_degrees = 90 - (sector_index * self.SECTOR_WIDTH_DEGREES)
        
        # Convert to radians
        angle_rad = np.deg2rad(angle_degrees)
        
        # Normalize to [0, 2π)
        angle_rad = angle_rad % (2 * np.pi)
        
        return angle_rad
    
    def get_board_coords(
        self, 
        sector: Optional[int], 
        ring_type: str
    ) -> Optional[tuple[float, float]]:
        """
        Get board coordinates for a specific sector and ring combination.
        
        Args:
            sector: Sector number (1-20), or None for bull
            ring_type: One of 'bull', 'triple', 'single', 'double'
        
        Returns:
            (x, y) board coordinates in millimeters, or None if invalid
        """
        # Handle bull center
        if ring_type == "bull":
            return (0.0, 0.0)
        
        # Validate sector
        if sector is None or sector not in self.SECTOR_ORDER:
            logger.warning(f"Invalid sector: {sector}")
            return None
        
        # Get sector angle
        angle_rad = self.get_sector_angle(sector)
        
        # Determine radius based on ring type
        # Use the middle of each ring for control points
        if ring_type == "triple":
            radius = (self.TRIPLE_RING_INNER_RADIUS + self.TRIPLE_RING_OUTER_RADIUS) / 2
        elif ring_type == "single":
            # Single ring is between triple and double
            radius = (self.SINGLE_RING_INNER_RADIUS + self.SINGLE_RING_OUTER_RADIUS) / 2
        elif ring_type == "double":
            radius = (self.DOUBLE_RING_INNER_RADIUS + self.DOUBLE_RING_OUTER_RADIUS) / 2
        else:
            logger.warning(f"Invalid ring type: {ring_type}")
            return None
        
        # Compute board coordinates
        x = radius * np.cos(angle_rad)
        y = radius * np.sin(angle_rad)
        
        return (float(x), float(y))
    
    def project_point(
        self, 
        board_coords: tuple[float, float], 
        homography: np.ndarray
    ) -> tuple[float, float]:
        """
        Project board coordinates to pixel coordinates using homography.
        
        Args:
            board_coords: (x, y) board coordinates in millimeters
            homography: 3x3 homography matrix
        
        Returns:
            (u, v) pixel coordinates
        """
        x, y = board_coords
        
        # Create homogeneous coordinates
        point_h = np.array([[x, y, 1.0]], dtype=np.float32).T
        
        # Apply homography
        result = homography @ point_h
        
        # Convert from homogeneous to Cartesian
        u = result[0, 0] / result[2, 0]
        v = result[1, 0] / result[2, 0]
        
        return (float(u), float(v))
    
    def generate_spiderweb(
        self, 
        homography: np.ndarray,
        num_ring_samples: int = 360
    ) -> dict:
        """
        Generate complete spiderweb overlay (all sector boundaries and rings).
        
        Args:
            homography: 3x3 homography matrix
            num_ring_samples: Number of points to sample per ring
        
        Returns:
            Dictionary with 'sector_boundaries' and 'rings' keys:
            - sector_boundaries: List of 20 line segments (each is [(u1,v1), (u2,v2)])
            - rings: Dict with ring names as keys, each containing list of (u,v) points
        """
        spiderweb = {
            'sector_boundaries': [],
            'rings': {}
        }
        
        # Generate sector boundaries (20 radial lines from bull to outer edge)
        for sector in self.SECTOR_ORDER:
            angle_rad = self.get_sector_angle(sector)
            
            # Line from bull center to outer edge
            # Start at bull center
            start_board = (0.0, 0.0)
            start_pixel = self.project_point(start_board, homography)
            
            # End at board outer edge
            end_x = self.BOARD_RADIUS * np.cos(angle_rad)
            end_y = self.BOARD_RADIUS * np.sin(angle_rad)
            end_board = (float(end_x), float(end_y))
            end_pixel = self.project_point(end_board, homography)
            
            spiderweb['sector_boundaries'].append([start_pixel, end_pixel])
        
        # Generate rings (circles at various radii)
        ring_radii = {
            'double_bull': self.DOUBLE_BULL_RADIUS,
            'single_bull': self.SINGLE_BULL_RADIUS,
            'triple_inner': self.TRIPLE_RING_INNER_RADIUS,
            'triple_outer': self.TRIPLE_RING_OUTER_RADIUS,
            'double_inner': self.DOUBLE_RING_INNER_RADIUS,
            'double_outer': self.DOUBLE_RING_OUTER_RADIUS,
        }
        
        for ring_name, radius in ring_radii.items():
            ring_points = []
            
            for i in range(num_ring_samples):
                angle_rad = 2 * np.pi * i / num_ring_samples
                
                # Board coordinates
                x = radius * np.cos(angle_rad)
                y = radius * np.sin(angle_rad)
                board_coords = (float(x), float(y))
                
                # Project to pixels
                pixel_coords = self.project_point(board_coords, homography)
                ring_points.append(pixel_coords)
            
            spiderweb['rings'][ring_name] = ring_points
        
        logger.debug(
            f"Generated spiderweb: {len(spiderweb['sector_boundaries'])} boundaries, "
            f"{len(spiderweb['rings'])} rings"
        )
        
        return spiderweb
    
    def draw_spiderweb(
        self, 
        image: np.ndarray, 
        spiderweb: dict,
        color: tuple[int, int, int] = (0, 255, 255),
        thickness: int = 1
    ) -> np.ndarray:
        """
        Draw spiderweb overlay on image.
        
        Args:
            image: Input image (BGR)
            spiderweb: Spiderweb data from generate_spiderweb()
            color: Line color (B, G, R)
            thickness: Line thickness
        
        Returns:
            Image with spiderweb overlay
        """
        overlay = image.copy()
        
        # Draw sector boundaries
        for line in spiderweb['sector_boundaries']:
            start, end = line
            cv2.line(
                overlay,
                (int(start[0]), int(start[1])),
                (int(end[0]), int(end[1])),
                color,
                thickness
            )
        
        # Draw rings
        for ring_name, points in spiderweb['rings'].items():
            for i in range(len(points)):
                start = points[i]
                end = points[(i + 1) % len(points)]
                cv2.line(
                    overlay,
                    (int(start[0]), int(start[1])),
                    (int(end[0]), int(end[1])),
                    color,
                    thickness
                )
        
        return overlay
