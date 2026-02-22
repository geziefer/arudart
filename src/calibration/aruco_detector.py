"""
ArucoDetector class for detecting ARUCO markers in camera images.

Provides marker detection and corner extraction for extrinsic calibration.
Uses DICT_4X4_50 dictionary by default (4x4 bits, 50 unique markers).

Requirements: AC-6.2.5, AC-6.3.1
"""

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ArucoDetector:
    """
    Detect ARUCO markers in camera images and extract corner coordinates.
    
    Used for extrinsic calibration to establish correspondence between
    image coordinates and board coordinates.
    
    Attributes:
        config: Configuration dictionary with marker positions
        dictionary: ARUCO dictionary for marker detection
        detector_params: Detection parameters for cv2.aruco
    """
    
    # Valid marker IDs for dartboard calibration (0-5)
    VALID_MARKER_IDS = set(range(6))
    
    # Minimum markers required for homography computation
    MIN_MARKERS_REQUIRED = 4
    
    def __init__(self, config: dict, dictionary_id: int = cv2.aruco.DICT_4X4_50):
        """
        Initialize ARUCO detector.
        
        Args:
            config: Configuration dictionary with marker positions
            dictionary_id: ARUCO dictionary to use (DICT_4X4_50 default)
        """
        self.config = config
        self.dictionary_id = dictionary_id
        
        # Initialize ARUCO dictionary
        self.dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
        
        # Initialize detector parameters with defaults
        self.detector_params = cv2.aruco.DetectorParameters()
        
        # Create detector (OpenCV 4.7+ API)
        self.detector = cv2.aruco.ArucoDetector(self.dictionary, self.detector_params)
        
        # Get expected marker size from config (for validation)
        aruco_config = config.get('calibration', {}).get('aruco', {})
        self.expected_marker_size_mm = aruco_config.get('marker_size_mm', 40.0)
        
        logger.debug(f"ArucoDetector initialized with dictionary {dictionary_id}")
    
    def detect_markers(self, image: np.ndarray) -> dict[int, np.ndarray]:
        """
        Detect ARUCO markers in image.
        
        Args:
            image: Input image (BGR or grayscale)
        
        Returns:
            Dictionary mapping marker_id → corners
            corners: 4×2 array of corner coordinates [top-left, top-right, bottom-right, bottom-left]
            Returns empty dict if no markers detected or detection fails.
            
        Example:
            {
                0: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]],  # Marker 0 corners
                1: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]],  # Marker 1 corners
                ...
            }
        """
        if image is None:
            logger.error("Cannot detect markers: image is None")
            return {}
        
        try:
            # Convert to grayscale if needed
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image
            
            # Detect markers using OpenCV 4.7+ API
            corners, ids, rejected = self.detector.detectMarkers(gray)
            
            # Build result dictionary
            detected_markers: dict[int, np.ndarray] = {}
            
            if ids is not None and len(ids) > 0:
                for i, marker_id in enumerate(ids.flatten()):
                    # Extract corners for this marker (4×2 array)
                    # corners[i] has shape (1, 4, 2), we want (4, 2)
                    marker_corners = corners[i].reshape(4, 2)
                    detected_markers[int(marker_id)] = marker_corners
                
                logger.debug(f"Detected {len(detected_markers)} markers: {list(detected_markers.keys())}")
            else:
                logger.debug("No markers detected in image")
            
            return detected_markers
            
        except cv2.error as e:
            logger.error(f"OpenCV error during marker detection: {e}")
            return {}
        except Exception as e:
            logger.exception(f"Unexpected error during marker detection: {e}")
            return {}
    
    def validate_markers(self, detected_markers: dict[int, np.ndarray]) -> bool:
        """
        Validate that required markers are detected.
        
        Checks:
        1. At least 4 markers detected (minimum for homography)
        2. Marker IDs are in valid range (0-5)
        
        Args:
            detected_markers: Dictionary from detect_markers()
        
        Returns:
            True if at least 4 markers detected with valid IDs
        """
        if not detected_markers:
            logger.warning("Validation failed: no markers detected")
            return False
        
        # Check number of markers
        num_markers = len(detected_markers)
        if num_markers < self.MIN_MARKERS_REQUIRED:
            logger.warning(
                f"Validation failed: only {num_markers} markers detected, "
                f"need at least {self.MIN_MARKERS_REQUIRED}"
            )
            return False
        
        # Check marker IDs are valid
        invalid_ids = set(detected_markers.keys()) - self.VALID_MARKER_IDS
        if invalid_ids:
            logger.warning(f"Validation warning: unexpected marker IDs detected: {invalid_ids}")
            # Don't fail validation for unexpected IDs, just warn
        
        # Validate corner arrays
        for marker_id, corners in detected_markers.items():
            if corners.shape != (4, 2):
                logger.warning(
                    f"Validation failed: marker {marker_id} has invalid corner shape "
                    f"{corners.shape}, expected (4, 2)"
                )
                return False
        
        logger.debug(f"Validation passed: {num_markers} valid markers detected")
        return True
    
    def draw_markers(
        self, 
        image: np.ndarray, 
        detected_markers: dict[int, np.ndarray],
        draw_ids: bool = True,
        draw_corners: bool = True
    ) -> np.ndarray:
        """
        Draw detected markers on image for visualization.
        
        Args:
            image: Input image (will be copied, not modified)
            detected_markers: Dictionary from detect_markers()
            draw_ids: Whether to draw marker IDs
            draw_corners: Whether to draw corner points
        
        Returns:
            Image with markers outlined and IDs labeled
        """
        if image is None:
            logger.error("Cannot draw markers: image is None")
            return image
        
        # Make a copy to avoid modifying original
        output = image.copy()
        
        if not detected_markers:
            return output
        
        # Colors for visualization
        outline_color = (0, 255, 0)  # Green
        id_color = (255, 0, 0)       # Blue (BGR)
        corner_colors = [
            (0, 0, 255),    # Red - top-left
            (0, 255, 255),  # Yellow - top-right
            (255, 0, 255),  # Magenta - bottom-right
            (255, 255, 0),  # Cyan - bottom-left
        ]
        
        for marker_id, corners in detected_markers.items():
            # Draw marker outline (polygon)
            pts = corners.astype(np.int32).reshape((-1, 1, 2))
            cv2.polylines(output, [pts], isClosed=True, color=outline_color, thickness=2)
            
            # Draw corner points
            if draw_corners:
                for i, (x, y) in enumerate(corners):
                    cv2.circle(output, (int(x), int(y)), 5, corner_colors[i], -1)
            
            # Draw marker ID
            if draw_ids:
                # Position ID text at center of marker
                center_x = int(np.mean(corners[:, 0]))
                center_y = int(np.mean(corners[:, 1]))
                
                # Draw background rectangle for better visibility
                text = f"ID:{marker_id}"
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.6
                thickness = 2
                (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
                
                # Background rectangle
                cv2.rectangle(
                    output,
                    (center_x - text_w // 2 - 2, center_y - text_h // 2 - 2),
                    (center_x + text_w // 2 + 2, center_y + text_h // 2 + 2),
                    (0, 0, 0),
                    -1
                )
                
                # Text
                cv2.putText(
                    output,
                    text,
                    (center_x - text_w // 2, center_y + text_h // 2),
                    font,
                    font_scale,
                    id_color,
                    thickness
                )
        
        return output
    
    def get_marker_center(self, corners: np.ndarray) -> tuple[float, float]:
        """
        Get the center point of a marker from its corners.
        
        Args:
            corners: 4×2 array of corner coordinates
        
        Returns:
            (x, y) center coordinates
        """
        center_x = float(np.mean(corners[:, 0]))
        center_y = float(np.mean(corners[:, 1]))
        return center_x, center_y
    
    def get_marker_size_pixels(self, corners: np.ndarray) -> float:
        """
        Estimate marker size in pixels from corner coordinates.
        
        Uses average of the four edge lengths.
        
        Args:
            corners: 4×2 array of corner coordinates
        
        Returns:
            Estimated marker size in pixels
        """
        # Calculate edge lengths
        edges = []
        for i in range(4):
            p1 = corners[i]
            p2 = corners[(i + 1) % 4]
            edge_length = np.linalg.norm(p2 - p1)
            edges.append(edge_length)
        
        return float(np.mean(edges))
    
    def get_diagnostic_info(
        self, 
        image: np.ndarray, 
        detected_markers: dict[int, np.ndarray]
    ) -> dict:
        """
        Get diagnostic information for troubleshooting detection issues.
        
        Args:
            image: Input image
            detected_markers: Dictionary from detect_markers()
        
        Returns:
            Dictionary with diagnostic information
        """
        info = {
            'num_markers_detected': len(detected_markers),
            'marker_ids': list(detected_markers.keys()),
            'validation_passed': self.validate_markers(detected_markers),
            'image_shape': image.shape if image is not None else None,
        }
        
        # Add per-marker info
        marker_info = {}
        for marker_id, corners in detected_markers.items():
            center = self.get_marker_center(corners)
            size_px = self.get_marker_size_pixels(corners)
            marker_info[marker_id] = {
                'center': center,
                'size_pixels': size_px,
                'corners': corners.tolist(),
            }
        info['markers'] = marker_info
        
        # Add suggestions if detection failed
        if not detected_markers:
            info['suggestions'] = [
                "Check lighting conditions (markers need good contrast)",
                "Ensure markers are not occluded",
                "Verify markers are flat and not damaged",
                "Check camera focus",
            ]
        elif len(detected_markers) < self.MIN_MARKERS_REQUIRED:
            info['suggestions'] = [
                f"Only {len(detected_markers)} markers detected, need at least {self.MIN_MARKERS_REQUIRED}",
                "Check if some markers are outside camera view",
                "Ensure all markers are visible and not occluded",
            ]
        
        return info
