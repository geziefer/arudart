"""
ExtrinsicCalibrator class for computing homography transformation.

Uses ARUCO markers to compute homography from camera image plane to board plane.
Implements AC-6.3.1, AC-6.3.2, AC-6.3.3, AC-6.3.6 from Step 6 requirements.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from src.calibration.aruco_detector import ArucoDetector

logger = logging.getLogger(__name__)


class ExtrinsicCalibrator:
    """
    Compute homography transformation from camera image plane to board plane.
    
    Uses ARUCO markers as reference points to establish correspondence between
    image coordinates (pixels) and board coordinates (millimeters).
    
    Attributes:
        config: Configuration dictionary with marker positions
        aruco_detector: ArucoDetector instance for marker detection
        marker_positions: Dict mapping marker_id → board coordinates (x, y) in mm
    """
    
    # Minimum markers required for homography computation
    MIN_MARKERS_REQUIRED = 4
    
    # RANSAC parameters for cv2.findHomography
    RANSAC_THRESHOLD = 3.0  # pixels
    RANSAC_CONFIDENCE = 0.999
    
    # Quality thresholds
    MAX_REPROJECTION_ERROR = 5.0  # pixels - warn if exceeded
    DEGENERATE_DET_THRESHOLD = 1e-6  # determinant threshold for degenerate homography
    
    def __init__(self, config: dict, aruco_detector: ArucoDetector):
        """
        Initialize extrinsic calibrator.
        
        Args:
            config: Configuration dictionary with marker positions
            aruco_detector: ArucoDetector instance for marker detection
        """
        self.config = config
        self.aruco_detector = aruco_detector
        
        # Load marker positions from config
        self.marker_positions = self._load_marker_positions(config)
        
        logger.info(
            f"ExtrinsicCalibrator initialized with {len(self.marker_positions)} "
            f"marker positions"
        )
    
    def _load_marker_positions(self, config: dict) -> dict[int, tuple[float, float]]:
        """
        Load marker positions from configuration.
        
        Args:
            config: Configuration dictionary
        
        Returns:
            Dictionary mapping marker_id → (x, y) board coordinates in mm
        """
        marker_positions = {}
        
        aruco_markers = config.get('calibration', {}).get('aruco_markers', {})
        
        for key, value in aruco_markers.items():
            # Parse marker_N format
            if key.startswith('marker_'):
                try:
                    marker_id = int(key.split('_')[1])
                    x, y = float(value[0]), float(value[1])
                    marker_positions[marker_id] = (x, y)
                    logger.debug(f"Loaded marker {marker_id} position: ({x}, {y}) mm")
                except (ValueError, IndexError) as e:
                    logger.warning(f"Invalid marker config '{key}': {e}")
        
        if not marker_positions:
            logger.warning(
                "No marker positions found in config. "
                "Expected [calibration.aruco_markers] section with marker_N entries."
            )
        
        return marker_positions

    def _get_marker_board_corners(
        self, marker_id: int, marker_size_mm: float = 40.0
    ) -> np.ndarray:
        """
        Get the 4 corner positions of a marker in board coordinates.
        
        Marker corners are ordered: [top-left, top-right, bottom-right, bottom-left]
        relative to the marker's center position.
        
        Args:
            marker_id: Marker identifier
            marker_size_mm: Physical marker size in millimeters
        
        Returns:
            4×2 array of corner coordinates in board space (mm)
        
        Raises:
            KeyError: If marker_id not found in marker_positions
        """
        if marker_id not in self.marker_positions:
            raise KeyError(f"Marker {marker_id} not found in marker positions")
        
        center_x, center_y = self.marker_positions[marker_id]
        half_size = marker_size_mm / 2.0
        
        # Corners in board coordinates (origin at board center, +X right, +Y up)
        # Order: top-left, top-right, bottom-right, bottom-left
        corners = np.array([
            [center_x - half_size, center_y + half_size],  # top-left
            [center_x + half_size, center_y + half_size],  # top-right
            [center_x + half_size, center_y - half_size],  # bottom-right
            [center_x - half_size, center_y - half_size],  # bottom-left
        ], dtype=np.float32)
        
        return corners
    
    def calibrate(
        self, camera_id: int, image: np.ndarray
    ) -> tuple[np.ndarray, dict] | None:
        """
        Compute homography for a camera.
        
        Args:
            camera_id: Camera identifier
            image: Current camera frame
        
        Returns:
            (homography_matrix, debug_info) or None if calibration fails
            - homography_matrix: 3×3 transformation matrix H
            - debug_info: Dictionary with detected markers, reprojection error, etc.
        """
        if image is None:
            logger.error(f"Camera {camera_id}: Cannot calibrate - image is None")
            return None
        
        # Step 1: Detect markers
        detected_markers = self.aruco_detector.detect_markers(image)
        
        if not detected_markers:
            logger.warning(
                f"Camera {camera_id}: No markers detected. "
                "Check lighting and marker visibility."
            )
            return None
        
        # Step 2: Validate markers
        if not self.aruco_detector.validate_markers(detected_markers):
            logger.warning(
                f"Camera {camera_id}: Marker validation failed. "
                f"Detected {len(detected_markers)} markers, need at least "
                f"{self.MIN_MARKERS_REQUIRED}."
            )
            return None
        
        # Step 3: Build point correspondences
        image_points, board_points, used_markers = self._build_point_correspondences(
            detected_markers
        )
        
        if image_points is None:
            logger.warning(
                f"Camera {camera_id}: Failed to build point correspondences. "
                "Some detected markers may not have configured positions."
            )
            return None
        
        num_points = len(image_points)
        logger.info(
            f"Camera {camera_id}: Built {num_points} point correspondences "
            f"from {len(used_markers)} markers"
        )
        
        # Step 4: Compute homography
        homography, mask = cv2.findHomography(
            image_points, board_points,
            cv2.RANSAC,
            self.RANSAC_THRESHOLD,
            confidence=self.RANSAC_CONFIDENCE
        )
        
        if homography is None:
            logger.error(
                f"Camera {camera_id}: cv2.findHomography() failed. "
                "Check point correspondences."
            )
            return None
        
        # Step 5: Validate homography
        det = np.linalg.det(homography)
        if abs(det) < self.DEGENERATE_DET_THRESHOLD:
            logger.error(
                f"Camera {camera_id}: Degenerate homography (det={det:.2e}). "
                "Markers may be collinear or too close together."
            )
            return None
        
        # Step 6: Compute reprojection error
        reprojection_error = self.verify_homography(
            homography, image_points, board_points
        )
        
        if reprojection_error > self.MAX_REPROJECTION_ERROR:
            logger.warning(
                f"Camera {camera_id}: High reprojection error ({reprojection_error:.2f} pixels). "
                f"Calibration may be inaccurate. Consider recalibrating."
            )
        else:
            logger.info(
                f"Camera {camera_id}: Reprojection error: {reprojection_error:.2f} pixels ✓"
            )
        
        # Build debug info
        debug_info = {
            'camera_id': camera_id,
            'markers_detected': list(detected_markers.keys()),
            'markers_used': used_markers,
            'num_points': num_points,
            'reprojection_error': reprojection_error,
            'homography_det': float(det),
            'inlier_ratio': float(np.sum(mask)) / len(mask) if mask is not None else 1.0,
        }
        
        return homography, debug_info

    def _build_point_correspondences(
        self, detected_markers: dict[int, np.ndarray]
    ) -> tuple[np.ndarray, np.ndarray, list[int]] | tuple[None, None, None]:
        """
        Build arrays of corresponding image and board points.
        
        For each detected marker with a known position, extracts 4 corner
        correspondences (image pixels → board coordinates).
        
        Args:
            detected_markers: Dictionary mapping marker_id → corners (4×2 array)
        
        Returns:
            Tuple of (image_points, board_points, used_markers) or (None, None, None)
            - image_points: N×2 array of pixel coordinates
            - board_points: N×2 array of board coordinates (mm)
            - used_markers: List of marker IDs used
        """
        # Get marker size from config
        aruco_config = self.config.get('calibration', {}).get('aruco', {})
        marker_size_mm = aruco_config.get('marker_size_mm', 40.0)
        
        image_points_list = []
        board_points_list = []
        used_markers = []
        
        for marker_id, image_corners in detected_markers.items():
            # Skip markers without configured positions
            if marker_id not in self.marker_positions:
                logger.debug(
                    f"Skipping marker {marker_id}: no position configured"
                )
                continue
            
            # Get board coordinates for this marker's corners
            try:
                board_corners = self._get_marker_board_corners(
                    marker_id, marker_size_mm
                )
            except KeyError:
                continue
            
            # Add all 4 corners as correspondences
            image_points_list.append(image_corners)
            board_points_list.append(board_corners)
            used_markers.append(marker_id)
        
        # Check minimum markers
        if len(used_markers) < self.MIN_MARKERS_REQUIRED:
            logger.warning(
                f"Insufficient markers with known positions: "
                f"{len(used_markers)} < {self.MIN_MARKERS_REQUIRED}"
            )
            return None, None, None
        
        # Stack into arrays
        image_points = np.vstack(image_points_list).astype(np.float32)
        board_points = np.vstack(board_points_list).astype(np.float32)
        
        return image_points, board_points, used_markers
    
    def save_calibration(
        self,
        camera_id: int,
        homography: np.ndarray,
        debug_info: dict,
        output_dir: str = "calibration"
    ):
        """
        Save homography to JSON file.
        
        Args:
            camera_id: Camera identifier
            homography: 3×3 homography matrix
            debug_info: Calibration metadata
            output_dir: Directory to save calibration file
        
        Output format (homography_cam{N}.json):
        {
            "camera_id": 0,
            "homography": [[h11, h12, h13], [h21, h22, h23], [h31, h32, h33]],
            "markers_detected": [0, 1, 2, 3],
            "num_points": 16,
            "reprojection_error": 2.3,
            "calibration_date": "2024-01-15T10:35:00"
        }
        """
        # Create output directory if needed
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Prepare calibration data
        calibration_data = {
            "camera_id": camera_id,
            "homography": homography.tolist(),
            "markers_detected": debug_info.get('markers_detected', []),
            "markers_used": debug_info.get('markers_used', []),
            "num_points": debug_info.get('num_points', 0),
            "reprojection_error": debug_info.get('reprojection_error', 0.0),
            "calibration_date": datetime.now().isoformat()
        }
        
        # Save to JSON file
        output_file = output_path / f"homography_cam{camera_id}.json"
        
        with open(output_file, 'w') as f:
            json.dump(calibration_data, f, indent=2)
        
        logger.info(f"Homography saved to: {output_file}")
        
        # Log quality assessment
        error = debug_info.get('reprojection_error', 0.0)
        if error < self.MAX_REPROJECTION_ERROR:
            logger.info(
                f"✓ Calibration meets quality requirement "
                f"(error {error:.2f} < {self.MAX_REPROJECTION_ERROR} pixels)"
            )
        else:
            logger.warning(
                f"⚠ Calibration does NOT meet quality requirement "
                f"(error {error:.2f} >= {self.MAX_REPROJECTION_ERROR} pixels)"
            )
        
        return output_file
    
    def verify_homography(
        self,
        homography: np.ndarray,
        image_points: np.ndarray,
        board_points: np.ndarray
    ) -> float:
        """
        Verify homography quality by computing reprojection error.
        
        Transforms board points to image coordinates using the homography
        and computes RMS error against actual image points.
        
        Args:
            homography: 3×3 homography matrix
            image_points: N×2 array of pixel coordinates
            board_points: N×2 array of board coordinates
        
        Returns:
            RMS reprojection error in pixels
        """
        if homography is None:
            return float('inf')
        
        if len(image_points) == 0 or len(board_points) == 0:
            return float('inf')
        
        # Transform board points to image coordinates using inverse homography
        # H maps image → board, so H_inv maps board → image
        try:
            H_inv = np.linalg.inv(homography)
        except np.linalg.LinAlgError:
            logger.error("Cannot invert homography matrix")
            return float('inf')
        
        # Apply inverse homography to board points
        # Convert to homogeneous coordinates
        num_points = len(board_points)
        board_homogeneous = np.hstack([
            board_points,
            np.ones((num_points, 1), dtype=np.float32)
        ])
        
        # Transform: [u', v', w'] = H_inv @ [x, y, 1]
        projected_homogeneous = (H_inv @ board_homogeneous.T).T
        
        # Convert from homogeneous to Cartesian
        w = projected_homogeneous[:, 2:3]
        # Avoid division by zero
        w = np.where(np.abs(w) < 1e-10, 1e-10, w)
        projected_points = projected_homogeneous[:, :2] / w
        
        # Compute RMS error
        errors = np.linalg.norm(image_points - projected_points, axis=1)
        rms_error = float(np.sqrt(np.mean(errors ** 2)))
        
        return rms_error
    
    @staticmethod
    def load_calibration(
        camera_id: int, calibration_dir: str = "calibration"
    ) -> tuple[np.ndarray, dict] | None:
        """
        Load homography data from JSON file.
        
        Args:
            camera_id: Camera identifier
            calibration_dir: Directory containing calibration files
        
        Returns:
            Tuple of (homography, metadata) or None if file not found
        """
        calibration_file = Path(calibration_dir) / f"homography_cam{camera_id}.json"
        
        if not calibration_file.exists():
            logger.warning(f"Homography file not found: {calibration_file}")
            return None
        
        with open(calibration_file, 'r') as f:
            data = json.load(f)
        
        homography = np.array(data['homography'], dtype=np.float64)
        
        metadata = {
            'camera_id': data.get('camera_id', camera_id),
            'markers_detected': data.get('markers_detected', []),
            'markers_used': data.get('markers_used', []),
            'num_points': data.get('num_points', 0),
            'reprojection_error': data.get('reprojection_error', 0.0),
            'calibration_date': data.get('calibration_date', ''),
        }
        
        logger.info(
            f"Loaded homography for camera {camera_id} "
            f"(error: {metadata['reprojection_error']:.2f} pixels)"
        )
        
        return homography, metadata
