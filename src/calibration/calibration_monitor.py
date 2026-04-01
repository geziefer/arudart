"""Calibration drift monitor.

Periodically checks if the board calibration has drifted by detecting
the bull center and comparing it to the expected position from the
current homography. Triggers full recalibration when drift exceeds
a threshold.
"""

import logging
import math
import time

import cv2
import numpy as np

from src.calibration.feature_detector import FeatureDetector

logger = logging.getLogger(__name__)

# Drift thresholds in pixels
DRIFT_WARN_PX = 5
DRIFT_RECAL_PX = 12


class CalibrationMonitor:
    """Monitor calibration drift via bull center detection.

    Compares the detected bull pixel position against the expected
    position (board origin mapped back through the homography).
    """

    def __init__(self, config: dict, coordinate_mapper, camera_ids: list[int]):
        self.config = config
        self.coordinate_mapper = coordinate_mapper
        self.camera_ids = camera_ids
        self.feature_detector = FeatureDetector(config)
        self.rounds_since_check = 0
        self.check_interval_rounds = 10
        self.consecutive_warnings = 0
        self.last_check_time = 0.0

    def should_check(self) -> bool:
        """Whether a drift check is due."""
        return self.rounds_since_check >= self.check_interval_rounds

    def on_round_complete(self) -> None:
        """Call after each round completes."""
        self.rounds_since_check += 1

    def check_drift(self, frames: dict) -> dict:
        """Run a quick bull drift check on current frames.

        Args:
            frames: Dict mapping camera_id to BGR frame (clean board).

        Returns:
            Dict with keys: needs_recalibration (bool),
            per_camera (dict of cam_id -> drift_px), message (str).
        """
        self.rounds_since_check = 0
        self.last_check_time = time.time()

        drifts = {}
        for cam_id in self.camera_ids:
            if cam_id not in frames:
                continue
            if not self.coordinate_mapper.is_calibrated(cam_id):
                continue

            frame = frames[cam_id]
            detected_bull = self.feature_detector.detect_bull_center(frame)
            if detected_bull is None:
                logger.warning("cam%d: bull not detected during drift check", cam_id)
                continue

            # Expected bull pixel: map board origin (0,0) back to image
            expected = self.coordinate_mapper.map_to_image(cam_id, 0.0, 0.0)
            if expected is None:
                continue

            dx = detected_bull[0] - expected[0]
            dy = detected_bull[1] - expected[1]
            drift = math.sqrt(dx * dx + dy * dy)
            drifts[cam_id] = drift

            logger.info(
                "cam%d drift check: detected=(%.0f,%.0f) expected=(%.0f,%.0f) drift=%.1fpx",
                cam_id, detected_bull[0], detected_bull[1],
                expected[0], expected[1], drift,
            )

        if not drifts:
            return {"needs_recalibration": False, "per_camera": {}, "message": "No cameras checked"}

        max_drift = max(drifts.values())
        max_cam = max(drifts, key=drifts.get)

        if max_drift >= DRIFT_RECAL_PX:
            self.consecutive_warnings = 0
            msg = "cam%d drift %.1fpx exceeds threshold - recalibration needed" % (max_cam, max_drift)
            logger.warning(msg)
            return {"needs_recalibration": True, "per_camera": drifts, "message": msg}

        if max_drift >= DRIFT_WARN_PX:
            self.consecutive_warnings += 1
            msg = "cam%d drift %.1fpx (warning %d/3)" % (max_cam, max_drift, self.consecutive_warnings)
            logger.warning(msg)
            if self.consecutive_warnings >= 3:
                self.consecutive_warnings = 0
                return {"needs_recalibration": True, "per_camera": drifts, "message": msg + " - recalibrating"}
            return {"needs_recalibration": False, "per_camera": drifts, "message": msg}

        self.consecutive_warnings = 0
        msg = "All cameras OK (max drift %.1fpx on cam%d)" % (max_drift, max_cam)
        logger.info(msg)
        return {"needs_recalibration": False, "per_camera": drifts, "message": msg}

    def run_recalibration(self, frames: dict) -> bool:
        """Run full auto-recalibration using current frames.

        Detects features, computes homography, saves to disk, and
        reloads the coordinate mapper.

        Args:
            frames: Dict mapping camera_id to BGR frame (clean board).

        Returns:
            True if recalibration succeeded for at least one camera.
        """
        from src.calibration.feature_matcher import FeatureMatcher
        from src.calibration.homography_calculator import HomographyCalculator

        logger.info("Starting auto-recalibration...")
        matcher = FeatureMatcher(self.config)
        homography_calc = HomographyCalculator(self.config)
        success_count = 0

        for cam_id in self.camera_ids:
            if cam_id not in frames:
                continue

            frame = frames[cam_id]
            try:
                detection = self.feature_detector.detect(frame)
                if detection.bull_center is None:
                    logger.warning("cam%d: bull not detected, skipping recalibration", cam_id)
                    continue

                point_pairs = matcher.match(detection)
                if len(point_pairs) < 4:
                    logger.warning("cam%d: only %d point pairs, need 4+", cam_id, len(point_pairs))
                    continue

                pixel_pts = [(pp.pixel_x, pp.pixel_y) for pp in point_pairs]
                board_pts = [(pp.board_x, pp.board_y) for pp in point_pairs]

                H, inliers, error = homography_calc.compute(pixel_pts, board_pts)
                if H is None:
                    logger.warning("cam%d: homography computation failed", cam_id)
                    continue

                homography_calc.save(H, cam_id, len(inliers), len(point_pairs), error)
                logger.info(
                    "cam%d recalibrated: %d/%d inliers, error=%.2fmm",
                    cam_id, len(inliers), len(point_pairs), error,
                )
                success_count += 1

            except Exception as e:
                logger.error("cam%d recalibration failed: %s", cam_id, e)

        if success_count > 0:
            self.coordinate_mapper.reload_calibration()
            logger.info("Recalibration complete: %d/%d cameras updated", success_count, len(self.camera_ids))
            return True

        logger.warning("Recalibration failed for all cameras")
        return False
