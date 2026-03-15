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
    
    # Standard control points for manual calibration.
    # Each point is a TRUE wire-wire intersection: where a sector boundary wire
    # physically crosses a ring wire. These are the most precise click targets
    # because they are single, unambiguous points (two wires crossing).
    #
    # Format: (label, (sector_a, sector_b), ring_radius_key, description)
    # - (sector_a, sector_b): The two sectors sharing the boundary wire
    # - ring_radius_key: Which ring wire to intersect with
    #
    # Points are distributed symmetrically: 2 boundaries per cardinal direction.
    # North: 20/1, 5/20  South: 19/3, 17/3  East: 6/13, 10/6  West: 8/11, 16/8
    # Each boundary has both iT (inner triple) and oD (outer double) = 8x2 + bull = 17.
    CONTROL_POINTS = [
        ("BULL", None, "bull", "Bull center"),
        # North
        ("iT 20/1", (20, 1), "triple_inner", "iT 20/1 - inner triple at 20/1 boundary"),
        ("iT 5/20", (5, 20), "triple_inner", "iT 5/20 - inner triple at 5/20 boundary"),
        # South
        ("iT 19/3", (19, 3), "triple_inner", "iT 19/3 - inner triple at 19/3 boundary"),
        ("iT 17/3", (17, 3), "triple_inner", "iT 17/3 - inner triple at 17/3 boundary"),
        # East
        ("iT 6/13", (6, 13), "triple_inner", "iT 6/13 - inner triple at 6/13 boundary"),
        ("iT 10/6", (10, 6), "triple_inner", "iT 10/6 - inner triple at 10/6 boundary"),
        # West
        ("iT 8/11", (8, 11), "triple_inner", "iT 8/11 - inner triple at 8/11 boundary"),
        ("iT 16/8", (16, 8), "triple_inner", "iT 16/8 - inner triple at 16/8 boundary"),
        # North
        ("oD 20/1", (20, 1), "double_outer", "oD 20/1 - outer double at 20/1 boundary"),
        ("oD 5/20", (5, 20), "double_outer", "oD 5/20 - outer double at 5/20 boundary"),
        # South
        ("oD 19/3", (19, 3), "double_outer", "oD 19/3 - outer double at 19/3 boundary"),
        ("oD 17/3", (17, 3), "double_outer", "oD 17/3 - outer double at 17/3 boundary"),
        # East
        ("oD 6/13", (6, 13), "double_outer", "oD 6/13 - outer double at 6/13 boundary"),
        ("oD 10/6", (10, 6), "double_outer", "oD 10/6 - outer double at 10/6 boundary"),
        # West
        ("oD 8/11", (8, 11), "double_outer", "oD 8/11 - outer double at 8/11 boundary"),
        ("oD 16/8", (16, 8), "double_outer", "oD 16/8 - outer double at 16/8 boundary"),
    ]
    
    # Map ring radius keys to actual radii for wire intersections.
    # These are the actual wire positions (not ring centers).
    RING_WIRE_RADII = {
        "bull": 0.0,
        "double_bull": DOUBLE_BULL_RADIUS,
        "single_bull": SINGLE_BULL_RADIUS,
        "triple_inner": TRIPLE_RING_INNER_RADIUS,
        "triple_outer": TRIPLE_RING_OUTER_RADIUS,
        "double_inner": DOUBLE_RING_INNER_RADIUS,
        "double_outer": DOUBLE_RING_OUTER_RADIUS,
    }
    
    def __init__(self):
        """Initialize board geometry."""
        logger.info("BoardGeometry initialized with Winmau Blade 6 dimensions")
    
    def get_control_point_coords(self) -> list[tuple[str, tuple[float, float]]]:
        """
        Get standard control points with their board coordinates.
        
        Control points are true wire-wire intersections: where a sector
        boundary wire crosses a ring wire.
        
        Returns:
            List of (label, (x, y)) tuples where x, y are in millimeters
        """
        control_points = []
        
        for label, sectors, ring_key, description in self.CONTROL_POINTS:
            if ring_key == "bull":
                control_points.append((label, (0.0, 0.0)))
                continue
            
            # Get the boundary angle between the two sectors
            sector_a, sector_b = sectors
            angle_rad = self.get_sector_boundary_angle(sector_a, sector_b)
            if angle_rad is None:
                logger.warning(f"Invalid sector boundary: {sector_a}/{sector_b}")
                continue
            
            # Get the ring wire radius
            radius = self.RING_WIRE_RADII.get(ring_key)
            if radius is None:
                logger.warning(f"Invalid ring key: {ring_key}")
                continue
            
            x = float(radius * np.cos(angle_rad))
            y = float(radius * np.sin(angle_rad))
            control_points.append((label, (x, y)))
            logger.debug(f"Control point {label}: ({x:.1f}, {y:.1f})")
        
        return control_points
    
    def get_sector_boundary_angle(self, sector_a: int, sector_b: int) -> Optional[float]:
        """
        Get the angle of the boundary wire between two adjacent sectors.
        
        The boundary wire sits at the clockwise edge of sector_a
        (= counter-clockwise edge of sector_b).
        
        Args:
            sector_a: First sector number
            sector_b: Second sector number (must be adjacent to sector_a)
        
        Returns:
            Angle in radians, or None if sectors are not adjacent
        """
        if sector_a not in self.SECTOR_ORDER or sector_b not in self.SECTOR_ORDER:
            return None
        
        idx_a = self.SECTOR_ORDER.index(sector_a)
        idx_b = self.SECTOR_ORDER.index(sector_b)
        
        # Check adjacency (wrapping around)
        if (idx_a + 1) % 20 == idx_b:
            # sector_b is clockwise from sector_a
            # Boundary is at the clockwise edge of sector_a
            # = center of sector_a minus half a sector width
            boundary_index = idx_a + 0.5
        elif (idx_b + 1) % 20 == idx_a:
            # sector_a is clockwise from sector_b
            # Boundary is at the clockwise edge of sector_b
            boundary_index = idx_b + 0.5
        else:
            logger.warning(f"Sectors {sector_a} and {sector_b} are not adjacent")
            return None
        
        # Convert boundary index to angle
        # Index 0 = sector 20 center at 90°, each index step = 18° clockwise
        angle_degrees = 90 - (boundary_index * self.SECTOR_WIDTH_DEGREES)
        angle_rad = np.deg2rad(angle_degrees) % (2 * np.pi)
        
        return float(angle_rad)
    
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
            homography: 3x3 homography matrix (image→board).
                        Internally inverted to board→image for projection.
            num_ring_samples: Number of points to sample per ring
        
        Returns:
            Dictionary with 'sector_boundaries' and 'rings' keys:
            - sector_boundaries: List of 20 line segments (each is [(u1,v1), (u2,v2)])
            - rings: Dict with ring names as keys, each containing list of (u,v) points
        """
        # The homography passed in maps image→board.
        # To project board coords onto the image, we need the inverse (board→image).
        try:
            H_board_to_image = np.linalg.inv(homography)
        except np.linalg.LinAlgError:
            logger.error("Cannot invert homography for spiderweb projection")
            return {'sector_boundaries': [], 'rings': {}}
        
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
            start_pixel = self.project_point(start_board, H_board_to_image)
            
            # End at board outer edge
            end_x = self.BOARD_RADIUS * np.cos(angle_rad)
            end_y = self.BOARD_RADIUS * np.sin(angle_rad)
            end_board = (float(end_x), float(end_y))
            end_pixel = self.project_point(end_board, H_board_to_image)
            
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
                pixel_coords = self.project_point(board_coords, H_board_to_image)
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
