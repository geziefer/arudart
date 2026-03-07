"""
Manual calibration using interactive control point selection.

This module provides an interactive UI for clicking known control points
on the dartboard to establish pixel-to-board coordinate correspondences.
"""

import logging
from typing import Optional

import cv2
import numpy as np

from .board_geometry import BoardGeometry

logger = logging.getLogger(__name__)


class ManualCalibrator:
    """
    Interactive manual calibration using control point selection.
    
    The user clicks on known dartboard features (bull, T20, D20, etc.) and
    the system records the pixel-to-board coordinate correspondences.
    """
    
    def __init__(self, board_geometry: BoardGeometry):
        """
        Initialize manual calibrator.
        
        Args:
            board_geometry: BoardGeometry instance for coordinate computation
        """
        self.board_geometry = board_geometry
        self.control_points = board_geometry.get_control_point_coords()
        
        # UI state
        self.current_image = None
        self.clicked_points = {}  # label -> (u, v)
        self.current_point_index = 0
        self.window_name = "Manual Calibration"
        
        # Validation state
        self.homography = None
        self.reprojection_errors = {}  # label -> error in pixels
        self.show_spiderweb = False
        
        logger.info(f"ManualCalibrator initialized with {len(self.control_points)} control points")
    
    def calibrate(self, image: np.ndarray) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """
        Run interactive calibration to collect control point correspondences.
        
        Displays the image and prompts the user to click on each control point.
        Returns when minimum 4 points are collected and user confirms.
        
        Args:
            image: Camera image (BGR)
        
        Returns:
            List of ((u, v), (x, y)) point pairs where:
            - (u, v) are pixel coordinates
            - (x, y) are board coordinates in millimeters
        """
        self.current_image = image.copy()
        self.clicked_points = {}
        self.current_point_index = 0
        
        # Create window and set mouse callback
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)
        
        logger.info("Starting interactive calibration")
        logger.info("Click on each control point as prompted")
        logger.info("Press 'd' to delete last point, 's' to toggle spiderweb, 'q' to finish (min 4 points)")
        
        while True:
            # Update homography if we have enough points
            if len(self.clicked_points) >= 4:
                self._compute_preliminary_homography()
            
            # Draw current state
            display_image = self._draw_ui()
            cv2.imshow(self.window_name, display_image)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                # Finish calibration
                if len(self.clicked_points) >= 4:
                    logger.info(f"Calibration complete with {len(self.clicked_points)} points")
                    break
                else:
                    logger.warning(f"Need at least 4 points (have {len(self.clicked_points)})")
            
            elif key == ord('d'):
                # Delete last point
                if self.clicked_points:
                    last_label = list(self.clicked_points.keys())[-1]
                    del self.clicked_points[last_label]
                    self.current_point_index = max(0, self.current_point_index - 1)
                    self.homography = None  # Invalidate homography
                    logger.info(f"Deleted point {last_label}")
            
            elif key == ord('s'):
                # Toggle spiderweb overlay
                self.show_spiderweb = not self.show_spiderweb
                logger.info(f"Spiderweb overlay: {'ON' if self.show_spiderweb else 'OFF'}")
        
        cv2.destroyWindow(self.window_name)
        
        # Build point pairs
        point_pairs = []
        for label, pixel_coords in self.clicked_points.items():
            # Find board coordinates for this label
            board_coords = None
            for cp_label, cp_coords in self.control_points:
                if cp_label == label:
                    board_coords = cp_coords
                    break
            
            if board_coords is not None:
                point_pairs.append((pixel_coords, board_coords))
        
        logger.info(f"Returning {len(point_pairs)} point pairs")
        return point_pairs
    
    def _mouse_callback(self, event, x, y, flags, param):
        """Handle mouse clicks for control point selection."""
        if event == cv2.EVENT_LBUTTONDOWN:
            # Get current control point to click
            if self.current_point_index < len(self.control_points):
                label, board_coords = self.control_points[self.current_point_index]
                
                # Record click
                self.clicked_points[label] = (float(x), float(y))
                logger.info(f"Clicked {label} at ({x}, {y})")
                
                # Move to next point
                self.current_point_index += 1
    
    def _compute_preliminary_homography(self):
        """
        Compute preliminary homography from current clicked points.
        
        This is used for visual validation via spiderweb overlay and
        reprojection error computation.
        """
        if len(self.clicked_points) < 4:
            self.homography = None
            return
        
        # Build point pairs
        image_points = []
        board_points = []
        
        for label, pixel_coords in self.clicked_points.items():
            # Find board coordinates for this label
            for cp_label, cp_coords in self.control_points:
                if cp_label == label:
                    image_points.append(pixel_coords)
                    board_points.append(cp_coords)
                    break
        
        # Compute homography
        image_pts = np.array(image_points, dtype=np.float32)
        board_pts = np.array(board_points, dtype=np.float32)
        
        try:
            H, mask = cv2.findHomography(
                image_pts,
                board_pts,
                method=cv2.RANSAC,
                ransacReprojThreshold=5.0
            )
            
            if H is not None:
                self.homography = H
                self._compute_reprojection_errors(image_pts, board_pts, H)
            else:
                self.homography = None
                logger.warning("Homography computation returned None")
        
        except Exception as e:
            logger.error(f"Error computing homography: {e}")
            self.homography = None
    
    def _compute_reprojection_errors(
        self, 
        image_points: np.ndarray, 
        board_points: np.ndarray, 
        homography: np.ndarray
    ):
        """
        Compute reprojection error for each point.
        
        Args:
            image_points: Nx2 array of pixel coordinates
            board_points: Nx2 array of board coordinates
            homography: 3x3 homography matrix (image -> board)
        """
        self.reprojection_errors = {}
        
        # Homography maps image -> board, so we need inverse to project board -> image
        H_inv = np.linalg.inv(homography)
        
        # Project board points back to image using inverse homography
        board_h = np.hstack([board_points, np.ones((len(board_points), 1))])
        projected_h = (H_inv @ board_h.T).T
        projected = projected_h[:, :2] / projected_h[:, 2:3]
        
        # Compute errors
        errors = np.linalg.norm(image_points - projected, axis=1)
        
        # Store errors by label
        labels = list(self.clicked_points.keys())
        for i, label in enumerate(labels):
            self.reprojection_errors[label] = float(errors[i])
    
    def _draw_ui(self) -> np.ndarray:
        """
        Draw UI overlay showing control points and instructions.
        
        Returns:
            Image with UI overlay
        """
        display = self.current_image.copy()
        
        # Draw spiderweb overlay if enabled and homography available
        if self.show_spiderweb and self.homography is not None:
            spiderweb = self.board_geometry.generate_spiderweb(self.homography)
            display = self.board_geometry.draw_spiderweb(
                display, 
                spiderweb, 
                color=(0, 255, 255),
                thickness=1
            )
        
        # Draw clicked points
        for label, (u, v) in self.clicked_points.items():
            # Determine color based on reprojection error
            error = self.reprojection_errors.get(label, 0.0)
            if error > 10.0:
                color = (0, 0, 255)  # Red for outliers
            else:
                color = (0, 255, 0)  # Green for good points
            
            # Draw point
            cv2.circle(display, (int(u), int(v)), 5, color, -1)
            
            # Draw label with error
            if error > 0:
                label_text = f"{label} ({error:.1f}px)"
            else:
                label_text = label
            
            cv2.putText(
                display,
                label_text,
                (int(u) + 10, int(v) - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1
            )
        
        # Draw prompt for next point
        if self.current_point_index < len(self.control_points):
            label, board_coords = self.control_points[self.current_point_index]
            prompt = f"Click on: {label}"
            cv2.putText(
                display,
                prompt,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2
            )
        else:
            prompt = "All points collected! Press 'q' to finish"
            cv2.putText(
                display,
                prompt,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )
        
        # Draw instructions
        instructions = [
            f"Points: {len(self.clicked_points)}/{len(self.control_points)} (min 4)",
            "Press 'd' to delete last point",
            "Press 's' to toggle spiderweb overlay",
            "Press 'q' to finish"
        ]
        
        # Add reprojection error stats if available
        if self.reprojection_errors:
            errors = list(self.reprojection_errors.values())
            avg_error = np.mean(errors)
            max_error = np.max(errors)
            instructions.append(f"Avg error: {avg_error:.2f}px, Max: {max_error:.2f}px")
        
        y_offset = 60
        for instruction in instructions:
            cv2.putText(
                display,
                instruction,
                (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1
            )
            y_offset += 25
        
        return display
