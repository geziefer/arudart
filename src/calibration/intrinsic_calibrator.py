"""
Intrinsic calibration using chessboard pattern.

Captures multiple chessboard images from a camera, detects corners,
and computes camera matrix + distortion coefficients using
cv2.calibrateCamera. Results are saved to JSON for use by CoordinateMapper.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class IntrinsicCalibrator:
    """
    Chessboard-based intrinsic camera calibration.
    
    Detects chessboard corners in captured images and computes
    camera matrix and distortion coefficients.
    """
    
    def __init__(self, config: dict):
        """
        Initialize intrinsic calibrator.
        
        Args:
            config: Configuration dict, expects 'calibration.chessboard' section
        """
        chessboard_config = config.get("calibration", {}).get("chessboard", {})
        corners = chessboard_config.get("inner_corners", [9, 6])
        self.pattern_size = (corners[0], corners[1])
        self.square_size_mm = chessboard_config.get("square_size_mm", 25.0)
        
        # Termination criteria for corner sub-pixel refinement
        self.criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            30, 0.001
        )
        
        # Prepare object points (3D points in real world space)
        # (0,0,0), (25,0,0), (50,0,0), ..., (200,125,0)
        self.objp = np.zeros(
            (self.pattern_size[0] * self.pattern_size[1], 3),
            dtype=np.float32
        )
        self.objp[:, :2] = np.mgrid[
            0:self.pattern_size[0],
            0:self.pattern_size[1]
        ].T.reshape(-1, 2) * self.square_size_mm
        
        logger.info(
            f"IntrinsicCalibrator: pattern={self.pattern_size}, "
            f"square={self.square_size_mm}mm"
        )

    def detect_corners(
        self, image: np.ndarray
    ) -> Optional[np.ndarray]:
        """
        Detect chessboard corners in an image.
        
        Args:
            image: BGR image
        
        Returns:
            Refined corner positions (N, 1, 2) or None if not found
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        found, corners = cv2.findChessboardCorners(
            gray, self.pattern_size,
            cv2.CALIB_CB_ADAPTIVE_THRESH
            + cv2.CALIB_CB_NORMALIZE_IMAGE
            + cv2.CALIB_CB_FAST_CHECK
        )
        
        if not found:
            return None
        
        # Sub-pixel refinement
        corners_refined = cv2.cornerSubPix(
            gray, corners, (11, 11), (-1, -1), self.criteria
        )
        return corners_refined
    
    def draw_corners(
        self, image: np.ndarray, corners: np.ndarray
    ) -> np.ndarray:
        """
        Draw detected corners on image for visualization.
        
        Args:
            image: BGR image
            corners: Corner positions from detect_corners()
        
        Returns:
            Image with corners drawn
        """
        vis = image.copy()
        cv2.drawChessboardCorners(vis, self.pattern_size, corners, True)
        return vis
    
    def calibrate(
        self, images: list[np.ndarray]
    ) -> Optional[dict]:
        """
        Run calibration from a list of chessboard images.
        
        Args:
            images: List of BGR images containing chessboard pattern
        
        Returns:
            Dict with camera_matrix, distortion_coeffs, reprojection_error,
            image_size, num_images. Returns None if insufficient valid images.
        """
        obj_points = []  # 3D points
        img_points = []  # 2D points
        image_size = None
        
        for i, image in enumerate(images):
            if image_size is None:
                h, w = image.shape[:2]
                image_size = (w, h)
            
            corners = self.detect_corners(image)
            if corners is not None:
                obj_points.append(self.objp)
                img_points.append(corners)
                logger.debug(f"Image {i}: corners detected")
            else:
                logger.debug(f"Image {i}: no corners found")
        
        if len(obj_points) < 5:
            logger.error(
                f"Insufficient valid images: {len(obj_points)} < 5"
            )
            return None
        
        logger.info(
            f"Calibrating with {len(obj_points)}/{len(images)} valid images"
        )
        
        ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
            obj_points, img_points, image_size, None, None
        )
        
        logger.info(f"Reprojection error: {ret:.4f} pixels")
        
        if ret > 1.0:
            logger.warning(
                f"High reprojection error: {ret:.4f}px (threshold: 0.5px)"
            )
        
        return {
            "camera_matrix": camera_matrix,
            "distortion_coeffs": dist_coeffs.flatten(),
            "reprojection_error": ret,
            "image_size": list(image_size),
            "num_images": len(obj_points),
        }
    
    def save(
        self,
        camera_id: int,
        calibration_data: dict,
        output_dir: str = "calibration"
    ):
        """
        Save intrinsic calibration to JSON.
        
        Args:
            camera_id: Camera identifier (0, 1, 2)
            calibration_data: Dict from calibrate()
            output_dir: Output directory
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = output_path / f"intrinsic_cam{camera_id}.json"
        
        data = {
            "camera_id": camera_id,
            "camera_matrix": calibration_data["camera_matrix"].tolist(),
            "distortion_coeffs": calibration_data["distortion_coeffs"].tolist(),
            "reprojection_error": calibration_data["reprojection_error"],
            "image_size": calibration_data["image_size"],
            "num_images": calibration_data["num_images"],
            "calibration_date": datetime.now().isoformat(),
        }
        
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved intrinsic calibration: {filename}")
    
    def load(
        self, camera_id: int, calibration_dir: str = "calibration"
    ) -> Optional[dict]:
        """
        Load intrinsic calibration from JSON.
        
        Args:
            camera_id: Camera identifier
            calibration_dir: Directory containing calibration files
        
        Returns:
            Dict with camera_matrix (ndarray), distortion_coeffs (ndarray),
            or None if file not found.
        """
        filename = Path(calibration_dir) / f"intrinsic_cam{camera_id}.json"
        
        if not filename.exists():
            return None
        
        try:
            with open(filename, "r") as f:
                data = json.load(f)
            
            return {
                "camera_matrix": np.array(
                    data["camera_matrix"], dtype=np.float64
                ),
                "distortion_coeffs": np.array(
                    data["distortion_coeffs"], dtype=np.float64
                ),
                "reprojection_error": data["reprojection_error"],
                "image_size": data["image_size"],
            }
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
            return None
