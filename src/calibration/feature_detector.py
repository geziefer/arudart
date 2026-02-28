"""
Feature detection for spiderweb-based dartboard calibration.

This module detects dartboard features (bull center, ring edges, radial wires)
in camera images for use in coordinate mapping calibration.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RadialWire:
    """Represents a detected radial wire on the dartboard."""
    angle: float  # degrees from vertical (0° = pointing up)
    endpoints: tuple[tuple[float, float], tuple[float, float]]  # ((x1, y1), (x2, y2))
    confidence: float  # detection confidence score


@dataclass
class WireIntersection:
    """Represents an intersection between a radial wire and a ring edge."""
    pixel: tuple[float, float]  # (u, v) pixel coordinates
    ring_type: str  # 'double_ring' or 'triple_ring'
    wire_index: int  # index into radial_wires list
    sector_estimate: Optional[int]  # estimated sector number (1-20), None if unknown


@dataclass
class FeatureDetectionResult:
    """Result of dartboard feature detection."""
    bull_center: Optional[tuple[float, float]]  # (u, v) pixel coordinates, None if not detected
    ring_edges: dict[str, list[tuple[float, float]]]  # 'double_ring', 'triple_ring' -> list of (u, v) points
    radial_wires: list[RadialWire]  # detected radial wires
    wire_intersections: list[WireIntersection]  # wire-ring intersections
    detection_time_ms: float  # time taken for detection
    error: Optional[str] = None  # error message if detection failed


class FeatureDetector:
    """
    Detects dartboard features (bull, rings, radial wires) for calibration.
    
    Uses computer vision techniques to identify the dartboard's natural geometry:
    - Bull center: Small dark circle at board center
    - Ring edges: Double ring (170mm) and triple ring (107mm) as ellipses
    - Radial wires: 20 wires separating sectors, detected as lines through bull
    - Wire intersections: Points where radial wires cross ring edges
    """
    
    def __init__(self, config: dict):
        """
        Initialize the feature detector.
        
        Args:
            config: Configuration dictionary containing calibration.feature_detection parameters
        """
        self.config = config
        
        # Load feature detection parameters from config
        feature_config = config.get('calibration', {}).get('feature_detection', {})
        
        self.bull_min_radius_px = feature_config.get('bull_min_radius_px', 10)
        self.bull_max_radius_px = feature_config.get('bull_max_radius_px', 30)
        self.canny_threshold_low = feature_config.get('canny_threshold_low', 50)
        self.canny_threshold_high = feature_config.get('canny_threshold_high', 150)
        self.hough_line_threshold = feature_config.get('hough_line_threshold', 50)
        self.min_wire_length_px = feature_config.get('min_wire_length_px', 50)
        
        logger.info(
            f"FeatureDetector initialized: bull_radius=[{self.bull_min_radius_px}, {self.bull_max_radius_px}], "
            f"canny=[{self.canny_threshold_low}, {self.canny_threshold_high}], "
            f"hough_threshold={self.hough_line_threshold}, min_wire_length={self.min_wire_length_px}"
        )
    
    def detect(self, image: np.ndarray) -> FeatureDetectionResult:
        """
        Detect all dartboard features in the given image.
        
        This is the main entry point for feature detection. It orchestrates
        the detection of bull center, ring edges, radial wires, and their
        intersections.
        
        Args:
            image: Input image (BGR, 8-bit) from camera
        
        Returns:
            FeatureDetectionResult containing all detected features
        """
        start_time = time.time()
        
        # Detect bull center first (required for other detections)
        bull_center = self.detect_bull_center(image)
        
        if bull_center is None:
            logger.warning("Bull center not detected - check lighting and camera position")
            return FeatureDetectionResult(
                bull_center=None,
                ring_edges={},
                radial_wires=[],
                wire_intersections=[],
                detection_time_ms=(time.time() - start_time) * 1000,
                error="BULL_NOT_DETECTED"
            )
        
        # Detect ring edges using bull center as reference
        ring_edges = self.detect_ring_edges(image, bull_center)
        
        # Detect radial wires
        radial_wires = self.detect_radial_wires(image, bull_center)
        
        # Find wire-ring intersections
        wire_intersections = self.find_wire_intersections(ring_edges, radial_wires)
        
        detection_time_ms = (time.time() - start_time) * 1000
        
        # Check if we have sufficient features for calibration
        num_intersections = len(wire_intersections)
        if num_intersections < 4:
            logger.warning(
                f"Insufficient features detected: {num_intersections} intersections < 4 minimum"
            )
            return FeatureDetectionResult(
                bull_center=bull_center,
                ring_edges=ring_edges,
                radial_wires=radial_wires,
                wire_intersections=wire_intersections,
                detection_time_ms=detection_time_ms,
                error="INSUFFICIENT_FEATURES"
            )
        
        logger.info(
            f"Feature detection complete: bull={bull_center is not None}, "
            f"double_ring_pts={len(ring_edges.get('double_ring', []))}, "
            f"triple_ring_pts={len(ring_edges.get('triple_ring', []))}, "
            f"wires={len(radial_wires)}, intersections={num_intersections}, "
            f"time={detection_time_ms:.1f}ms"
        )
        
        return FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges=ring_edges,
            radial_wires=radial_wires,
            wire_intersections=wire_intersections,
            detection_time_ms=detection_time_ms
        )
    
    def detect_bull_center(self, image: np.ndarray) -> Optional[tuple[float, float]]:
        """
        Detect the bull center using Hough circle detection.
        
        The bull appears as a small dark circle at the board center. This method
        uses HoughCircles to find circles in the expected radius range, then
        selects the best candidate based on position and accumulator value.
        
        Args:
            image: Input image (BGR, 8-bit)
        
        Returns:
            (u, v) pixel coordinates of bull center, or None if not detected
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Use HoughCircles to detect circles
        # Parameters tuned for bull detection (small dark circle)
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1,  # Inverse ratio of accumulator resolution
            minDist=100,  # Minimum distance between circle centers (only one bull)
            param1=50,  # Canny edge detection high threshold (lowered from 100)
            param2=20,  # Accumulator threshold (lowered from 30 for more sensitivity)
            minRadius=self.bull_min_radius_px,
            maxRadius=self.bull_max_radius_px
        )
        
        if circles is None or len(circles[0]) == 0:
            logger.debug("No circles detected in expected bull radius range")
            return None
        
        # circles shape: (1, N, 3) where each circle is (x, y, radius)
        circles = circles[0]
        
        # If only one circle found, use it
        if len(circles) == 1:
            x, y, r = circles[0]
            logger.debug(f"Single bull candidate detected at ({x:.1f}, {y:.1f}), radius={r:.1f}")
            return (float(x), float(y))
        
        # Multiple circles found - select best candidate
        # Score by: proximity to image center + accumulator strength
        image_center = (image.shape[1] / 2, image.shape[0] / 2)
        
        best_circle = None
        best_score = -float('inf')
        
        for circle in circles:
            x, y, r = circle
            
            # Distance from image center (normalized by image diagonal)
            dist_from_center = np.sqrt((x - image_center[0])**2 + (y - image_center[1])**2)
            image_diagonal = np.sqrt(image.shape[1]**2 + image.shape[0]**2)
            normalized_dist = dist_from_center / image_diagonal
            
            # Score: prefer circles near image center
            # (accumulator strength is implicit in HoughCircles detection)
            score = -normalized_dist
            
            if score > best_score:
                best_score = score
                best_circle = circle
        
        if best_circle is None:
            return None
        
        x, y, r = best_circle
        logger.debug(
            f"Best bull candidate: ({x:.1f}, {y:.1f}), radius={r:.1f}, "
            f"dist_from_center={np.sqrt((x - image_center[0])**2 + (y - image_center[1])**2):.1f}px"
        )
        
        # Refine center with sub-pixel accuracy using contour moments
        # Create a mask around the detected circle
        mask = np.zeros(gray.shape, dtype=np.uint8)
        cv2.circle(mask, (int(x), int(y)), int(r * 1.5), 255, -1)
        
        # Threshold to find dark bull region
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        thresh = cv2.bitwise_and(thresh, mask)
        
        # Find contours in the thresholded region
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            # Find the largest contour (should be the bull)
            largest_contour = max(contours, key=cv2.contourArea)
            
            # Compute moments for sub-pixel center
            M = cv2.moments(largest_contour)
            if M['m00'] > 0:
                refined_x = M['m10'] / M['m00']
                refined_y = M['m01'] / M['m00']
                
                # Only use refined center if it's close to Hough detection
                if np.sqrt((refined_x - x)**2 + (refined_y - y)**2) < r:
                    logger.debug(f"Refined bull center: ({refined_x:.2f}, {refined_y:.2f})")
                    return (float(refined_x), float(refined_y))
        
        # Fall back to Hough detection if refinement fails
        return (float(x), float(y))
    
    def detect_ring_edges(
        self, 
        image: np.ndarray, 
        bull_center: tuple[float, float]
    ) -> dict[str, list[tuple[float, float]]]:
        """
        Detect ring edges (double and triple rings) as ellipses.
        
        Uses Canny edge detection and ellipse fitting to find the double ring
        (170mm radius) and triple ring (107mm radius). Returns sampled points
        along the fitted ellipses.
        
        Args:
            image: Input image (BGR, 8-bit)
            bull_center: (u, v) pixel coordinates of bull center
        
        Returns:
            Dictionary with 'double_ring' and 'triple_ring' keys, each containing
            a list of (u, v) points along the ring edge
        """
        result = {'double_ring': [], 'triple_ring': []}
        
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply Canny edge detection
        edges = cv2.Canny(gray, self.canny_threshold_low, self.canny_threshold_high)
        
        # Estimate pixel scale based on bull size
        # Bull outer radius is ~15.9mm, detected bull radius is in pixels
        # We can estimate the scale, but we'll use a more robust approach:
        # Assume bull radius detection gives us roughly 15-25 pixels for a ~16mm bull
        # This means ~1.5 pixels per mm
        # Double ring: 170mm → ~255 pixels
        # Triple ring: 107mm → ~160 pixels
        
        bull_u, bull_v = bull_center
        
        # Define ring parameters: (name, expected_radius_mm, expected_radius_px, tolerance_px)
        # We'll estimate based on typical camera setup
        ring_params = [
            ('double_ring', 170, 255, 20),  # Double ring at ~170mm
            ('triple_ring', 107, 160, 20),  # Triple ring at ~107mm
        ]
        
        for ring_name, radius_mm, expected_radius_px, tolerance_px in ring_params:
            # Create annular mask around expected radius
            mask = np.zeros(edges.shape, dtype=np.uint8)
            cv2.circle(
                mask, 
                (int(bull_u), int(bull_v)), 
                int(expected_radius_px + tolerance_px), 
                255, 
                -1
            )
            cv2.circle(
                mask, 
                (int(bull_u), int(bull_v)), 
                int(expected_radius_px - tolerance_px), 
                0, 
                -1
            )
            
            # Extract edge points within mask
            masked_edges = cv2.bitwise_and(edges, mask)
            
            # Find edge points
            edge_points = np.column_stack(np.where(masked_edges > 0))
            
            if len(edge_points) < 5:
                logger.debug(f"Insufficient edge points for {ring_name}: {len(edge_points)} < 5")
                continue
            
            # Convert from (row, col) to (x, y) for ellipse fitting
            edge_points_xy = edge_points[:, [1, 0]].astype(np.float32)
            
            try:
                # Fit ellipse to edge points
                ellipse = cv2.fitEllipse(edge_points_xy)
                
                # ellipse format: ((center_x, center_y), (width, height), angle)
                center, axes, angle = ellipse
                
                # Verify ellipse is reasonable (center near bull, appropriate size)
                center_dist = np.sqrt((center[0] - bull_u)**2 + (center[1] - bull_v)**2)
                if center_dist > 50:  # Ellipse center should be near bull
                    logger.debug(
                        f"{ring_name} ellipse center too far from bull: {center_dist:.1f}px"
                    )
                    continue
                
                # Sample points along fitted ellipse
                num_samples = 36  # Sample every 10 degrees
                sampled_points = []
                
                for i in range(num_samples):
                    theta = 2 * np.pi * i / num_samples
                    
                    # Parametric ellipse equation
                    # x = center_x + (width/2) * cos(theta) * cos(angle) - (height/2) * sin(theta) * sin(angle)
                    # y = center_y + (width/2) * cos(theta) * sin(angle) + (height/2) * sin(theta) * cos(angle)
                    
                    a = axes[0] / 2  # semi-major axis
                    b = axes[1] / 2  # semi-minor axis
                    angle_rad = np.deg2rad(angle)
                    
                    x = center[0] + a * np.cos(theta) * np.cos(angle_rad) - b * np.sin(theta) * np.sin(angle_rad)
                    y = center[1] + a * np.cos(theta) * np.sin(angle_rad) + b * np.sin(theta) * np.cos(angle_rad)
                    
                    sampled_points.append((float(x), float(y)))
                
                result[ring_name] = sampled_points
                
                logger.debug(
                    f"{ring_name} detected: center=({center[0]:.1f}, {center[1]:.1f}), "
                    f"axes=({axes[0]:.1f}, {axes[1]:.1f}), angle={angle:.1f}°, "
                    f"sampled_points={len(sampled_points)}"
                )
                
            except cv2.error as e:
                logger.debug(f"Failed to fit ellipse for {ring_name}: {e}")
                continue
        
        return result
    
    def detect_radial_wires(
        self, 
        image: np.ndarray, 
        bull_center: tuple[float, float]
    ) -> list[RadialWire]:
        """
        Detect radial wires using Hough line detection.
        
        Radial wires are the 20 lines extending from the bull to the double ring,
        separating the scoring sectors. This method uses HoughLinesP to detect
        line segments, filters them to find lines passing near the bull center,
        and clusters them by angle.
        
        Args:
            image: Input image (BGR, 8-bit)
            bull_center: (u, v) pixel coordinates of bull center
        
        Returns:
            List of detected RadialWire objects
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply Canny edge detection
        edges = cv2.Canny(gray, self.canny_threshold_low, self.canny_threshold_high)
        
        # Use HoughLinesP to detect line segments
        lines = cv2.HoughLinesP(
            edges,
            rho=1,  # Distance resolution in pixels
            theta=np.pi / 180,  # Angle resolution in radians (1 degree)
            threshold=30,  # Lowered from 50 for more sensitivity
            minLineLength=30,  # Lowered from 50 to detect shorter wire segments
            maxLineGap=15  # Increased from 10 to bridge gaps in wires
        )
        
        if lines is None or len(lines) == 0:
            logger.debug("No lines detected by HoughLinesP")
            return []
        
        bull_u, bull_v = bull_center
        
        # Filter lines that pass near bull center and are roughly radial
        candidate_wires = []
        
        for line in lines:
            x1, y1, x2, y2 = line[0]
            
            # Compute distance from bull center to line
            # Using point-to-line distance formula
            line_length = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            if line_length < 1:
                continue
            
            # Distance from point (bull_u, bull_v) to line through (x1, y1) and (x2, y2)
            dist_to_bull = abs((x2 - x1) * (y1 - bull_v) - (x1 - bull_u) * (y2 - y1)) / line_length
            
            # Filter: line must pass near bull center (within 30 pixels, increased tolerance)
            if dist_to_bull > 30:
                continue
            
            # Compute line angle relative to bull center
            # Use midpoint of line segment
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            
            # Angle from bull to line midpoint (in degrees, 0° = right, 90° = up)
            angle_to_midpoint = np.degrees(np.arctan2(bull_v - mid_y, mid_x - bull_u))
            
            # Compute line's own angle
            line_angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            
            # Check if line is roughly radial (angle from bull matches line angle)
            # Allow 30° tolerance for perspective distortion
            angle_diff = abs(angle_to_midpoint - line_angle)
            # Normalize to [0, 180] since lines are bidirectional
            angle_diff = min(angle_diff, 180 - angle_diff)
            
            if angle_diff > 30 and angle_diff < 150:  # Not radial (should be ~0° or ~180°)
                continue
            
            # Convert angle to "from vertical" (0° = pointing up from bull)
            # Standard math: 0° = right, 90° = up
            # We want: 0° = up, 90° = right
            angle_from_vertical = 90 - angle_to_midpoint
            # Normalize to [0, 360)
            angle_from_vertical = angle_from_vertical % 360
            
            # Compute confidence based on line length and distance to bull
            confidence = line_length / (1 + dist_to_bull)
            
            candidate_wires.append({
                'angle': angle_from_vertical,
                'endpoints': ((float(x1), float(y1)), (float(x2), float(y2))),
                'confidence': confidence,
                'dist_to_bull': dist_to_bull
            })
        
        logger.debug(f"Found {len(candidate_wires)} candidate radial wires")
        
        if not candidate_wires:
            return []
        
        # Cluster lines by angle (18° sectors for 20 wires)
        sector_width = 18.0  # degrees
        clusters = {}
        
        for wire in candidate_wires:
            # Determine which sector this wire belongs to
            # Normalize angle to handle 0°/360° boundary
            angle = wire['angle']
            sector = int(angle / sector_width) % 20  # Ensure sector is in [0, 19]
            
            if sector not in clusters:
                clusters[sector] = []
            clusters[sector].append(wire)
        
        # For each cluster, select the strongest line
        radial_wires = []
        
        for sector, wires in clusters.items():
            # Select wire with highest confidence
            best_wire = max(wires, key=lambda w: w['confidence'])
            
            radial_wires.append(RadialWire(
                angle=best_wire['angle'],
                endpoints=best_wire['endpoints'],
                confidence=best_wire['confidence']
            ))
        
        logger.debug(
            f"Detected {len(radial_wires)} radial wires after clustering "
            f"(from {len(candidate_wires)} candidates)"
        )
        
        return radial_wires
    
    def find_wire_intersections(
        self, 
        ring_edges: dict[str, list[tuple[float, float]]], 
        radial_wires: list[RadialWire]
    ) -> list[WireIntersection]:
        """
        Find intersections between radial wires and ring edges.
        
        Computes where each detected radial wire crosses the double and triple
        ring edges. These intersections serve as correspondence points for
        homography computation.
        
        Args:
            ring_edges: Dictionary with 'double_ring' and 'triple_ring' point lists
            radial_wires: List of detected RadialWire objects
        
        Returns:
            List of WireIntersection objects
        """
        intersections = []
        
        if not radial_wires:
            logger.debug("No radial wires provided for intersection finding")
            return intersections
        
        # Process each radial wire
        for wire_index, wire in enumerate(radial_wires):
            # Extract wire endpoints
            (x1, y1), (x2, y2) = wire.endpoints
            
            # For each ring type (double and triple)
            for ring_type in ['double_ring', 'triple_ring']:
                if ring_type not in ring_edges or not ring_edges[ring_type]:
                    continue
                
                # Find intersection between wire line and ring edge
                intersection = self._line_ring_intersection(
                    (x1, y1, x2, y2), 
                    ring_edges[ring_type]
                )
                
                if intersection is not None:
                    # Estimate sector based on wire angle
                    sector_estimate = self._estimate_sector_from_angle(wire.angle)
                    
                    intersections.append(WireIntersection(
                        pixel=intersection,
                        ring_type=ring_type,
                        wire_index=wire_index,
                        sector_estimate=sector_estimate
                    ))
                    
                    logger.debug(
                        f"Wire {wire_index} (angle={wire.angle:.1f}°) intersects {ring_type} "
                        f"at ({intersection[0]:.1f}, {intersection[1]:.1f}), sector={sector_estimate}"
                    )
        
        logger.debug(f"Found {len(intersections)} wire-ring intersections")
        return intersections
    
    def _line_ring_intersection(
        self, 
        line: tuple[float, float, float, float], 
        ring_points: list[tuple[float, float]]
    ) -> Optional[tuple[float, float]]:
        """
        Find the intersection between a line and a ring edge.
        
        The ring edge is represented as a list of sampled points along an ellipse.
        This method finds the point on the ring that is closest to the line.
        
        Args:
            line: Line segment as (x1, y1, x2, y2)
            ring_points: List of (x, y) points along the ring edge
        
        Returns:
            (x, y) intersection point, or None if no intersection found
        """
        if not ring_points:
            return None
        
        x1, y1, x2, y2 = line
        
        # Extend the line segment to a full line for intersection testing
        # Compute line direction vector
        dx = x2 - x1
        dy = y2 - y1
        line_length = np.sqrt(dx**2 + dy**2)
        
        if line_length < 1:
            return None
        
        # Normalize direction
        dx /= line_length
        dy /= line_length
        
        # Find ring points closest to the line
        # We'll find the point with minimum distance to the line
        min_dist = float('inf')
        closest_point = None
        
        for px, py in ring_points:
            # Distance from point (px, py) to line through (x1, y1) with direction (dx, dy)
            # Using point-to-line distance formula
            # Vector from line point to ring point
            vx = px - x1
            vy = py - y1
            
            # Project onto line direction to get closest point on line
            t = vx * dx + vy * dy
            
            # Closest point on line
            closest_x = x1 + t * dx
            closest_y = y1 + t * dy
            
            # Distance from ring point to closest point on line
            dist = np.sqrt((px - closest_x)**2 + (py - closest_y)**2)
            
            if dist < min_dist:
                min_dist = dist
                closest_point = (px, py)
        
        # Only return intersection if it's reasonably close to the line (within 10 pixels)
        if min_dist < 10 and closest_point is not None:
            return (float(closest_point[0]), float(closest_point[1]))
        
        return None
    
    def _estimate_sector_from_angle(self, angle: float) -> int:
        """
        Estimate the sector number (1-20) from a wire angle.
        
        Sector 20 is at the top (0° from vertical). Sectors are numbered
        clockwise: 20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5.
        
        Args:
            angle: Angle in degrees from vertical (0° = pointing up)
        
        Returns:
            Estimated sector number (1-20)
        """
        # Sector order (clockwise from top)
        sector_order = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
        
        # Each sector spans 18 degrees
        sector_width = 18.0
        
        # Normalize angle to [0, 360)
        angle = angle % 360
        
        # Determine which sector index (0-19) this angle falls into
        # Sector 0 (which is sector 20) is centered at 0°, so it spans [-9°, 9°]
        # We need to offset by half a sector width
        adjusted_angle = (angle + sector_width / 2) % 360
        sector_index = int(adjusted_angle / sector_width) % 20
        
        # Map sector index to actual sector number
        sector_number = sector_order[sector_index]
        
        return sector_number
