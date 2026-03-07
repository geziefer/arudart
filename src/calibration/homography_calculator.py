"""
Homography calculator for computing transformation matrices.

This module computes homography matrices from matched point pairs using
RANSAC for robustness, and provides serialization for persistence.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class HomographyCalculator:
    """
    Compute and manage homography matrices for coordinate transformation.
    
    Uses RANSAC for robust homography computation from point correspondences.
    """
    
    def __init__(self, config: dict):
        """
        Initialize homography calculator.
        
        Args:
            config: Configuration dictionary with RANSAC parameters
        """
        self.ransac_threshold = config.get('ransac_threshold_px', 5.0)
        self.ransac_confidence = config.get('ransac_confidence', 0.999)
        self.max_reprojection_error = config.get('max_reprojection_error_mm', 5.0)
        
        logger.info(
            f"HomographyCalculator initialized: "
            f"RANSAC threshold={self.ransac_threshold}px, "
            f"confidence={self.ransac_confidence}"
        )
    
    def compute(
        self, 
        point_pairs: list[tuple[tuple[float, float], tuple[float, float]]]
    ) -> Optional[tuple[np.ndarray, dict]]:
        """
        Compute homography matrix from point correspondences.
        
        Args:
            point_pairs: List of ((u, v), (x, y)) tuples where:
                - (u, v) are pixel coordinates
                - (x, y) are board coordinates in millimeters
        
        Returns:
            Tuple of (homography_matrix, metadata) or None if computation fails
            - homography_matrix: 3x3 numpy array
            - metadata: dict with num_points, num_inliers, reprojection_error_mm, timestamp
        """
        if len(point_pairs) < 4:
            logger.error(f"Insufficient points for homography: {len(point_pairs)} < 4")
            return None
        
        # Separate into image and board point arrays
        image_points = np.array([p[0] for p in point_pairs], dtype=np.float32)
        board_points = np.array([p[1] for p in point_pairs], dtype=np.float32)
        
        logger.info(f"Computing homography from {len(point_pairs)} point pairs")
        
        # Compute homography with RANSAC
        try:
            H, mask = cv2.findHomography(
                image_points,
                board_points,
                method=cv2.RANSAC,
                ransacReprojThreshold=self.ransac_threshold,
                confidence=self.ransac_confidence
            )
            
            if H is None:
                logger.error("Homography computation returned None")
                return None
            
            # Check for degenerate homography
            det = np.linalg.det(H)
            if abs(det) < 1e-6:
                logger.error(f"Degenerate homography: det={det}")
                return None
            
            # Verify homography quality
            num_inliers = int(np.sum(mask))
            error = self.verify(H, point_pairs)
            
            logger.info(
                f"Homography computed: {num_inliers}/{len(point_pairs)} inliers, "
                f"reprojection error={error:.2f}mm"
            )
            
            if error > self.max_reprojection_error:
                logger.warning(
                    f"High reprojection error: {error:.2f}mm > {self.max_reprojection_error}mm"
                )
            
            # Build metadata
            metadata = {
                'num_points': len(point_pairs),
                'num_inliers': num_inliers,
                'reprojection_error_mm': float(error),
                'timestamp': datetime.now().isoformat()
            }
            
            return (H, metadata)
        
        except Exception as e:
            logger.error(f"Error computing homography: {e}")
            return None
    
    def verify(
        self, 
        homography: np.ndarray, 
        point_pairs: list[tuple[tuple[float, float], tuple[float, float]]]
    ) -> float:
        """
        Compute average reprojection error for homography.
        
        Args:
            homography: 3x3 homography matrix (image -> board)
            point_pairs: List of ((u, v), (x, y)) point correspondences
        
        Returns:
            Average reprojection error in millimeters
        """
        if len(point_pairs) == 0:
            return float('inf')
        
        image_points = np.array([p[0] for p in point_pairs], dtype=np.float32)
        board_points = np.array([p[1] for p in point_pairs], dtype=np.float32)
        
        # Project image points to board coordinates
        image_h = np.hstack([image_points, np.ones((len(image_points), 1))])
        projected_h = (homography @ image_h.T).T
        projected = projected_h[:, :2] / projected_h[:, 2:3]
        
        # Compute errors in millimeters
        errors = np.linalg.norm(board_points - projected, axis=1)
        avg_error = float(np.mean(errors))
        
        return avg_error
    
    def save(
        self, 
        camera_id: int, 
        homography: np.ndarray, 
        metadata: dict, 
        output_dir: str = "calibration"
    ):
        """
        Save homography matrix to JSON file.
        
        Args:
            camera_id: Camera identifier (0, 1, 2)
            homography: 3x3 homography matrix
            metadata: Metadata dict from compute()
            output_dir: Output directory path
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = output_path / f"homography_cam{camera_id}.json"
        
        # Build JSON data
        data = {
            'camera_id': camera_id,
            'homography': homography.tolist(),
            **metadata
        }
        
        # Write to file
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved homography to {filename}")
    
    def load(
        self, 
        camera_id: int, 
        calibration_dir: str = "calibration"
    ) -> Optional[np.ndarray]:
        """
        Load homography matrix from JSON file.
        
        Args:
            camera_id: Camera identifier (0, 1, 2)
            calibration_dir: Calibration directory path
        
        Returns:
            3x3 homography matrix or None if file not found
        """
        filename = Path(calibration_dir) / f"homography_cam{camera_id}.json"
        
        if not filename.exists():
            logger.warning(f"Homography file not found: {filename}")
            return None
        
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            
            homography = np.array(data['homography'], dtype=np.float64)
            
            logger.info(
                f"Loaded homography from {filename}: "
                f"{data.get('num_inliers', 'N/A')}/{data.get('num_points', 'N/A')} inliers, "
                f"error={data.get('reprojection_error_mm', 'N/A'):.2f}mm"
            )
            
            return homography
        
        except Exception as e:
            logger.error(f"Error loading homography from {filename}: {e}")
            return None
