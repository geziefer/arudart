"""
Manual calibration using interactive control point selection.

This module provides an interactive UI for clicking known wire intersection
points on the dartboard to establish pixel-to-board coordinate correspondences.
Includes a zoom overlay for precise clicking.
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
    
    The user clicks on known wire intersection points (where sector boundary
    wires cross ring wires) and the system records the pixel-to-board
    coordinate correspondences. A zoom overlay helps with precise clicking.
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
        self.mouse_x = 0
        self.mouse_y = 0
        self.window_name = "Manual Calibration"
        
        # Validation state
        self.homography = None
        self.reprojection_errors = {}  # label -> error in pixels
        self.show_spiderweb = False
        self.aborted = False  # True if user pressed ESC to abort

        logger.info(f"ManualCalibrator initialized with {len(self.control_points)} control points")
    
    def calibrate(self, image: np.ndarray) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """
        Run interactive calibration to collect control point correspondences.
        
        Displays the image and prompts the user to click on each wire
        intersection point. A 4x zoom overlay helps with precise clicking.
        Returns when user presses 'q' (with >= 4 points) or ESC (abort).
        
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
        self.aborted = False
        self._points_changed = False
        
        # Create window and set mouse callback
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)
        
        logger.info("Starting interactive calibration")
        logger.info("Click on each wire intersection as prompted")
        logger.info("Keys: 'd'=delete last, 'q'=finish, ESC=abort")
        
        while True:
            # Update homography only when points change
            if len(self.clicked_points) >= 4 and self._points_changed:
                self._compute_preliminary_homography()
                self._points_changed = False
            
            # Draw current state
            display_image = self._draw_ui()
            cv2.imshow(self.window_name, display_image)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == 27:  # ESC - always quit immediately
                logger.info("Calibration aborted by user (ESC)")
                self.aborted = True
                break
            
            elif key == ord('q'):
                if len(self.clicked_points) >= 4:
                    logger.info(f"Calibration complete with {len(self.clicked_points)} points")
                else:
                    logger.warning(
                        f"Exiting with only {len(self.clicked_points)} points "
                        f"(minimum 4 needed for homography)"
                    )
                    self.aborted = True
                break
            
            elif key == ord('d'):
                # Delete last point
                if self.clicked_points:
                    last_label = list(self.clicked_points.keys())[-1]
                    del self.clicked_points[last_label]
                    self.current_point_index = max(0, self.current_point_index - 1)
                    self.homography = None
                    self._points_changed = True
                    logger.info(f"Deleted point {last_label}")
        
        cv2.destroyWindow(self.window_name)
        
        # Build point pairs
        point_pairs = []
        for label, pixel_coords in self.clicked_points.items():
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
        """Handle mouse events: track position and record clicks."""
        self.mouse_x = x
        self.mouse_y = y
        
        if event == cv2.EVENT_LBUTTONDOWN:
            if self.current_point_index < len(self.control_points):
                label, board_coords = self.control_points[self.current_point_index]
                self.clicked_points[label] = (float(x), float(y))
                logger.info(f"Clicked {label} at ({x}, {y})")
                self.current_point_index += 1
                self._points_changed = True

    def _compute_preliminary_homography(self):
        """Compute preliminary homography from current clicked points."""
        if len(self.clicked_points) < 4:
            self.homography = None
            return
        
        image_points = []
        board_points = []
        
        for label, pixel_coords in self.clicked_points.items():
            for cp_label, cp_coords in self.control_points:
                if cp_label == label:
                    image_points.append(pixel_coords)
                    board_points.append(cp_coords)
                    break
        
        image_pts = np.array(image_points, dtype=np.float32)
        board_pts = np.array(board_points, dtype=np.float32)
        
        try:
            H, mask = cv2.findHomography(
                image_pts, board_pts,
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
        """Compute reprojection error for each point."""
        self.reprojection_errors = {}
        
        H_inv = np.linalg.inv(homography)
        board_h = np.hstack([board_points, np.ones((len(board_points), 1))])
        projected_h = (H_inv @ board_h.T).T
        projected = projected_h[:, :2] / projected_h[:, 2:3]
        errors = np.linalg.norm(image_points - projected, axis=1)
        
        labels = list(self.clicked_points.keys())
        for i, label in enumerate(labels):
            self.reprojection_errors[label] = float(errors[i])

    def _draw_zoom_overlay(self, display: np.ndarray) -> None:
        """
        Draw a 4x magnified zoom inset in the top-right corner.
        
        Shows the area around the current mouse position with a crosshair
        for precise wire intersection clicking.
        
        Args:
            display: Image to draw on (modified in-place)
        """
        zoom_size = 150
        zoom_factor = 4
        roi_half = zoom_size // (zoom_factor * 2)  # half-size of source ROI
        
        # Extract ROI around mouse position (clamped to image bounds)
        h, w = self.current_image.shape[:2]
        x1 = max(0, self.mouse_x - roi_half)
        y1 = max(0, self.mouse_y - roi_half)
        x2 = min(w, self.mouse_x + roi_half)
        y2 = min(h, self.mouse_y + roi_half)
        
        roi = self.current_image[y1:y2, x1:x2]
        if roi.size == 0:
            return
        
        zoomed = cv2.resize(roi, (zoom_size, zoom_size), interpolation=cv2.INTER_LINEAR)
        
        # Draw crosshair in center of zoomed view
        c = zoom_size // 2
        cv2.line(zoomed, (c - 30, c), (c + 30, c), (0, 255, 255), 2)
        cv2.line(zoomed, (c, c - 30), (c, c + 30), (0, 255, 255), 2)
        cv2.circle(zoomed, (c, c), 3, (0, 255, 255), -1)
        
        # White border
        cv2.rectangle(zoomed, (0, 0), (zoom_size - 1, zoom_size - 1), (255, 255, 255), 2)
        
        # Place in top-right corner
        margin = 10
        y_off = margin
        x_off = display.shape[1] - zoom_size - margin
        display[y_off:y_off + zoom_size, x_off:x_off + zoom_size] = zoomed
        
        # Label
        cv2.putText(
            display, "4x ZOOM", (x_off, y_off - 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2
        )


    def generate_spiderweb_overlay(self, image: np.ndarray, homography: np.ndarray) -> np.ndarray:
        """
        Generate an image with spiderweb overlay and clicked control points.

        Used after calibration is complete to show the result for review.

        Args:
            image: Original camera image (BGR)
            homography: 3x3 homography matrix (image->board)

        Returns:
            Image with spiderweb and control points drawn
        """
        spiderweb = self.board_geometry.generate_spiderweb(homography)
        overlay = self.board_geometry.draw_spiderweb(
            image.copy(), spiderweb, color=(0, 255, 255), thickness=1
        )

        # Draw clicked control points
        for label, (u, v) in self.clicked_points.items():
            error = self.reprojection_errors.get(label, 0.0)
            color = (0, 0, 255) if error > 10.0 else (0, 255, 0)
            cv2.circle(overlay, (int(u), int(v)), 5, color, -1)
            label_text = f"{label} ({error:.1f}px)" if error > 0 else label
            cv2.putText(
                overlay, label_text, (int(u) + 10, int(v) - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1
            )

        # Add summary text
        if self.reprojection_errors:
            errors = list(self.reprojection_errors.values())
            summary = f"Points: {len(self.clicked_points)} | Avg err: {np.mean(errors):.1f}px | Max: {np.max(errors):.1f}px"
            cv2.putText(
                overlay, summary, (10, overlay.shape[0] - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
            )

        return overlay


    def _draw_ui(self) -> np.ndarray:
        """
        Draw UI overlay showing control points, instructions, and zoom.
        
        Returns:
            Image with UI overlay
        """
        display = self.current_image.copy()
        
        # Draw crosshair at mouse position
        cv2.line(display, (self.mouse_x - 20, self.mouse_y),
                 (self.mouse_x + 20, self.mouse_y), (0, 255, 255), 1)
        cv2.line(display, (self.mouse_x, self.mouse_y - 20),
                 (self.mouse_x, self.mouse_y + 20), (0, 255, 255), 1)
        
        # Draw clicked points
        for label, (u, v) in self.clicked_points.items():
            error = self.reprojection_errors.get(label, 0.0)
            color = (0, 0, 255) if error > 10.0 else (0, 255, 0)
            
            cv2.circle(display, (int(u), int(v)), 5, color, -1)
            
            label_text = f"{label} ({error:.1f}px)" if error > 0 else label
            cv2.putText(
                display, label_text, (int(u) + 10, int(v) - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
            )
        
        # Draw prompt for next point
        if self.current_point_index < len(self.control_points):
            label, board_coords = self.control_points[self.current_point_index]
            # Find the description from BoardGeometry
            description = label
            for cp_entry in self.board_geometry.CONTROL_POINTS:
                if cp_entry[0] == label:
                    description = cp_entry[3]
                    break
            prompt = f"Click: {description}"
            cv2.putText(
                display, prompt, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2
            )
        else:
            cv2.putText(
                display, "All points collected! Press 'q' to finish", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
            )
        
        # Draw instructions
        instructions = [
            f"Points: {len(self.clicked_points)}/{len(self.control_points)} (min 4)",
            "'d'=delete last  'q'=finish  ESC=abort",
        ]
        if self.reprojection_errors:
            errors = list(self.reprojection_errors.values())
            instructions.append(
                f"Avg error: {np.mean(errors):.2f}px, Max: {np.max(errors):.2f}px"
            )
        
        y_offset = 60
        for instruction in instructions:
            cv2.putText(
                display, instruction, (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1
            )
            y_offset += 25
        
        # Draw zoom overlay last (on top of everything)
        self._draw_zoom_overlay(display)
        
        return display
