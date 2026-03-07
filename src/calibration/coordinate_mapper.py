"""
Coordinate mapper for transforming between pixel and board coordinates.

This module provides the main interface for coordinate transformation,
loading calibration data and applying homography transformations.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CoordinateMapper:
    """
    Main interface for pixel-to-board coordinate transformation.
    
    Loads intrinsic calibration (camera matrix, distortion) and homography
    matrices from JSON files, and provides thread-safe coordinate transformation.
    
    Coordinate system:
    - Board: Origin at bull center, +X right, +Y up, millimeters
    - Image: Origin at top-left, +u right, +v down, pixels
    """
    
    def __init__(self, config: dict, calibration_dir: str = "calibration"):
        """
        Initialize coordinate mapper.
        
        Args:
            config: Configuration dictionary
            calibration_dir: Directory containing calibration JSON files
        """
        self.calibration_dir = Path(calibration_dir)
        self.config = config
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Calibration data per camera
        self._camera_matrices = {}  # camera_id -> K (3x3)
        self._distortion_coeffs = {}  # camera_id -> D (5,)
        self._homographies = {}  # camera_id -> H (3x3)
        
        # Load calibration for all cameras
        for camera_id in [0, 1, 2]:
            self._load_intrinsic(camera_id)
            self._load_homography(camera_id)
        
        logger.info(
            f"CoordinateMapper initialized: "
            f"{len(self._homographies)}/3 cameras calibrated"
        )
    
    def _load_intrinsic(self, camera_id: int):
        """
        Load intrinsic calibration (camera matrix and distortion).
        
        Args:
            camera_id: Camera identifier (0, 1, 2)
        """
        filename = self.calibration_dir / f"intrinsic_cam{camera_id}.json"
        
        if not filename.exists():
            logger.debug(f"Intrinsic calibration not found: {filename}")
            return
        
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            
            K = np.array(data['camera_matrix'], dtype=np.float64)
            D = np.array(data['distortion_coeffs'], dtype=np.float64)
            
            with self._lock:
                self._camera_matrices[camera_id] = K
                self._distortion_coeffs[camera_id] = D
            
            logger.info(
                f"Loaded intrinsic calibration for camera {camera_id}: "
                f"error={data.get('reprojection_error', 'N/A'):.3f}px"
            )
        
        except Exception as e:
            logger.error(f"Error loading intrinsic calibration from {filename}: {e}")
    
    def _load_homography(self, camera_id: int):
        """
        Load homography matrix.
        
        Args:
            camera_id: Camera identifier (0, 1, 2)
        """
        filename = self.calibration_dir / f"homography_cam{camera_id}.json"
        
        if not filename.exists():
            logger.debug(f"Homography not found: {filename}")
            return
        
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            
            H = np.array(data['homography'], dtype=np.float64)
            
            with self._lock:
                self._homographies[camera_id] = H
            
            logger.info(
                f"Loaded homography for camera {camera_id}: "
                f"{data.get('num_inliers', 'N/A')}/{data.get('num_points', 'N/A')} inliers, "
                f"error={data.get('reprojection_error_mm', 'N/A'):.2f}mm"
            )
        
        except Exception as e:
            logger.error(f"Error loading homography from {filename}: {e}")
    
    def map_to_board(
        self, 
        camera_id: int, 
        u: float, 
        v: float
    ) -> Optional[tuple[float, float]]:
        """
        Transform pixel coordinates to board coordinates.
        
        Args:
            camera_id: Camera identifier (0, 1, 2)
            u: Pixel x-coordinate (horizontal)
            v: Pixel y-coordinate (vertical)
        
        Returns:
            (x, y) board coordinates in millimeters, or None if:
            - Camera not calibrated
            - Point maps outside board bounds (radius > 200mm)
        """
        with self._lock:
            if camera_id not in self._homographies:
                return None
            
            H = self._homographies[camera_id]
            K = self._camera_matrices.get(camera_id)
            D = self._distortion_coeffs.get(camera_id)
        
        # Undistort pixel if intrinsic calibration available
        if K is not None and D is not None:
            point = np.array([[[u, v]]], dtype=np.float32)
            undistorted = cv2.undistortPoints(point, K, D, P=K)
            u_undist, v_undist = undistorted[0, 0]
        else:
            u_undist, v_undist = u, v
        
        # Apply homography (image -> board)
        point_h = np.array([[u_undist, v_undist, 1.0]])
        result = H @ point_h.T
        x = result[0, 0] / result[2, 0]
        y = result[1, 0] / result[2, 0]
        
        # Bounds check (board radius ~170mm for scoring area, 200mm for safety)
        radius = np.sqrt(x*x + y*y)
        if radius > 200:
            return None
        
        return (float(x), float(y))
    
    def map_to_image(
        self, 
        camera_id: int, 
        x: float, 
        y: float
    ) -> Optional[tuple[float, float]]:
        """
        Transform board coordinates to pixel coordinates (inverse).
        
        Args:
            camera_id: Camera identifier (0, 1, 2)
            x: Board x-coordinate in millimeters
            y: Board y-coordinate in millimeters
        
        Returns:
            (u, v) pixel coordinates, or None if camera not calibrated
        """
        with self._lock:
            if camera_id not in self._homographies:
                return None
            
            H = self._homographies[camera_id]
            K = self._camera_matrices.get(camera_id)
            D = self._distortion_coeffs.get(camera_id)
        
        # Inverse homography (board -> image)
        H_inv = np.linalg.inv(H)
        
        # Apply inverse homography
        point_h = np.array([[x, y, 1.0]])
        result = H_inv @ point_h.T
        u = result[0, 0] / result[2, 0]
        v = result[1, 0] / result[2, 0]
        
        # Apply distortion if intrinsic calibration available
        if K is not None and D is not None:
            # Note: cv2.projectPoints expects 3D points, so we add z=0
            points_3d = np.array([[x, y, 0.0]], dtype=np.float32)
            rvec = np.zeros(3, dtype=np.float32)
            tvec = np.zeros(3, dtype=np.float32)
            
            # This is a simplified approach - for full accuracy, we'd need
            # to properly handle the distortion model
            # For now, we return undistorted coordinates
            pass
        
        return (float(u), float(v))
    
    def is_calibrated(self, camera_id: int) -> bool:
        """
        Check if camera is calibrated (has homography).
        
        Args:
            camera_id: Camera identifier (0, 1, 2)
        
        Returns:
            True if camera has homography loaded
        """
        with self._lock:
            return camera_id in self._homographies
    
    def reload_calibration(self, camera_id: Optional[int] = None):
        """
        Reload calibration from disk.
        
        Args:
            camera_id: Camera to reload, or None to reload all cameras
        """
        if camera_id is not None:
            logger.info(f"Reloading calibration for camera {camera_id}")
            self._load_intrinsic(camera_id)
            self._load_homography(camera_id)
        else:
            logger.info("Reloading calibration for all cameras")
            for cam_id in [0, 1, 2]:
                self._load_intrinsic(cam_id)
                self._load_homography(cam_id)
    
    def get_calibrated_cameras(self) -> list[int]:
        """
        Get list of calibrated camera IDs.
        
        Returns:
            List of camera IDs that have homography loaded
        """
        with self._lock:
            return list(self._homographies.keys())
