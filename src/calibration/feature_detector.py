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
class SectorBoundary:
    """Represents a detected sector boundary on the dartboard."""
    angle: float  # degrees from vertical (0° = sector 20 at top)
    sector: int  # sector number (1-20)
    edge_points: list[tuple[float, float]]  # color transition points
    confidence: float  # detection confidence score


@dataclass
class BoundaryIntersection:
    """Represents an intersection between a sector boundary and a ring edge."""
    pixel: tuple[float, float]  # (u, v) pixel coordinates
    ring_type: str  # 'double_ring' or 'triple_ring'
    sector: int  # sector number (1-20)
    confidence: float  # detection confidence score


@dataclass
class FeatureDetectionResult:
    """Result of dartboard feature detection."""
    bull_center: Optional[tuple[float, float]]  # (u, v) pixel coordinates, None if not detected
    ring_edges: dict[str, list[tuple[float, float]]]  # 'double_ring', 'triple_ring' -> list of (u, v) points
    sector_boundaries: list[SectorBoundary]  # detected sector boundaries via color
    boundary_intersections: list[BoundaryIntersection]  # boundary-ring intersections
    detection_time_ms: float  # time taken for detection
    error: Optional[str] = None  # error message if detection failed


class FeatureDetector:
    """
    Detects dartboard features (bull, rings, sector boundaries) for calibration.
    
    Uses computer vision techniques to identify the dartboard's natural geometry:
    - Bull center: Colored circle at board center (red/green), fitted as ellipse
    - Ring edges: Double ring (170mm) and triple ring (107mm) as ellipses
    - Sector boundaries: Detected via color transitions (black/white in singles, red/green in rings)
    - Boundary intersections: Points where sector boundaries cross ring edges
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
        
        # Load HSV color ranges
        self.black_singles_range = (
            (feature_config.get('black_singles_h_min', 0), feature_config.get('black_singles_s_min', 0), feature_config.get('black_singles_v_min', 0)),
            (feature_config.get('black_singles_h_max', 180), feature_config.get('black_singles_s_max', 50), feature_config.get('black_singles_v_max', 80))
        )
        self.white_singles_range = (
            (feature_config.get('white_singles_h_min', 0), feature_config.get('white_singles_s_min', 0), feature_config.get('white_singles_v_min', 150)),
            (feature_config.get('white_singles_h_max', 180), feature_config.get('white_singles_s_max', 50), feature_config.get('white_singles_v_max', 255))
        )
        self.red_ring_range_1 = (
            (feature_config.get('red_ring_h_min_1', 0), feature_config.get('red_ring_s_min', 100), feature_config.get('red_ring_v_min', 100)),
            (feature_config.get('red_ring_h_max_1', 10), feature_config.get('red_ring_s_max', 255), feature_config.get('red_ring_v_max', 255))
        )
        self.red_ring_range_2 = (
            (feature_config.get('red_ring_h_min_2', 170), feature_config.get('red_ring_s_min', 100), feature_config.get('red_ring_v_min', 100)),
            (feature_config.get('red_ring_h_max_2', 180), feature_config.get('red_ring_s_max', 255), feature_config.get('red_ring_v_max', 255))
        )
        self.green_ring_range = (
            (feature_config.get('green_ring_h_min', 40), feature_config.get('green_ring_s_min', 100), feature_config.get('green_ring_v_min', 100)),
            (feature_config.get('green_ring_h_max', 80), feature_config.get('green_ring_s_max', 255), feature_config.get('green_ring_v_max', 255))
        )
        
        self.min_boundary_edge_points = feature_config.get('min_boundary_edge_points', 10)
        self.boundary_clustering_angle_deg = feature_config.get('boundary_clustering_angle_deg', 2.0)
        
        logger.info(
            f"FeatureDetector initialized: bull_radius=[{self.bull_min_radius_px}, {self.bull_max_radius_px}], "
            f"canny=[{self.canny_threshold_low}, {self.canny_threshold_high}]"
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
        
        # Detect sector boundaries using color segmentation
        sector_boundaries = self.detect_sector_boundaries(image, bull_center)
        
        # Find boundary-ring intersections
        boundary_intersections = self.find_boundary_intersections(ring_edges, sector_boundaries, bull_center)
        
        detection_time_ms = (time.time() - start_time) * 1000
        
        # Check if we have sufficient features for calibration
        num_boundaries = len(sector_boundaries)
        num_intersections = len(boundary_intersections)
        
        if num_boundaries < 8:
            logger.warning(
                f"Insufficient sector boundaries detected: {num_boundaries} < 8 minimum"
            )
            return FeatureDetectionResult(
                bull_center=bull_center,
                ring_edges=ring_edges,
                sector_boundaries=sector_boundaries,
                boundary_intersections=boundary_intersections,
                detection_time_ms=detection_time_ms,
                error="INSUFFICIENT_BOUNDARIES"
            )
        
        if num_intersections < 4:
            logger.warning(
                f"Insufficient boundary intersections detected: {num_intersections} < 4 minimum"
            )
            return FeatureDetectionResult(
                bull_center=bull_center,
                ring_edges=ring_edges,
                sector_boundaries=sector_boundaries,
                boundary_intersections=boundary_intersections,
                detection_time_ms=detection_time_ms,
                error="INSUFFICIENT_FEATURES"
            )
        
        logger.info(
            f"Feature detection complete: bull={bull_center is not None}, "
            f"double_ring_pts={len(ring_edges.get('double_ring', []))}, "
            f"triple_ring_pts={len(ring_edges.get('triple_ring', []))}, "
            f"boundaries={num_boundaries}, intersections={num_intersections}, "
            f"time={detection_time_ms:.1f}ms"
        )
        
        return FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges=ring_edges,
            sector_boundaries=sector_boundaries,
            boundary_intersections=boundary_intersections,
            detection_time_ms=detection_time_ms
        )
    
    def detect_bull_center(self, image: np.ndarray) -> Optional[tuple[float, float]]:
        """
        Detect the bull center using multiple strategies with strict validation.
        
        Strategy priority:
        1. Geometric center from line intersections (most reliable)
        2. Hough circles with strict color validation
        3. Color-based detection as last resort
        
        The bull MUST have both red and green colors (double bull + single bull).
        
        Args:
            image: Input image (BGR, 8-bit)
        
        Returns:
            (u, v) pixel coordinates of bull center, or None if not detected
        """
        image_center = (image.shape[1] / 2, image.shape[0] / 2)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Strategy 1: Find geometric center from line intersections
        # This is the most reliable - all sector boundaries converge at the bull
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, self.canny_threshold_low, self.canny_threshold_high)
        
        # Detect lines (sector boundaries)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi/180,
            threshold=50,
            minLineLength=50,
            maxLineGap=10
        )
        
        if lines is not None and len(lines) > 10:
            # Find intersection points
            intersections = []
            for i in range(min(len(lines), 50)):  # Limit to first 50 lines for performance
                for j in range(i+1, min(len(lines), 50)):
                    x1, y1, x2, y2 = lines[i][0]
                    x3, y3, x4, y4 = lines[j][0]
                    
                    denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
                    if abs(denom) < 1e-6:
                        continue
                    
                    t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
                    ix = x1 + t*(x2-x1)
                    iy = y1 + t*(y2-y1)
                    
                    # Only consider intersections near image center
                    if 0 <= ix < image.shape[1] and 0 <= iy < image.shape[0]:
                        dist = np.sqrt((ix - image_center[0])**2 + (iy - image_center[1])**2)
                        if dist < 150:  # Within 150 pixels of image center
                            intersections.append((ix, iy))
            
            if len(intersections) > 20:
                # Find the densest cluster of intersections
                intersections = np.array(intersections)
                
                # Use median (more robust than mean)
                center_x = np.median(intersections[:, 0])
                center_y = np.median(intersections[:, 1])
                
                # Verify this is the bull by checking for red AND green colors
                if self._verify_bull_colors(hsv, center_x, center_y, radius=25):
                    logger.debug(
                        f"Bull center detected via line intersections: ({center_x:.2f}, {center_y:.2f})"
                    )
                    return (float(center_x), float(center_y))
                else:
                    logger.debug(
                        f"Line intersection center ({center_x:.1f}, {center_y:.1f}) "
                        f"rejected: insufficient bull colors"
                    )
        
        # Strategy 2: Hough circles with STRICT color validation
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=50,
            param1=100,
            param2=15,
            minRadius=8,
            maxRadius=35
        )
        
        if circles is not None:
            circles = np.round(circles[0, :]).astype("int")
            
            # Sort by distance from image center
            circles_with_dist = []
            for (x, y, r) in circles:
                dist = np.sqrt((x - image_center[0])**2 + (y - image_center[1])**2)
                if dist < 150:  # Must be near image center
                    circles_with_dist.append((x, y, r, dist))
            
            circles_with_dist.sort(key=lambda c: c[3])  # Sort by distance
            
            # Try each circle, starting with closest to center
            for x, y, r, dist in circles_with_dist:
                # STRICT validation: must have BOTH red and green colors
                if self._verify_bull_colors(hsv, x, y, radius=int(r * 1.5)):
                    logger.debug(
                        f"Bull center detected via Hough circles: ({x}, {y}), "
                        f"radius={r}px, dist_from_center={dist:.1f}px"
                    )
                    return (float(x), float(y))
            
            logger.debug("Hough circles found but none passed color validation")
        
        # Strategy 3: Color-based detection (last resort)
        logger.debug("Geometric and Hough methods failed, trying color-based detection")
        
        # Create masks for bull colors
        red_mask1 = cv2.inRange(hsv, np.array(self.red_ring_range_1[0]), np.array(self.red_ring_range_1[1]))
        red_mask2 = cv2.inRange(hsv, np.array(self.red_ring_range_2[0]), np.array(self.red_ring_range_2[1]))
        red_mask = cv2.bitwise_or(red_mask1, red_mask2)
        
        green_mask = cv2.inRange(hsv, np.array(self.green_ring_range[0]), np.array(self.green_ring_range[1]))
        
        # Bull must have BOTH red and green
        bull_mask = cv2.bitwise_and(red_mask, green_mask)
        
        # Clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        bull_mask = cv2.morphologyEx(bull_mask, cv2.MORPH_CLOSE, kernel)
        bull_mask = cv2.morphologyEx(bull_mask, cv2.MORPH_OPEN, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(bull_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            logger.debug("No contours found with both red and green colors")
            return None
        
        # Find smallest contour near image center
        min_area = np.pi * self.bull_min_radius_px ** 2
        max_area = np.pi * self.bull_max_radius_px ** 2 * 4
        
        best_contour = None
        best_score = float('inf')
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue
            
            M = cv2.moments(contour)
            if M['m00'] > 0:
                cx = M['m10'] / M['m00']
                cy = M['m01'] / M['m00']
                dist = np.sqrt((cx - image_center[0])**2 + (cy - image_center[1])**2)
                
                if dist > 150:
                    continue
                
                # Score: prefer small + close to center
                score = (area / max_area) + (dist / 150)
                
                if score < best_score:
                    best_score = score
                    best_contour = {'center': (cx, cy), 'contour': contour, 'area': area}
        
        if best_contour is None:
            logger.debug("No suitable contours found in color-based detection")
            return None
        
        logger.debug(
            f"Bull center detected via color mask: ({best_contour['center'][0]:.2f}, "
            f"{best_contour['center'][1]:.2f}), area={best_contour['area']:.1f}px²"
        )
        
        return best_contour['center']
    
    def _verify_bull_colors(self, hsv: np.ndarray, x: float, y: float, radius: int) -> bool:
        """
        Verify that a point is the bull by checking for BOTH red and green colors.
        
        Args:
            hsv: HSV image
            x, y: Center point to check
            radius: Radius around point to sample
        
        Returns:
            True if both red and green colors are present (indicating bull)
        """
        # Sample region around point
        y1 = max(0, int(y) - radius)
        y2 = min(hsv.shape[0], int(y) + radius)
        x1 = max(0, int(x) - radius)
        x2 = min(hsv.shape[1], int(x) + radius)
        
        if y2 <= y1 or x2 <= x1:
            return False
        
        roi = hsv[y1:y2, x1:x2]
        
        # Check for red
        red_mask1 = cv2.inRange(roi, np.array([0, 80, 80]), np.array([15, 255, 255]))
        red_mask2 = cv2.inRange(roi, np.array([165, 80, 80]), np.array([180, 255, 255]))
        red_mask = cv2.bitwise_or(red_mask1, red_mask2)
        red_pixels = np.sum(red_mask > 0)
        
        # Check for green
        green_mask = cv2.inRange(roi, np.array([35, 80, 80]), np.array([85, 255, 255]))
        green_pixels = np.sum(green_mask > 0)
        
        total_pixels = roi.shape[0] * roi.shape[1]
        
        # Bull must have BOTH red and green (at least 3% each)
        red_ratio = red_pixels / total_pixels
        green_ratio = green_pixels / total_pixels
        
        has_both = red_ratio > 0.03 and green_ratio > 0.03
        
        logger.debug(
            f"Color verification at ({x:.1f}, {y:.1f}): "
            f"red={red_ratio:.1%}, green={green_ratio:.1%}, valid={has_both}"
        )
        
        return has_both
    
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
    
    def detect_sector_boundaries(
        self, 
        image: np.ndarray, 
        bull_center: tuple[float, float]
    ) -> list[SectorBoundary]:
        """
        Detect sector boundaries using color segmentation.
        
        Detects boundaries between dartboard sectors by finding color transitions:
        - Black/white transitions in singles regions
        - Red/green transitions in ring regions
        
        Args:
            image: Input image (BGR, 8-bit)
            bull_center: (u, v) pixel coordinates of bull center
        
        Returns:
            List of detected SectorBoundary objects with angles and sector numbers
        """
        # Convert to HSV color space for better color segmentation
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        bull_u, bull_v = bull_center
        
        # Use edge detection on grayscale to find strong boundaries
        # This is more reliable than pure color segmentation
        edges = cv2.Canny(gray, self.canny_threshold_low, self.canny_threshold_high)
        
        # Create annular mask for singles region (between triple and double rings)
        # Approximate radii based on typical camera setup
        mask = np.zeros(edges.shape, dtype=np.uint8)
        cv2.circle(mask, (int(bull_u), int(bull_v)), 270, 255, -1)  # Outer boundary
        cv2.circle(mask, (int(bull_u), int(bull_v)), 140, 0, -1)   # Inner boundary (exclude triple ring)
        
        # Apply mask to edges
        masked_edges = cv2.bitwise_and(edges, mask)
        
        # Find edge points
        edge_points = np.column_stack(np.where(masked_edges > 0))
        
        if len(edge_points) == 0:
            logger.debug("No edge points detected in singles region")
            return []
        
        # Convert from (row, col) to (x, y) and compute angles from bull center
        transition_data = []
        for row, col in edge_points:
            x, y = float(col), float(row)
            
            # Compute angle from bull center (0° = up, clockwise)
            dx = x - bull_u
            dy = bull_v - y  # Invert Y for standard coordinate system
            angle = np.degrees(np.arctan2(dx, dy))  # atan2(x, y) gives angle from vertical
            if angle < 0:
                angle += 360
            
            # Compute distance from bull
            dist = np.sqrt(dx**2 + dy**2)
            
            # Only include points in the singles region
            if 140 < dist < 270:
                transition_data.append({
                    'point': (x, y),
                    'angle': angle,
                    'distance': dist
                })
        
        logger.debug(f"Found {len(edge_points)} edge points, {len(transition_data)} in singles region")
        
        if len(transition_data) < 100:
            logger.debug(f"Insufficient transition points: {len(transition_data)} < 100 minimum")
            return []
        
        # Cluster transition points by angle (18° sectors for 20 boundaries)
        # Use histogram to find peaks in angular distribution
        angles = np.array([d['angle'] for d in transition_data])
        
        # Create histogram with 360 bins (1° per bin)
        hist, bin_edges = np.histogram(angles, bins=360, range=(0, 360))
        
        # Smooth histogram to reduce noise (simple moving average, no scipy needed)
        window_size = 5
        hist_smooth = np.convolve(hist.astype(float), np.ones(window_size)/window_size, mode='same')
        
        # Find peaks in histogram (these are potential sector boundaries)
        # Simple peak detection: local maxima above threshold
        # Start with 75th percentile, but lower if we don't find enough peaks
        threshold_percentile = 75
        min_distance = 10  # Minimum distance between peaks in bins
        
        logger.debug(
            f"Histogram stats: max={hist.max()}, mean={hist.mean():.1f}, "
            f"median={np.median(hist):.1f}, num_angles={len(angles)}"
        )
        
        # Try progressively lower thresholds until we find enough peaks
        for attempt_percentile in [75, 70, 65, 60, 55, 50]:
            threshold = np.percentile(hist_smooth, attempt_percentile)
            
            peaks = []
            for i in range(min_distance, len(hist_smooth) - min_distance):
                # Check if this is a local maximum
                if hist_smooth[i] > threshold:
                    # Check if it's higher than neighbors within min_distance
                    is_peak = True
                    for j in range(i - min_distance, i + min_distance + 1):
                        if j != i and hist_smooth[j] >= hist_smooth[i]:
                            is_peak = False
                            break
                    
                    if is_peak:
                        peaks.append(i)
            
            logger.debug(
                f"Attempt {attempt_percentile}th percentile: threshold={threshold:.1f}, "
                f"found {len(peaks)} peaks"
            )
            
            # If we found enough peaks, stop
            if len(peaks) >= 8:
                break
        
        if len(peaks) < 8:
            logger.debug(f"Insufficient peaks found: {len(peaks)} < 8 (threshold={threshold:.1f})")
            return []
        
        # Create sector boundaries from peaks
        sector_boundaries = []
        
        for peak_idx in peaks:
            peak_angle = bin_edges[peak_idx]
            
            # Get all transition points near this angle (±5°)
            angle_tolerance = 5.0
            nearby_points = [
                d for d in transition_data 
                if abs(d['angle'] - peak_angle) < angle_tolerance or 
                   abs(d['angle'] - peak_angle - 360) < angle_tolerance or
                   abs(d['angle'] - peak_angle + 360) < angle_tolerance
            ]
            
            if len(nearby_points) < self.min_boundary_edge_points:
                continue
            
            # Compute mean angle for this boundary
            nearby_angles = [d['angle'] for d in nearby_points]
            mean_angle = np.mean(nearby_angles)
            
            # Get edge points
            edge_points = [d['point'] for d in nearby_points]
            
            # Compute confidence based on number of points and peak height
            confidence = len(nearby_points) * hist_smooth[peak_idx] / 100.0
            
            # Estimate sector number from angle
            sector = self._estimate_sector_from_boundary_angle(mean_angle)
            
            sector_boundaries.append(SectorBoundary(
                angle=mean_angle,
                sector=sector,
                edge_points=edge_points,
                confidence=confidence
            ))
        
        logger.debug(
            f"Detected {len(sector_boundaries)} sector boundaries "
            f"(from {len(transition_data)} transition points, {len(peaks)} peaks)"
        )
        
        return sector_boundaries
    
    def _merge_nearby_boundaries(
        self, 
        boundaries: list[SectorBoundary], 
        sector_width: float
    ) -> list[SectorBoundary]:
        """
        Merge sector boundaries that are too close together.
        
        Args:
            boundaries: List of detected boundaries
            sector_width: Expected angular width of sectors (18°)
        
        Returns:
            List of merged boundaries
        """
        if not boundaries:
            return []
        
        # Sort by angle
        sorted_boundaries = sorted(boundaries, key=lambda b: b.angle)
        
        merged = []
        current_group = [sorted_boundaries[0]]
        
        for i in range(1, len(sorted_boundaries)):
            boundary = sorted_boundaries[i]
            prev_boundary = current_group[-1]
            
            # Check if this boundary is close to the previous one
            angle_diff = boundary.angle - prev_boundary.angle
            
            # Handle wrap-around at 360°
            if angle_diff > 180:
                angle_diff -= 360
            elif angle_diff < -180:
                angle_diff += 360
            
            if abs(angle_diff) < sector_width / 2:
                # Merge with current group
                current_group.append(boundary)
            else:
                # Start new group
                if current_group:
                    merged.append(self._merge_boundary_group(current_group))
                current_group = [boundary]
        
        # Don't forget the last group
        if current_group:
            merged.append(self._merge_boundary_group(current_group))
        
        return merged
    
    def _merge_boundary_group(self, group: list[SectorBoundary]) -> SectorBoundary:
        """
        Merge a group of nearby boundaries into a single boundary.
        
        Args:
            group: List of boundaries to merge
        
        Returns:
            Merged SectorBoundary
        """
        if len(group) == 1:
            return group[0]
        
        # Weighted average of angles by confidence
        total_confidence = sum(b.confidence for b in group)
        mean_angle = sum(b.angle * b.confidence for b in group) / total_confidence
        
        # Combine edge points
        all_edge_points = []
        for b in group:
            all_edge_points.extend(b.edge_points)
        
        # Use most common sector number
        sectors = [b.sector for b in group]
        sector = max(set(sectors), key=sectors.count)
        
        return SectorBoundary(
            angle=mean_angle,
            sector=sector,
            edge_points=all_edge_points,
            confidence=total_confidence / len(group)
        )
    
    def _estimate_sector_from_boundary_angle(self, angle: float) -> int:
        """
        Estimate sector number from boundary angle.
        
        The boundary is between two sectors. We assign it to the sector
        on the clockwise side of the boundary.
        
        Args:
            angle: Angle in degrees from vertical (0° = up, clockwise)
        
        Returns:
            Estimated sector number (1-20)
        """
        # Sector order (clockwise from top)
        sector_order = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
        
        # Each sector spans 18 degrees
        sector_width = 18.0
        
        # Normalize angle to [0, 360)
        angle = angle % 360
        
        # Boundaries are at sector edges, so we need to determine which sector
        # The boundary at 0° is between sectors 5 and 20
        # The boundary at 18° is between sectors 20 and 1
        # etc.
        
        # Determine which boundary index (0-19) this angle represents
        boundary_index = int((angle + sector_width / 2) / sector_width) % 20
        
        # The sector on the clockwise side of this boundary
        sector_number = sector_order[boundary_index]
        
        return sector_number
    
    def find_boundary_intersections(
        self, 
        ring_edges: dict[str, list[tuple[float, float]]], 
        sector_boundaries: list[SectorBoundary],
        bull_center: tuple[float, float]
    ) -> list[BoundaryIntersection]:
        """
        Find intersections between sector boundaries and ring edges.
        
        Args:
            ring_edges: Dictionary with 'double_ring' and 'triple_ring' point lists
            sector_boundaries: List of detected SectorBoundary objects
            bull_center: (u, v) pixel coordinates of bull center
        
        Returns:
            List of BoundaryIntersection objects
        """
        intersections = []
        
        if not sector_boundaries:
            logger.debug("No sector boundaries provided for intersection finding")
            return intersections
        
        bull_u, bull_v = bull_center
        
        # Process each sector boundary
        for boundary in sector_boundaries:
            # Boundary is defined by an angle from bull center
            angle_rad = np.radians(boundary.angle)
            
            # Direction vector for this boundary (from bull center outward)
            dx = np.sin(angle_rad)  # sin because 0° = up
            dy = -np.cos(angle_rad)  # -cos because Y increases downward
            
            # For each ring type (double and triple)
            for ring_type in ['double_ring', 'triple_ring']:
                if ring_type not in ring_edges or not ring_edges[ring_type]:
                    continue
                
                # Find intersection between boundary ray and ring edge
                intersection = self._ray_ring_intersection(
                    bull_center, 
                    (dx, dy), 
                    ring_edges[ring_type]
                )
                
                if intersection is not None:
                    intersections.append(BoundaryIntersection(
                        pixel=intersection,
                        ring_type=ring_type,
                        sector=boundary.sector,
                        confidence=boundary.confidence
                    ))
                    
                    logger.debug(
                        f"Boundary at {boundary.angle:.1f}° (sector {boundary.sector}) intersects {ring_type} "
                        f"at ({intersection[0]:.1f}, {intersection[1]:.1f})"
                    )
        
        logger.debug(f"Found {len(intersections)} boundary-ring intersections")
        return intersections
    
    def _ray_ring_intersection(
        self, 
        origin: tuple[float, float],
        direction: tuple[float, float],
        ring_points: list[tuple[float, float]]
    ) -> Optional[tuple[float, float]]:
        """
        Find intersection between a ray and a ring edge.
        
        Args:
            origin: Ray origin (bull center)
            direction: Ray direction vector (dx, dy)
            ring_points: List of (x, y) points along the ring edge
        
        Returns:
            (x, y) intersection point, or None if no intersection found
        """
        if not ring_points:
            return None
        
        ox, oy = origin
        dx, dy = direction
        
        # Normalize direction
        length = np.sqrt(dx**2 + dy**2)
        if length < 1e-6:
            return None
        dx /= length
        dy /= length
        
        # Find ring point closest to the ray
        min_dist = float('inf')
        closest_point = None
        
        for px, py in ring_points:
            # Vector from origin to ring point
            vx = px - ox
            vy = py - oy
            
            # Project onto ray direction
            t = vx * dx + vy * dy
            
            # Only consider points in front of the ray (t > 0)
            if t < 0:
                continue
            
            # Closest point on ray
            closest_x = ox + t * dx
            closest_y = oy + t * dy
            
            # Distance from ring point to ray
            dist = np.sqrt((px - closest_x)**2 + (py - closest_y)**2)
            
            if dist < min_dist:
                min_dist = dist
                closest_point = (px, py)
        
        # Only return intersection if it's reasonably close to the ray (within 10 pixels)
        if min_dist < 10 and closest_point is not None:
            return (float(closest_point[0]), float(closest_point[1]))
        
        return None
