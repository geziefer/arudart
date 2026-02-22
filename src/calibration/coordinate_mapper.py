"""
CoordinateMapper class for transforming pixel coordinates to board coordinates.

This is the main interface for coordinate transformation in the ARU-DART system.
Loads calibration data (intrinsic + extrinsic) and provides thread-safe transformation.

Implements AC-6.4.1, AC-6.4.2, AC-6.4.3, AC-6.4.4, AC-6.4.5, AC-6.3.7 from Step 6 requirements.
"""

import json
import logging
import threading
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CoordinateMapper:
    """
    Transform pixel coordinates to board coordinates and vice versa.
    
    Uses intrinsic calibration (camera matrix, distortion) and extrinsic
    calibration (homography) to map between coordinate systems.
    
    Thread-safe for multi-camera operation.
    
    Attributes:
        config: Configuration dictionary
        calibration_dir: Directory containing calibration JSON files
    """
    
    # Board bounds for out-of-bounds checking (mm from center)
    BOARD_RADIUS_MM = 200.0  # Slightly larger than physical board for tolerance
    MAX_VALID_RADIUS_MM = 300.0  # Absolute maximum before returning None
    
    def __init__(self, config: dict, calibration_dir: str = "calibration"):
        """
        Initialize coordinate mapper with calibration data.
        
        Args:
            config: Configuration dictionary from config.toml
            calibration_dir: Directory containing calibration JSON files
        """
        self.config = config
        self.calibration_dir = Path(calibration_dir)
        
        # Calibration data storage
        self._camera_matrices: dict[int, np.ndarray] = {}
        self._distortion_coeffs: dict[int, np.ndarray] = {}
        self._homographies: dict[int, np.ndarray] = {}
        self._homographies_inv: dict[int, np.ndarray] = {}  # Cached inverses
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Load calibration for all cameras
        self._load_all_calibrations()
    
    def _load_all_calibrations(self):
        """Load calibration data for all cameras."""
        for camera_id in [0, 1, 2]:
            try:
                self._load_intrinsic(camera_id)
            except (FileNotFoundError, ValueError) as e:
                logger.warning(f"Camera {camera_id}: Intrinsic calibration not loaded - {e}")
            
            try:
                self._load_homography(camera_id)
            except (FileNotFoundError, ValueError) as e:
                logger.warning(f"Camera {camera_id}: Homography not loaded - {e}")
        
        # Log summary
        calibrated = [cid for cid in [0, 1, 2] if self.is_calibrated(cid)]
        if calibrated:
            logger.info(f"CoordinateMapper: Cameras {calibrated} fully calibrated")
        else:
            logger.warning("CoordinateMapper: No cameras fully calibrated")
    
    def _load_intrinsic(self, camera_id: int):
        """Load intrinsic calibration from JSON file."""
        intrinsic_file = self.calibration_dir / f"intrinsic_cam{camera_id}.json"
        
        if not intrinsic_file.exists():
            raise FileNotFoundError(f"Intrinsic file not found: {intrinsic_file}")
        
        with open(intrinsic_file, 'r') as f:
            data = json.load(f)
        
        camera_matrix = np.array(data['camera_matrix'], dtype=np.float64)
        distortion_coeffs = np.array(data['distortion_coeffs'], dtype=np.float64)
        
        # Validate shapes
        if camera_matrix.shape != (3, 3):
            raise ValueError(f"Invalid camera matrix shape: {camera_matrix.shape}")
        
        self._camera_matrices[camera_id] = camera_matrix
        self._distortion_coeffs[camera_id] = distortion_coeffs
        
        logger.debug(f"Camera {camera_id}: Loaded intrinsic calibration")
    
    def _load_homography(self, camera_id: int):
        """Load homography from JSON file."""
        homography_file = self.calibration_dir / f"homography_cam{camera_id}.json"
        
        if not homography_file.exists():
            raise FileNotFoundError(f"Homography file not found: {homography_file}")
        
        with open(homography_file, 'r') as f:
            data = json.load(f)
        
        homography = np.array(data['homography'], dtype=np.float64)
        
        # Validate shape
        if homography.shape != (3, 3):
            raise ValueError(f"Invalid homography shape: {homography.shape}")
        
        # Check for degenerate homography
        det = np.linalg.det(homography)
        if abs(det) < 1e-10:
            raise ValueError(f"Degenerate homography (det={det})")
        
        self._homographies[camera_id] = homography
        
        # Pre-compute inverse for map_to_image
        self._homographies_inv[camera_id] = np.linalg.inv(homography)
        
        logger.debug(f"Camera {camera_id}: Loaded homography")
    
    def map_to_board(
        self, camera_id: int, u: float, v: float
    ) -> tuple[float, float] | None:
        """
        Transform pixel coordinates to board coordinates.
        
        Args:
            camera_id: Camera identifier (0, 1, or 2)
            u: Pixel x-coordinate
            v: Pixel y-coordinate
        
        Returns:
            (x, y) in millimeters from board center, or None if:
            - Camera not calibrated
            - Coordinates out of bounds
            - Transformation fails
            
        Board coordinate system:
            - Origin (0, 0) at board center
            - +X axis points right
            - +Y axis points up
        """
        with self._lock:
            if not self._is_calibrated_internal(camera_id):
                return None
            
            K = self._camera_matrices[camera_id]
            D = self._distortion_coeffs[camera_id]
            H = self._homographies[camera_id]
        
        try:
            # Step 1: Undistort the pixel coordinate
            pixel = np.array([[[u, v]]], dtype=np.float32)
            undistorted = cv2.undistortPoints(pixel, K, D, P=K)
            u_undist = undistorted[0, 0, 0]
            v_undist = undistorted[0, 0, 1]
            
            # Step 2: Apply homography to get board coordinates
            # H maps image → board
            point_homogeneous = np.array([u_undist, v_undist, 1.0], dtype=np.float64)
            board_homogeneous = H @ point_homogeneous
            
            # Convert from homogeneous
            w = board_homogeneous[2]
            if abs(w) < 1e-10:
                logger.debug(f"Camera {camera_id}: Homogeneous w near zero")
                return None
            
            x = board_homogeneous[0] / w
            y = board_homogeneous[1] / w
            
            # Step 3: Bounds checking
            radius = np.sqrt(x**2 + y**2)
            if radius > self.MAX_VALID_RADIUS_MM:
                logger.debug(
                    f"Camera {camera_id}: Out of bounds ({x:.1f}, {y:.1f}) mm, "
                    f"radius {radius:.1f} mm"
                )
                return None
            
            return float(x), float(y)
        
        except Exception as e:
            logger.error(f"Camera {camera_id}: map_to_board failed - {e}")
            return None
    
    def map_to_image(
        self, camera_id: int, x: float, y: float
    ) -> tuple[float, float] | None:
        """
        Transform board coordinates to pixel coordinates (inverse mapping).
        
        Args:
            camera_id: Camera identifier (0, 1, or 2)
            x: Board x-coordinate in mm
            y: Board y-coordinate in mm
        
        Returns:
            (u, v) pixel coordinates, or None if transformation fails
        """
        with self._lock:
            if not self._is_calibrated_internal(camera_id):
                return None
            
            K = self._camera_matrices[camera_id]
            D = self._distortion_coeffs[camera_id]
            H_inv = self._homographies_inv[camera_id]
        
        try:
            # Step 1: Apply inverse homography (board → undistorted image)
            board_homogeneous = np.array([x, y, 1.0], dtype=np.float64)
            image_homogeneous = H_inv @ board_homogeneous
            
            # Convert from homogeneous
            w = image_homogeneous[2]
            if abs(w) < 1e-10:
                return None
            
            u_undist = image_homogeneous[0] / w
            v_undist = image_homogeneous[1] / w
            
            # Step 2: Apply distortion (redistort)
            # Convert to normalized coordinates
            fx, fy = K[0, 0], K[1, 1]
            cx, cy = K[0, 2], K[1, 2]
            
            x_norm = (u_undist - cx) / fx
            y_norm = (v_undist - cy) / fy
            
            # Apply distortion model
            k1, k2, p1, p2, k3 = D[0], D[1], D[2], D[3], D[4] if len(D) > 4 else 0
            
            r2 = x_norm**2 + y_norm**2
            r4 = r2**2
            r6 = r2**3
            
            # Radial distortion
            radial = 1 + k1*r2 + k2*r4 + k3*r6
            
            # Tangential distortion
            x_dist = x_norm * radial + 2*p1*x_norm*y_norm + p2*(r2 + 2*x_norm**2)
            y_dist = y_norm * radial + p1*(r2 + 2*y_norm**2) + 2*p2*x_norm*y_norm
            
            # Convert back to pixel coordinates
            u = fx * x_dist + cx
            v = fy * y_dist + cy
            
            return float(u), float(v)
        
        except Exception as e:
            logger.error(f"Camera {camera_id}: map_to_image failed - {e}")
            return None
    
    def is_calibrated(self, camera_id: int) -> bool:
        """
        Check if camera has valid calibration data.
        
        Args:
            camera_id: Camera identifier
        
        Returns:
            True if both intrinsic and extrinsic calibration loaded
        """
        with self._lock:
            return self._is_calibrated_internal(camera_id)
    
    def _is_calibrated_internal(self, camera_id: int) -> bool:
        """Internal calibration check (no lock)."""
        return (
            camera_id in self._camera_matrices and
            camera_id in self._distortion_coeffs and
            camera_id in self._homographies
        )
    
    def reload_calibration(self, camera_id: int | None = None):
        """
        Reload calibration data from disk.
        
        Args:
            camera_id: Specific camera to reload, or None for all cameras
        """
        with self._lock:
            if camera_id is not None:
                cameras = [camera_id]
            else:
                cameras = [0, 1, 2]
            
            for cid in cameras:
                # Clear existing data
                self._camera_matrices.pop(cid, None)
                self._distortion_coeffs.pop(cid, None)
                self._homographies.pop(cid, None)
                self._homographies_inv.pop(cid, None)
                
                # Reload
                try:
                    self._load_intrinsic(cid)
                except (FileNotFoundError, ValueError) as e:
                    logger.warning(f"Camera {cid}: Intrinsic reload failed - {e}")
                
                try:
                    self._load_homography(cid)
                except (FileNotFoundError, ValueError) as e:
                    logger.warning(f"Camera {cid}: Homography reload failed - {e}")
        
        logger.info(f"Calibration reloaded for cameras: {cameras}")
    
    def get_calibration_status(self) -> dict[int, dict]:
        """
        Get calibration status for all cameras.
        
        Returns:
            Dictionary mapping camera_id → status dict with:
            - has_intrinsic: bool
            - has_homography: bool
            - is_calibrated: bool
        """
        with self._lock:
            status = {}
            for camera_id in [0, 1, 2]:
                status[camera_id] = {
                    'has_intrinsic': camera_id in self._camera_matrices,
                    'has_homography': camera_id in self._homographies,
                    'is_calibrated': self._is_calibrated_internal(camera_id),
                }
            return status
    
    def is_out_of_bounds(self, x: float, y: float) -> bool:
        """
        Check if board coordinates are outside valid board area.
        
        Args:
            x: Board x-coordinate in mm
            y: Board y-coordinate in mm
        
        Returns:
            True if coordinates are outside board radius
        """
        radius = np.sqrt(x**2 + y**2)
        return radius > self.BOARD_RADIUS_MM
