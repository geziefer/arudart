"""
Coordinate fusion for multi-camera dart detections.

Combines per-camera dart tip detections into a single fused board coordinate
using confidence-weighted averaging and outlier rejection.
"""

import logging
import math
from statistics import median

logger = logging.getLogger(__name__)


class CoordinateFusion:
    """Fuse multiple camera detections into a single board coordinate.

    Uses confidence-weighted averaging with outlier rejection to combine
    detections from up to 3 cameras into a single best-estimate position.

    Args:
        config: Dictionary with 'fusion' section containing
            outlier_threshold_mm and min_confidence.
    """

    def __init__(self, config: dict) -> None:
        fusion_cfg = config.get("fusion", {})
        self.outlier_threshold_mm: float = fusion_cfg.get("outlier_threshold_mm", 50.0)
        self.min_confidence: float = fusion_cfg.get("min_confidence", 0.3)

    def fuse_detections(
        self, detections: list[dict]
    ) -> tuple[float, float, float, list[int]] | None:
        """Fuse multiple camera detections into a single position.

        Args:
            detections: List of detection dicts, each with keys:
                - camera_id: int
                - board: tuple (x, y) in mm
                - confidence: float in [0, 1]

        Returns:
            Tuple of (fused_x, fused_y, confidence, cameras_used) or None
            if no valid detections remain after filtering.
        """
        # Step 1: Filter by minimum confidence
        valid = [d for d in detections if d["confidence"] >= self.min_confidence]

        if not valid:
            logger.warning("No detections above min confidence %.2f", self.min_confidence)
            return None

        # Step 2: Single detection — return directly
        if len(valid) == 1:
            d = valid[0]
            x, y = d["board"]
            logger.info("Single camera detection from camera %d", d["camera_id"])
            return (x, y, d["confidence"], [d["camera_id"]])

        # Step 3: Multiple detections — outlier rejection + weighted average
        inliers = self.reject_outliers(valid)

        if not inliers:
            logger.warning("All detections rejected as outliers")
            return None

        wx, wy = self.compute_weighted_average(inliers)
        combined_confidence = sum(d["confidence"] for d in inliers) / len(inliers)
        cameras_used = [d["camera_id"] for d in inliers]

        logger.info(
            "Fused %d cameras: (%.1f, %.1f) conf=%.2f cameras=%s",
            len(inliers), wx, wy, combined_confidence, cameras_used,
        )
        return (wx, wy, combined_confidence, cameras_used)

    def reject_outliers(self, detections: list[dict]) -> list[dict]:
        """Reject detections that are far from the median position.

        Computes the median X and Y across all detections, then keeps only
        those within outlier_threshold_mm of the median.

        Special case: if ≤2 detections, all are kept (no rejection).

        Args:
            detections: List of detection dicts with 'board' and 'camera_id'.

        Returns:
            List of inlier detections.
        """
        if len(detections) <= 2:
            return detections

        xs = [d["board"][0] for d in detections]
        ys = [d["board"][1] for d in detections]
        median_x = median(xs)
        median_y = median(ys)

        inliers = []
        for d in detections:
            dx = d["board"][0] - median_x
            dy = d["board"][1] - median_y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= self.outlier_threshold_mm:
                inliers.append(d)
            else:
                logger.info(
                    "Rejected outlier from camera %d: dist=%.1fmm (threshold=%.1f)",
                    d["camera_id"], dist, self.outlier_threshold_mm,
                )

        return inliers

    def compute_weighted_average(
        self, detections: list[dict]
    ) -> tuple[float, float]:
        """Compute confidence-weighted average position.

        Weighted average: sum(coord * confidence) / sum(confidence)
        Applied independently to X and Y coordinates.

        Args:
            detections: List of detection dicts with 'board' and 'confidence'.

        Returns:
            Tuple of (weighted_x, weighted_y).
        """
        total_conf = sum(d["confidence"] for d in detections)

        wx = sum(d["board"][0] * d["confidence"] for d in detections) / total_conf
        wy = sum(d["board"][1] * d["confidence"] for d in detections) / total_conf

        return (wx, wy)
