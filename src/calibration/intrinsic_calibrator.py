"""
IntrinsicCalibrator class for camera intrinsic calibration.

Uses chessboard pattern to compute camera matrix and distortion coefficients.
Implements AC-6.1.1, AC-6.1.2, AC-6.1.3, AC-6.1.4 from Step 6 requirements.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


class IntrinsicCalibrator:
    """
    Perform intrinsic camera calibration using chessboard pattern.
    
    Computes camera matrix K and distortion coefficients D using
    cv2.calibrateCamera() with captured chessboard images.
    """
    
    def __init__(self, config: dict, chessboard_size: tuple[int, int] = None,
                 square_size_mm: float = None):
        """
        Initialize intrinsic calibrator.
        
        Args:
            config: Configuration dictionary from config.toml
            chessboard_size: Inner corners (width, height). If None, reads from config.
            square_size_mm: Size of each square in millimeters. If None, reads from config.
        """
        self.logger = logging.getLogger('arudart.intrinsic_calibrator')
        self.config = config
        
        # Get chessboard parameters from config or use provided values
        calib_config = config.get('calibration', {}).get('chessboard', {})
        
        if chessboard_size is not None:
            self.chessboard_size = chessboard_size
        else:
            inner_corners = calib_config.get('inner_corners', [9, 6])
            self.chessboard_size = (inner_corners[0], inner_corners[1])
        
        if square_size_mm is not None:
            self.square_size_mm = square_size_mm
        else:
            self.square_size_mm = calib_config.get('square_size_mm', 25.0)
        
        # Get image size from camera settings
        camera_settings = config.get('camera_settings', {})
        self.image_width = camera_settings.get('width', 800)
        self.image_height = camera_settings.get('height', 600)
        
        # Termination criteria for corner sub-pixel refinement
        self.subpix_criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            30,  # max iterations
            0.001  # epsilon
        )
        
        # Prepare 3D object points for chessboard (z=0 plane)
        # Points are in millimeters: (0,0,0), (25,0,0), (50,0,0), ...
        self.objp = np.zeros(
            (self.chessboard_size[0] * self.chessboard_size[1], 3),
            dtype=np.float32
        )
        self.objp[:, :2] = np.mgrid[
            0:self.chessboard_size[0],
            0:self.chessboard_size[1]
        ].T.reshape(-1, 2) * self.square_size_mm
        
        self.logger.info(
            f"IntrinsicCalibrator initialized: "
            f"chessboard={self.chessboard_size}, "
            f"square_size={self.square_size_mm}mm"
        )
    
    def capture_calibration_images(self, camera_id: int, num_images: int = 25,
                                   display: bool = True) -> list[np.ndarray]:
        """
        Capture chessboard images for calibration.
        
        Args:
            camera_id: Camera device index to calibrate
            num_images: Target number of images (20-30 recommended)
            display: Show preview window with detection overlay
        
        Returns:
            List of captured images with detected chessboard
            
        User interaction:
            - Press SPACE to capture image when chessboard detected
            - Press 'q' to finish early
            - Shows live preview with chessboard detection overlay
        """
        self.logger.info(f"Starting calibration image capture for camera {camera_id}")
        self.logger.info(f"Target: {num_images} images, press SPACE to capture, 'q' to finish")
        
        # Open camera
        cap = cv2.VideoCapture(camera_id)
        if not cap.isOpened():
            self.logger.error(f"Failed to open camera {camera_id}")
            return []
        
        # Set camera resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.image_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.image_height)
        
        captured_images = []
        window_name = f"Intrinsic Calibration - Camera {camera_id}"
        
        if display:
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        
        try:
            while len(captured_images) < num_images:
                ret, frame = cap.read()
                if not ret:
                    self.logger.warning("Failed to read frame from camera")
                    continue
                
                # Convert to grayscale for chessboard detection
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Find chessboard corners
                found, corners = cv2.findChessboardCorners(
                    gray, self.chessboard_size,
                    cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
                )
                
                # Create display frame
                display_frame = frame.copy()
                
                if found:
                    # Refine corner positions to sub-pixel accuracy
                    corners_refined = cv2.cornerSubPix(
                        gray, corners, (11, 11), (-1, -1), self.subpix_criteria
                    )
                    
                    # Draw detected corners
                    cv2.drawChessboardCorners(
                        display_frame, self.chessboard_size, corners_refined, found
                    )
                    
                    # Show status
                    status_text = f"Chessboard DETECTED - Press SPACE to capture"
                    status_color = (0, 255, 0)  # Green
                else:
                    status_text = "Chessboard not detected - adjust position"
                    status_color = (0, 0, 255)  # Red
                
                # Draw status overlay
                cv2.putText(
                    display_frame, status_text,
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2
                )
                cv2.putText(
                    display_frame, f"Captured: {len(captured_images)}/{num_images}",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
                )
                cv2.putText(
                    display_frame, "Press 'q' to finish early",
                    (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1
                )
                
                if display:
                    cv2.imshow(window_name, display_frame)
                
                # Handle key presses
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q'):
                    self.logger.info("User requested early finish")
                    break
                elif key == ord(' ') and found:
                    # Capture this image
                    captured_images.append(frame.copy())
                    self.logger.info(
                        f"Captured image {len(captured_images)}/{num_images}"
                    )
                    
                    # Brief visual feedback
                    if display:
                        feedback_frame = display_frame.copy()
                        cv2.putText(
                            feedback_frame, "CAPTURED!",
                            (300, 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 4
                        )
                        cv2.imshow(window_name, feedback_frame)
                        cv2.waitKey(200)
        
        finally:
            cap.release()
            if display:
                cv2.destroyWindow(window_name)
        
        self.logger.info(f"Captured {len(captured_images)} calibration images")
        return captured_images

    def find_chessboard_corners(self, image: np.ndarray) -> tuple[bool, np.ndarray | None]:
        """
        Find chessboard corners in an image.
        
        Args:
            image: Input image (BGR or grayscale)
        
        Returns:
            Tuple of (found, corners)
            - found: True if chessboard was detected
            - corners: Refined corner positions (N×1×2 array) or None
        """
        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # Find chessboard corners
        found, corners = cv2.findChessboardCorners(
            gray, self.chessboard_size,
            cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
        )
        
        if found:
            # Refine to sub-pixel accuracy
            corners = cv2.cornerSubPix(
                gray, corners, (11, 11), (-1, -1), self.subpix_criteria
            )
            return True, corners
        
        return False, None
    
    def calibrate(self, images: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, float]:
        """
        Compute camera matrix and distortion coefficients.
        
        Args:
            images: List of chessboard images
        
        Returns:
            (camera_matrix, distortion_coeffs, reprojection_error)
            - camera_matrix: 3×3 intrinsic matrix K
            - distortion_coeffs: 5-element distortion vector [k1, k2, p1, p2, k3]
            - reprojection_error: RMS error in pixels (should be < 0.5)
        
        Raises:
            ValueError: If calibration fails or too few valid images
        """
        if len(images) < 10:
            raise ValueError(
                f"Insufficient images for calibration: {len(images)} provided, "
                f"minimum 10 required (20-30 recommended)"
            )
        
        self.logger.info(f"Starting calibration with {len(images)} images")
        
        # Collect object points and image points from all valid images
        object_points = []  # 3D points in world coordinates
        image_points = []   # 2D points in image coordinates
        valid_count = 0
        
        for i, image in enumerate(images):
            found, corners = self.find_chessboard_corners(image)
            
            if found:
                object_points.append(self.objp)
                image_points.append(corners)
                valid_count += 1
            else:
                self.logger.warning(f"Chessboard not found in image {i}")
        
        if valid_count < 10:
            raise ValueError(
                f"Too few valid images: {valid_count} with detected chessboard, "
                f"minimum 10 required"
            )
        
        self.logger.info(f"Found chessboard in {valid_count}/{len(images)} images")
        
        # Get image size from first image
        if len(images[0].shape) == 3:
            image_size = (images[0].shape[1], images[0].shape[0])  # (width, height)
        else:
            image_size = (images[0].shape[1], images[0].shape[0])
        
        # Run calibration
        self.logger.info("Running cv2.calibrateCamera()...")
        
        ret, camera_matrix, distortion_coeffs, rvecs, tvecs = cv2.calibrateCamera(
            object_points, image_points, image_size, None, None
        )
        
        if not ret:
            raise ValueError("cv2.calibrateCamera() failed")
        
        # Compute reprojection error
        total_error = 0
        total_points = 0
        
        for i in range(len(object_points)):
            projected_points, _ = cv2.projectPoints(
                object_points[i], rvecs[i], tvecs[i],
                camera_matrix, distortion_coeffs
            )
            error = cv2.norm(image_points[i], projected_points, cv2.NORM_L2)
            total_error += error ** 2
            total_points += len(object_points[i])
        
        reprojection_error = np.sqrt(total_error / total_points)
        
        self.logger.info(f"Calibration complete:")
        self.logger.info(f"  Camera matrix:\n{camera_matrix}")
        self.logger.info(f"  Distortion coeffs: {distortion_coeffs.flatten()}")
        self.logger.info(f"  Reprojection error: {reprojection_error:.4f} pixels")
        
        # Validate reprojection error
        if reprojection_error > 0.5:
            self.logger.warning(
                f"Reprojection error ({reprojection_error:.4f}) exceeds threshold (0.5). "
                f"Consider capturing more images at different angles."
            )
        else:
            self.logger.info(f"Reprojection error {reprojection_error:.4f} < 0.5 ✓")
        
        # Flatten distortion coeffs to 1D array
        distortion_coeffs = distortion_coeffs.flatten()
        
        return camera_matrix, distortion_coeffs, reprojection_error
    
    def save_calibration(self, camera_id: int, camera_matrix: np.ndarray,
                        distortion_coeffs: np.ndarray, reprojection_error: float,
                        output_dir: str = "calibration"):
        """
        Save calibration results to JSON file.
        
        Args:
            camera_id: Camera identifier
            camera_matrix: 3×3 intrinsic matrix
            distortion_coeffs: Distortion coefficients
            reprojection_error: Calibration quality metric
            output_dir: Directory to save calibration file
        
        Output format (intrinsic_cam{N}.json):
        {
            "camera_id": 0,
            "camera_matrix": [[fx, 0, cx], [0, fy, cy], [0, 0, 1]],
            "distortion_coeffs": [k1, k2, p1, p2, k3],
            "reprojection_error": 0.42,
            "image_size": [800, 600],
            "chessboard_size": [9, 6],
            "square_size_mm": 25.0,
            "calibration_date": "2024-01-15T10:30:00"
        }
        """
        # Create output directory if needed
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Prepare calibration data
        calibration_data = {
            "camera_id": camera_id,
            "camera_matrix": camera_matrix.tolist(),
            "distortion_coeffs": distortion_coeffs.tolist(),
            "reprojection_error": float(reprojection_error),
            "image_size": [self.image_width, self.image_height],
            "chessboard_size": list(self.chessboard_size),
            "square_size_mm": self.square_size_mm,
            "calibration_date": datetime.now().isoformat()
        }
        
        # Save to JSON file
        output_file = output_path / f"intrinsic_cam{camera_id}.json"
        
        with open(output_file, 'w') as f:
            json.dump(calibration_data, f, indent=2)
        
        self.logger.info(f"Calibration saved to: {output_file}")
        
        # Validate reprojection error meets requirement
        if reprojection_error < 0.5:
            self.logger.info(
                f"✓ Calibration meets quality requirement "
                f"(error {reprojection_error:.4f} < 0.5 pixels)"
            )
        else:
            self.logger.warning(
                f"⚠ Calibration does NOT meet quality requirement "
                f"(error {reprojection_error:.4f} >= 0.5 pixels)"
            )
        
        return output_file
    
    @staticmethod
    def load_calibration(camera_id: int, calibration_dir: str = "calibration"
                        ) -> tuple[np.ndarray, np.ndarray, float] | None:
        """
        Load calibration data from JSON file.
        
        Args:
            camera_id: Camera identifier
            calibration_dir: Directory containing calibration files
        
        Returns:
            Tuple of (camera_matrix, distortion_coeffs, reprojection_error)
            or None if file not found
        """
        logger = logging.getLogger('arudart.intrinsic_calibrator')
        
        calibration_file = Path(calibration_dir) / f"intrinsic_cam{camera_id}.json"
        
        if not calibration_file.exists():
            logger.warning(f"Calibration file not found: {calibration_file}")
            return None
        
        with open(calibration_file, 'r') as f:
            data = json.load(f)
        
        camera_matrix = np.array(data['camera_matrix'], dtype=np.float64)
        distortion_coeffs = np.array(data['distortion_coeffs'], dtype=np.float64)
        reprojection_error = data['reprojection_error']
        
        logger.info(
            f"Loaded intrinsic calibration for camera {camera_id} "
            f"(error: {reprojection_error:.4f} pixels)"
        )
        
        return camera_matrix, distortion_coeffs, reprojection_error
