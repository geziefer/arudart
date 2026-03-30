"""
Heatmap generation for the human feedback system.

Generates visual heatmaps showing detection accuracy across different
board regions. Supports filtering by ring type (single, double, triple)
and overlays accuracy data on a dartboard background.

Requirements: AC-7.5.4.1, AC-7.5.4.2, AC-7.5.4.3, AC-7.5.4.4, AC-7.5.4.5
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Board geometry (mm)
BOARD_RADIUS_MM = 170.0

# Image dimensions (pixels)
IMAGE_SIZE = 800

# Grid resolution for accuracy computation
GRID_RESOLUTION = 20

# Standard dartboard ring radii (mm) for overlay
RING_RADII_MM = {
    "double_bull": 6.35,
    "single_bull": 15.9,
    "inner_single": 99.0,
    "triple_inner": 99.0,
    "triple_outer": 107.0,
    "outer_single": 162.0,
    "double_inner": 162.0,
    "double_outer": 170.0,
}

# Sector angles (standard dartboard order, starting from top going clockwise)
SECTOR_ORDER = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]


def _mm_to_pixel(x_mm: float, y_mm: float) -> tuple[int, int]:
    """Convert board coordinates (mm) to pixel coordinates.

    Board center maps to the center of the image. Y is inverted so
    positive Y in mm goes upward on the board but downward in pixels.

    Args:
        x_mm: Board X coordinate in mm.
        y_mm: Board Y coordinate in mm.

    Returns:
        Tuple of (pixel_x, pixel_y).
    """
    scale = (IMAGE_SIZE / 2) / BOARD_RADIUS_MM
    px = int(IMAGE_SIZE / 2 + x_mm * scale)
    py = int(IMAGE_SIZE / 2 - y_mm * scale)
    return px, py



def assign_color(accuracy: Optional[float]) -> tuple[int, int, int]:
    """Assign a BGR color based on accuracy value.

    Args:
        accuracy: Accuracy as a float in [0, 1], or None if no data.

    Returns:
        BGR color tuple.
    """
    if accuracy is None:
        return (128, 128, 128)  # gray — no data
    if accuracy > 0.90:
        return (0, 255, 0)  # green
    if accuracy >= 0.70:
        return (0, 255, 255)  # yellow (BGR)
    return (0, 0, 255)  # red


class HeatmapGenerator:
    """Generate visual heatmaps of detection accuracy across the dartboard.

    Attributes:
        board_radius_mm: Radius of the dartboard in mm.
        grid_resolution: Number of cells along each axis of the grid.
    """

    def __init__(
        self,
        board_radius_mm: float = BOARD_RADIUS_MM,
        grid_resolution: int = GRID_RESOLUTION,
    ) -> None:
        self.board_radius_mm = board_radius_mm
        self.grid_resolution = grid_resolution

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_heatmap(
        self,
        feedback_list: list[dict],
        ring_filter: Optional[str] = None,
    ) -> np.ndarray:
        """Generate a heatmap image from feedback data.

        Args:
            feedback_list: List of feedback metadata dicts as returned by
                ``FeedbackStorage.load_all_feedback()``.
            ring_filter: Optional ring type filter — one of ``"single"``,
                ``"double"``, ``"triple"``, or ``None`` for all.

        Returns:
            Heatmap image as a numpy array in BGR format (800×800×3).
        """
        filtered = self._filter_by_ring(feedback_list, ring_filter)

        # Create blank image
        image = np.full((IMAGE_SIZE, IMAGE_SIZE, 3), 255, dtype=np.uint8)

        # Compute per-cell accuracy and paint grid
        self._paint_grid(image, filtered)

        # Draw dartboard overlay (rings + sector lines)
        self._draw_board_overlay(image)

        return image

    def save_heatmap(self, image: np.ndarray, output_path: str | Path) -> None:
        """Save a heatmap image to a PNG file.

        Args:
            image: Heatmap image (BGR numpy array).
            output_path: Destination file path.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), image)
        logger.info("Heatmap saved to: %s", path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_by_ring(
        feedback_list: list[dict], ring_filter: Optional[str]
    ) -> list[dict]:
        """Filter feedback entries by ring type.

        Args:
            feedback_list: Raw feedback list.
            ring_filter: Ring name or None.

        Returns:
            Filtered list.
        """
        if ring_filter is None:
            return feedback_list
        return [
            fb
            for fb in feedback_list
            if fb.get("actual_score", {}).get("ring") == ring_filter
        ]

    def _paint_grid(self, image: np.ndarray, feedback_list: list[dict]) -> None:
        """Paint accuracy-colored grid cells onto *image*."""
        half = self.board_radius_mm
        cell_mm = (2 * half) / self.grid_resolution
        scale = (IMAGE_SIZE / 2) / self.board_radius_mm

        for row in range(self.grid_resolution):
            for col in range(self.grid_resolution):
                # Cell center in mm
                cx_mm = -half + (col + 0.5) * cell_mm
                cy_mm = half - (row + 0.5) * cell_mm

                # Skip cells outside the board circle
                if math.hypot(cx_mm, cy_mm) > self.board_radius_mm:
                    continue

                # Find feedback entries whose actual position falls in this cell
                cell_entries = self._entries_in_cell(
                    feedback_list, cx_mm, cy_mm, cell_mm
                )

                if not cell_entries:
                    accuracy = None
                else:
                    correct = sum(
                        1 for fb in cell_entries if fb.get("is_correct")
                    )
                    accuracy = correct / len(cell_entries)

                color = assign_color(accuracy)

                # Pixel rectangle for this cell
                px_left = int(IMAGE_SIZE / 2 + (-half + col * cell_mm) * scale)
                px_top = int(IMAGE_SIZE / 2 - (half - row * cell_mm) * scale)
                px_right = int(IMAGE_SIZE / 2 + (-half + (col + 1) * cell_mm) * scale)
                px_bottom = int(
                    IMAGE_SIZE / 2 - (half - (row + 1) * cell_mm) * scale
                )

                cv2.rectangle(
                    image,
                    (px_left, px_top),
                    (px_right, px_bottom),
                    color,
                    cv2.FILLED,
                )

    @staticmethod
    def _entries_in_cell(
        feedback_list: list[dict],
        cx_mm: float,
        cy_mm: float,
        cell_mm: float,
    ) -> list[dict]:
        """Return feedback entries whose board position falls in the cell."""
        half_cell = cell_mm / 2.0
        result: list[dict] = []
        for fb in feedback_list:
            dart_hit = fb.get("dart_hit_event", {})
            board_coords = dart_hit.get("board_coordinates", {})
            x = board_coords.get("x_mm")
            y = board_coords.get("y_mm")
            if x is None or y is None:
                continue
            if abs(x - cx_mm) <= half_cell and abs(y - cy_mm) <= half_cell:
                result.append(fb)
        return result

    @staticmethod
    def _draw_board_overlay(image: np.ndarray) -> None:
        """Draw dartboard rings and sector lines on *image*."""
        center = (IMAGE_SIZE // 2, IMAGE_SIZE // 2)
        scale = (IMAGE_SIZE / 2) / BOARD_RADIUS_MM
        overlay_color = (0, 0, 0)  # black

        # Draw rings
        for radius_mm in RING_RADII_MM.values():
            r_px = int(radius_mm * scale)
            cv2.circle(image, center, r_px, overlay_color, 1)

        # Draw sector lines
        for i in range(20):
            angle_deg = i * 18.0 - 9.0  # offset so lines are between sectors
            angle_rad = math.radians(angle_deg - 90)  # -90 to start from top
            inner_r = int(RING_RADII_MM["single_bull"] * scale)
            outer_r = int(RING_RADII_MM["double_outer"] * scale)
            x1 = int(center[0] + inner_r * math.cos(angle_rad))
            y1 = int(center[1] + inner_r * math.sin(angle_rad))
            x2 = int(center[0] + outer_r * math.cos(angle_rad))
            y2 = int(center[1] + outer_r * math.sin(angle_rad))
            cv2.line(image, (x1, y1), (x2, y2), overlay_color, 1)
