"""
Feature matching for color-based dartboard calibration.

This module maps detected dartboard features to known board coordinates,
creating correspondence point pairs for homography computation.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .feature_detector import FeatureDetectionResult, SectorBoundary

logger = logging.getLogger(__name__)


@dataclass
class PointPair:
    """Represents a correspondence between pixel and board coordinates."""
    pixel: tuple[float, float]  # (u, v) pixel coordinates
    board: tuple[float, float]  # (x, y) board coordinates in millimeters


class FeatureMatcher:
    """
    Maps detected dartboard features to known board coordinates.
    
    Uses the Winmau Blade 6 dartboard geometry to create correspondence points:
    - Bull center → (0, 0)
    - Double ring points → 170mm radius
    - Triple ring points → 107mm radius
    - Wire intersections → computed from sector angle and ring radius
    
    Board coordinate system:
    - Origin (0, 0) at bull center
    - +X axis points right
    - +Y axis points up
    - Sector 20 at top (12 o'clock, 0° angle)
    - Sectors numbered clockwise: 20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5
    """
    
    # Winmau Blade 6 dartboard dimensions (in millimeters)
    DOUBLE_BULL_RADIUS = 6.35
    SINGLE_BULL_RADIUS = 15.9
    TRIPLE_RING_INNER_RADIUS = 99.0
    TRIPLE_RING_OUTER_RADIUS = 107.0
    DOUBLE_RING_INNER_RADIUS = 162.0
    DOUBLE_RING_OUTER_RADIUS = 170.0
    
    # Sector configuration
    SECTOR_WIDTH_DEGREES = 18.0  # 360° / 20 sectors
    SECTOR_ORDER = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
    
    def __init__(self, config: dict):
        """
        Initialize the feature matcher.
        
        Args:
            config: Configuration dictionary containing calibration parameters
        """
        self.config = config
        
        logger.info("FeatureMatcher initialized with Winmau Blade 6 geometry")
    
    def match(self, detection_result: FeatureDetectionResult) -> list[PointPair]:
        """
        Match detected features to known board coordinates.
        
        This is the main entry point for feature matching. It creates correspondence
        point pairs from detected features:
        1. Bull center → (0, 0)
        2. Ring edge points → known radii (170mm for double, 107mm for triple)
        3. Wire intersections → computed from sector angle and ring radius
        
        Args:
            detection_result: Result from FeatureDetector.detect()
        
        Returns:
            List of PointPair objects mapping pixel to board coordinates
        """
        point_pairs = []
        
        # 1. Bull center → (0, 0)
        if detection_result.bull_center is not None:
            point_pairs.append(PointPair(
                pixel=detection_result.bull_center,
                board=(0.0, 0.0)
            ))
            logger.debug(f"Matched bull center: {detection_result.bull_center} → (0, 0)")
        else:
            logger.warning("Bull center not detected - cannot create correspondence points")
            return point_pairs
        
        bull_u, bull_v = detection_result.bull_center
        
        # 2. Identify sector 20 (top of board) from radial wires
        sector_20_wire_index = self.identify_sector_20(
            detection_result.radial_wires,
            image_orientation='top'
        )
        
        # 3. Assign sectors to detected wires
        wire_sectors = {}
        if sector_20_wire_index is not None:
            wire_sectors = self.assign_wire_sectors(
                detection_result.radial_wires,
                sector_20_wire_index
            )
            logger.debug(f"Assigned sectors to {len(wire_sectors)} wires")
        else:
            logger.warning("Could not identify sector 20 - wire intersections will not be matched")
        
        # 4. Match wire intersections to board coordinates
        for intersection in detection_result.wire_intersections:
            wire_idx = intersection.wire_index
            
            # Only match if we know which sector this wire belongs to
            if wire_idx in wire_sectors:
                sector = wire_sectors[wire_idx]
                
                # Compute board coordinates for this intersection
                angle_rad = self._sector_to_angle(sector)
                
                # Use outer radius for each ring type
                if intersection.ring_type == 'double_ring':
                    radius = self.DOUBLE_RING_OUTER_RADIUS
                elif intersection.ring_type == 'triple_ring':
                    radius = self.TRIPLE_RING_OUTER_RADIUS
                else:
                    logger.warning(f"Unknown ring type: {intersection.ring_type}")
                    continue
                
                # Board coordinates (x, y) in millimeters
                x = radius * np.cos(angle_rad)
                y = radius * np.sin(angle_rad)
                
                point_pairs.append(PointPair(
                    pixel=intersection.pixel,
                    board=(float(x), float(y))
                ))
                
                logger.debug(
                    f"Matched wire {wire_idx} (sector {sector}) × {intersection.ring_type}: "
                    f"{intersection.pixel} → ({x:.1f}, {y:.1f})"
                )
        
        # 5. Add ring edge points (sampled along ellipse)
        # For each ring, estimate angle from bull center and map to board coordinates
        for ring_type, radius in [
            ('double_ring', self.DOUBLE_RING_OUTER_RADIUS),
            ('triple_ring', self.TRIPLE_RING_OUTER_RADIUS)
        ]:
            if ring_type not in detection_result.ring_edges:
                continue
            
            for pixel_point in detection_result.ring_edges[ring_type]:
                # Estimate angle from bull center to this point
                # Note: pixel coordinates have origin at top-left, +Y down
                # Board coordinates have origin at center, +Y up
                # So we need to flip Y when computing angle
                
                px, py = pixel_point
                dx = px - bull_u
                dy = bull_v - py  # Flip Y axis
                
                angle_rad = np.arctan2(dy, dx)
                
                # Board coordinates
                x = radius * np.cos(angle_rad)
                y = radius * np.sin(angle_rad)
                
                point_pairs.append(PointPair(
                    pixel=pixel_point,
                    board=(float(x), float(y))
                ))
        
        logger.info(
            f"Feature matching complete: {len(point_pairs)} correspondence points "
            f"(bull=1, intersections={len(detection_result.wire_intersections)}, "
            f"ring_edges={len(point_pairs) - 1 - len(detection_result.wire_intersections)})"
        )
        
        return point_pairs
    
    def identify_sector_20(
        self, 
        radial_wires: list[RadialWire],
        image_orientation: str = 'top'
    ) -> Optional[int]:
        """
        Identify which detected wire corresponds to sector 20 (top of board).
        
        Sector 20 is at the top of the dartboard (12 o'clock position). This method
        finds the radial wire that is closest to vertical (pointing up from bull).
        
        Args:
            radial_wires: List of detected RadialWire objects
            image_orientation: Expected board orientation in image ('top' means sector 20 at top)
        
        Returns:
            Index into radial_wires list for sector 20 wire, or None if not found
        """
        if not radial_wires:
            logger.debug("No radial wires provided for sector 20 identification")
            return None
        
        # Sector 20 is at top of board (12 o'clock)
        # In our angle convention: 0° = pointing up from bull
        # So we want the wire with angle closest to 0° (or 360°)
        
        best_wire_index = None
        best_score = float('inf')
        
        for i, wire in enumerate(radial_wires):
            # Wire angle is in degrees from vertical (0° = pointing up)
            angle = wire.angle
            
            # Distance from 0° (handle wraparound at 360°)
            dist_from_zero = min(angle, 360 - angle)
            
            # Score: prefer wires pointing up (angle near 0°)
            score = dist_from_zero
            
            if score < best_score:
                best_score = score
                best_wire_index = i
        
        if best_wire_index is not None:
            logger.debug(
                f"Identified sector 20 wire: index={best_wire_index}, "
                f"angle={radial_wires[best_wire_index].angle:.1f}°, "
                f"deviation={best_score:.1f}°"
            )
        
        return best_wire_index
    
    def assign_wire_sectors(
        self, 
        radial_wires: list[RadialWire],
        sector_20_index: int
    ) -> dict[int, int]:
        """
        Assign sector numbers to detected wires based on sector 20 identification.
        
        Uses the known sector order (clockwise from sector 20) and wire angles
        to assign sector numbers to each detected wire.
        
        Args:
            radial_wires: List of detected RadialWire objects
            sector_20_index: Index of the wire corresponding to sector 20
        
        Returns:
            Dictionary mapping wire index to sector number (1-20)
        """
        if sector_20_index < 0 or sector_20_index >= len(radial_wires):
            logger.warning(f"Invalid sector_20_index: {sector_20_index}")
            return {}
        
        wire_sectors = {}
        
        # Get the angle of sector 20 wire
        sector_20_angle = radial_wires[sector_20_index].angle
        
        # For each detected wire, compute its angular offset from sector 20
        for i, wire in enumerate(radial_wires):
            # Angular difference from sector 20 (clockwise positive)
            angle_diff = wire.angle - sector_20_angle
            
            # Normalize to [0, 360)
            angle_diff = angle_diff % 360
            
            # Determine which sector this wire belongs to
            # Each sector spans 18°, and sectors are numbered clockwise
            sector_index = int(round(angle_diff / self.SECTOR_WIDTH_DEGREES)) % 20
            
            # Map sector index to actual sector number using sector order
            sector_number = self.SECTOR_ORDER[sector_index]
            
            wire_sectors[i] = sector_number
            
            logger.debug(
                f"Wire {i} (angle={wire.angle:.1f}°, offset={angle_diff:.1f}°) → "
                f"sector_index={sector_index} → sector {sector_number}"
            )
        
        return wire_sectors
    
    def _sector_to_angle(self, sector: int) -> float:
        """
        Convert sector number to angle in radians.
        
        Sector 20 is at 0° (top of board), sectors increase clockwise.
        
        Args:
            sector: Sector number (1-20)
        
        Returns:
            Angle in radians (0 = right, π/2 = up, π = left, 3π/2 = down)
        """
        # Find sector index in sector order
        try:
            sector_index = self.SECTOR_ORDER.index(sector)
        except ValueError:
            logger.warning(f"Invalid sector number: {sector}")
            return 0.0
        
        # Sector 20 (index 0) is at top (90° in standard math convention)
        # Sectors increase clockwise, so we subtract from 90°
        angle_degrees = 90 - (sector_index * self.SECTOR_WIDTH_DEGREES)
        
        # Convert to radians
        angle_rad = np.deg2rad(angle_degrees)
        
        return angle_rad
