#!/usr/bin/env python3
"""
Calibration verification script for ARU-DART.

Interactive tool to verify calibration accuracy by clicking known board
positions and comparing transformed coordinates against ground truth.

Usage:
    # Live camera
    python calibration/verify_calibration.py --camera 0

    # From saved image
    python calibration/verify_calibration.py --camera 0 --from-image data/testimages/BS/BS10_cam0_pre.jpg

Controls:
    Click    - Mark a test point (cycles through predefined positions)
    SPACE    - Skip current test point
    s        - Toggle spiderweb overlay
    ESC/q    - Finish and show results
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.calibration import BoardGeometry, CoordinateMapper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Test points: (label, sector, ring_type) for BoardGeometry.get_board_coords()
VERIFICATION_POINTS = [
    ("Bull", None, "bull"),
    ("T20 center", 20, "triple"),
    ("T1 center", 1, "triple"),
    ("T5 center", 5, "triple"),
    ("T19 center", 19, "triple"),
    ("T6 center", 6, "triple"),
    ("T11 center", 11, "triple"),
    ("D20 center", 20, "double"),
    ("D1 center", 1, "double"),
    ("D5 center", 5, "double"),
    ("D19 center", 19, "double"),
    ("D6 center", 6, "double"),
    ("D11 center", 11, "double"),
]


class VerificationUI:
    """Interactive UI for clicking verification test points."""

    def __init__(
        self,
        camera_id: int,
        frame: np.ndarray,
        mapper: CoordinateMapper,
        board_geometry: BoardGeometry,
    ):
        self.camera_id = camera_id
        self.frame = frame
        self.mapper = mapper
        self.board_geometry = board_geometry

        self.current_index = 0
        self.results = []  # (label, expected_xy, measured_xy, error_mm)
        self.skipped = []
        self.click_pos = None
        self.show_spiderweb = True
        self.mouse_x = 0
        self.mouse_y = 0

    def _mouse_callback(self, event, x, y, flags, param):
        self.mouse_x = x
        self.mouse_y = y
        if event == cv2.EVENT_LBUTTONDOWN:
            self.click_pos = (x, y)

    def run(self) -> list[dict]:
        """Run interactive verification. Returns list of result dicts."""
        window = f"Verify Calibration - Camera {self.camera_id}"
        cv2.namedWindow(window)
        cv2.setMouseCallback(window, self._mouse_callback)

        while self.current_index < len(VERIFICATION_POINTS):
            label, sector, ring_type = VERIFICATION_POINTS[self.current_index]
            expected = self.board_geometry.get_board_coords(sector, ring_type)

            display = self._draw_ui(label, expected)
            cv2.imshow(window, display)

            key = cv2.waitKey(30) & 0xFF

            if key == 27 or key == ord('q'):
                break
            elif key == ord(' '):
                self.skipped.append(label)
                logger.info(f"Skipped: {label}")
                self.current_index += 1
            elif key == ord('s'):
                self.show_spiderweb = not self.show_spiderweb

            if self.click_pos is not None:
                u, v = self.click_pos
                self.click_pos = None

                board_result = self.mapper.map_to_board(
                    self.camera_id, float(u), float(v)
                )

                if board_result is not None and expected is not None:
                    mx, my = board_result
                    ex, ey = expected
                    error = np.sqrt((mx - ex) ** 2 + (my - ey) ** 2)

                    self.results.append({
                        "label": label,
                        "expected_mm": (ex, ey),
                        "measured_mm": (round(mx, 2), round(my, 2)),
                        "pixel": (u, v),
                        "error_mm": round(error, 2),
                    })

                    logger.info(
                        f"{label}: expected ({ex:.1f}, {ey:.1f}), "
                        f"measured ({mx:.1f}, {my:.1f}), "
                        f"error {error:.2f}mm"
                    )
                else:
                    logger.warning(
                        f"{label}: transform failed at pixel ({u}, {v})"
                    )
                    self.results.append({
                        "label": label,
                        "expected_mm": expected,
                        "measured_mm": None,
                        "pixel": (u, v),
                        "error_mm": None,
                    })

                self.current_index += 1

        cv2.destroyWindow(window)
        return self.results

    def _draw_zoom_overlay(self, display: np.ndarray) -> None:
        """Draw a 4x magnified zoom inset with crosshair in top-right corner."""
        zoom_size = 150
        zoom_factor = 4
        roi_half = zoom_size // (zoom_factor * 2)

        h, w = self.frame.shape[:2]
        x1 = max(0, self.mouse_x - roi_half)
        y1 = max(0, self.mouse_y - roi_half)
        x2 = min(w, self.mouse_x + roi_half)
        y2 = min(h, self.mouse_y + roi_half)

        roi = self.frame[y1:y2, x1:x2]
        if roi.size == 0:
            return

        zoomed = cv2.resize(roi, (zoom_size, zoom_size), interpolation=cv2.INTER_LINEAR)

        c = zoom_size // 2
        cv2.line(zoomed, (c - 30, c), (c + 30, c), (0, 255, 255), 2)
        cv2.line(zoomed, (c, c - 30), (c, c + 30), (0, 255, 255), 2)
        cv2.circle(zoomed, (c, c), 3, (0, 255, 255), -1)

        cv2.rectangle(zoomed, (0, 0), (zoom_size - 1, zoom_size - 1), (255, 255, 255), 2)

        margin = 10
        y_off = margin
        x_off = display.shape[1] - zoom_size - margin
        display[y_off:y_off + zoom_size, x_off:x_off + zoom_size] = zoomed

        cv2.putText(
            display, "4x ZOOM", (x_off, y_off - 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2
        )

    def _draw_ui(self, label: str, expected: tuple[float, float] | None) -> np.ndarray:
        """Draw the verification UI frame with overlay and instructions."""
        display = self.frame.copy()

        # Draw crosshair at mouse position
        cv2.line(display, (self.mouse_x - 20, self.mouse_y),
                 (self.mouse_x + 20, self.mouse_y), (0, 255, 255), 1)
        cv2.line(display, (self.mouse_x, self.mouse_y - 20),
                 (self.mouse_x, self.mouse_y + 20), (0, 255, 255), 1)

        # Draw spiderweb overlay if enabled and mapper has homography
        if self.show_spiderweb:
            H = None
            with self.mapper._lock:
                if self.camera_id in self.mapper._homographies:
                    H = self.mapper._homographies[self.camera_id].copy()
            if H is not None:
                spiderweb = self.board_geometry.generate_spiderweb(H)
                display = self.board_geometry.draw_spiderweb(
                    display, spiderweb, color=(0, 255, 255), thickness=1
                )

        # Draw previously clicked results
        for r in self.results:
            px, py = r["pixel"]
            err = r["error_mm"]
            if err is not None:
                if err < 5:
                    c = (0, 200, 0)
                elif err < 10:
                    c = (0, 200, 200)
                else:
                    c = (0, 0, 200)
                cv2.circle(display, (px, py), 6, c, -1)
                cv2.putText(
                    display, f"{err:.1f}mm",
                    (px + 10, py - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, c, 1,
                )
            else:
                cv2.circle(display, (px, py), 6, (0, 0, 200), -1)
                cv2.putText(
                    display, "FAIL",
                    (px + 10, py - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 200), 1,
                )

        # Draw prompt for current point (same style as manual calibrator)
        prompt = f"Click: {label}  ({self.current_index + 1}/{len(VERIFICATION_POINTS)})"
        cv2.putText(
            display, prompt, (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2,
        )

        # Draw instructions and stats
        instructions = [
            "SPACE=skip  s=spiderweb  q/ESC=finish",
        ]
        if expected is not None:
            ex, ey = expected
            instructions.append(f"Expected: ({ex:.1f}, {ey:.1f}) mm")
        if self.results:
            errors = [r["error_mm"] for r in self.results if r["error_mm"] is not None]
            if errors:
                instructions.append(
                    f"Avg: {sum(errors)/len(errors):.1f}mm  "
                    f"Max: {max(errors):.1f}mm  "
                    f"Done: {len(self.results)}"
                )

        y_offset = 55
        for line in instructions:
            cv2.putText(
                display, line, (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
            )
            y_offset += 22

        # Draw zoom overlay last (on top of everything)
        self._draw_zoom_overlay(display)

        return display


def compute_statistics(results: list[dict]) -> dict:
    """
    Compute verification error statistics.

    Args:
        results: List of result dicts from VerificationUI.run()

    Returns:
        Dictionary with avg_error_mm, max_error_mm, num_measured,
        num_failed, per_point breakdown
    """
    errors = [r["error_mm"] for r in results if r["error_mm"] is not None]

    stats = {
        "num_measured": len(errors),
        "num_failed": sum(1 for r in results if r["error_mm"] is None),
        "num_total": len(results),
        "avg_error_mm": 0.0,
        "max_error_mm": 0.0,
        "min_error_mm": 0.0,
        "per_point": results,
    }

    if errors:
        stats["avg_error_mm"] = round(sum(errors) / len(errors), 2)
        stats["max_error_mm"] = round(max(errors), 2)
        stats["min_error_mm"] = round(min(errors), 2)

    return stats


def save_report(
    camera_id: int,
    stats: dict,
    skipped: list[str],
    output_path: Path,
):
    """
    Save verification report to JSON.

    Args:
        camera_id: Camera identifier
        stats: Statistics dict from compute_statistics()
        skipped: List of skipped point labels
        output_path: Path to write JSON report
    """
    report = {
        "camera_id": camera_id,
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "avg_error_mm": stats["avg_error_mm"],
            "max_error_mm": stats["max_error_mm"],
            "min_error_mm": stats["min_error_mm"],
            "num_measured": stats["num_measured"],
            "num_failed": stats["num_failed"],
            "num_skipped": len(skipped),
        },
        "skipped_points": skipped,
        "per_point": [],
    }

    for r in stats["per_point"]:
        entry = {
            "label": r["label"],
            "pixel": list(r["pixel"]),
            "error_mm": r["error_mm"],
        }
        if r["expected_mm"] is not None:
            entry["expected_mm"] = list(r["expected_mm"])
        if r["measured_mm"] is not None:
            entry["measured_mm"] = list(r["measured_mm"])
        report["per_point"].append(entry)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Saved verification report: {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify calibration accuracy for ARU-DART"
    )
    parser.add_argument(
        "--camera",
        type=int,
        choices=[0, 1, 2],
        required=True,
        help="Camera to verify (0, 1, or 2)",
    )
    parser.add_argument(
        "--from-image",
        type=str,
        help="Verify from saved image instead of live camera",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.toml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for verification report JSON",
    )

    args = parser.parse_args()

    # Load config
    with open(args.config, "rb") as f:
        config = tomllib.load(f)

    # Initialize mapper and geometry
    board_geometry = BoardGeometry()
    mapper = CoordinateMapper(config)

    if not mapper.is_calibrated(args.camera):
        logger.error(
            f"Camera {args.camera} is not calibrated. "
            "Run calibrate_manual.py first."
        )
        sys.exit(1)

    # Get frame
    if args.from_image:
        image_path = Path(args.from_image)
        if not image_path.exists():
            logger.error(f"Image not found: {image_path}")
            sys.exit(1)
        frame = cv2.imread(str(image_path))
        if frame is None:
            logger.error(f"Failed to load image: {image_path}")
            sys.exit(1)
        logger.info(f"Loaded image: {image_path}")
    else:
        from src.camera.camera_manager import CameraManager
        import time

        logger.info("Initializing cameras...")
        camera_manager = CameraManager(config)
        camera_manager.start_all()
        time.sleep(2.0)

        all_ids = sorted(camera_manager.get_camera_ids())
        if args.camera >= len(all_ids):
            logger.error(
                f"Camera {args.camera} not available "
                f"(only {len(all_ids)} detected)"
            )
            camera_manager.stop_all()
            sys.exit(1)

        device_id = all_ids[args.camera]
        
        # Retry frame capture (camera may need extra time)
        frame = None
        for attempt in range(5):
            frame = camera_manager.get_latest_frame(device_id)
            if frame is not None:
                break
            logger.info(f"Waiting for camera {args.camera} (attempt {attempt + 1}/5)...")
            time.sleep(0.5)
        
        camera_manager.stop_all()

        if frame is None:
            logger.error(f"Failed to capture frame from camera {args.camera}")
            sys.exit(1)

    # Run verification UI
    ui = VerificationUI(args.camera, frame, mapper, board_geometry)
    results = ui.run()

    if not results:
        logger.info("No points measured.")
        sys.exit(0)

    # Compute and display statistics
    stats = compute_statistics(results)

    logger.info("=== Verification Results ===")
    logger.info(f"Camera: {args.camera}")
    logger.info(f"Points measured: {stats['num_measured']}")
    logger.info(f"Points failed: {stats['num_failed']}")
    if ui.skipped:
        logger.info(f"Points skipped: {len(ui.skipped)}")
    logger.info(f"Average error: {stats['avg_error_mm']:.2f} mm")
    logger.info(f"Max error: {stats['max_error_mm']:.2f} mm")
    logger.info(f"Min error: {stats['min_error_mm']:.2f} mm")

    quality = "GOOD" if stats["avg_error_mm"] < 5 else "POOR"
    logger.info(f"Quality: {quality}")

    # Save report
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path("calibration") / f"verification_cam{args.camera}.json"

    save_report(args.camera, stats, ui.skipped, output_path)

    cv2.destroyAllWindows()
    sys.exit(0 if quality == "GOOD" else 1)


if __name__ == "__main__":
    main()
