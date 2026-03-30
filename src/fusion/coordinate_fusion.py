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
        self.outlier_threshold_mm: float = fusion_cfg.get("outlier_threshold_mm", 25.0)
        self.min_confidence: float = fusion_cfg.get("min_confidence", 0.3)
        self.pairwise_rejection_mm: float = fusion_cfg.get("pairwise_rejection_mm", 20.0)
        self.angular_falloff: float = fusion_cfg.get("angular_falloff", 1.0)
        self.min_angular_weight: float = 0.1

        # Camera anchor angles: TOML uses string keys like "cam0", config stores as int keys
        raw_anchors = fusion_cfg.get("camera_anchors", None)
        if raw_anchors is not None:
            self.camera_anchors: dict[int, float] = {
                int(k.replace("cam", "")): float(v) for k, v in raw_anchors.items()
            }
        else:
            self.camera_anchors = {0: 81, 1: 257, 2: 153}
            logger.warning(
                "camera_anchors not configured in [fusion]; using defaults %s",
                self.camera_anchors,
            )

    def fuse_detections(
        self, detections: list[dict]
    ) -> tuple[float, float, float, list[int]] | None:
        """Fuse multiple camera detections into a single position.

        Uses a two-pass strategy: first confidence-only weighted average to
        estimate board angle, then angular+confidence weighted average for
        the final fused position.

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

        # Step 3: Outlier rejection — route by camera count
        if len(valid) == 2:
            inliers = self.reject_outliers_pairwise(valid)
        else:
            # 3+ cameras
            inliers = self.reject_outliers(valid)
            if len(inliers) == 0:
                # Fallback: use highest-confidence detection from valid
                best = max(valid, key=lambda d: d["confidence"])
                logger.warning(
                    "All detections rejected as outliers; falling back to "
                    "highest-confidence detection from camera %d (conf=%.2f)",
                    best["camera_id"], best["confidence"],
                )
                inliers = [best]

        # Step 4: Single inlier — return directly (no angular weighting needed)
        if len(inliers) == 1:
            d = inliers[0]
            x, y = d["board"]
            return (x, y, d["confidence"], [d["camera_id"]])

        # Step 5: Two-pass fusion for 2+ inliers
        # Pass 1: confidence-only weighted average
        px, py = self.compute_weighted_average(inliers)

        # Compute board angle from preliminary position
        board_angle = math.atan2(py, px)

        # Compute angular weights and build combined weights
        angular_weights = {}
        combined_weights = {}
        for d in inliers:
            aw = self.compute_angular_weight(board_angle, d["camera_id"])
            angular_weights[id(d)] = aw
            combined_weights[id(d)] = d["confidence"] * aw

        # If all angular weights < min_angular_weight: fall back to confidence-only
        if all(aw < self.min_angular_weight for aw in angular_weights.values()):
            logger.debug(
                "All angular weights below %.2f; falling back to confidence-only weighting",
                self.min_angular_weight,
            )
            combined_weights = {id(d): d["confidence"] for d in inliers}

        # Pass 2: angular+confidence weighted average
        fx, fy = self.compute_weighted_average(inliers, weights=combined_weights)

        combined_confidence = sum(d["confidence"] for d in inliers) / len(inliers)
        cameras_used = [d["camera_id"] for d in inliers]

        # Log per-detection diagnostics
        for d in inliers:
            aw = angular_weights[id(d)]
            anchor_deg = self.camera_anchors.get(d["camera_id"], None)
            if anchor_deg is not None:
                anchor_rad = math.radians(anchor_deg)
                delta = abs(board_angle - anchor_rad)
                delta = min(delta, 2 * math.pi - delta)
                ang_dist_deg = math.degrees(delta)
            else:
                ang_dist_deg = float("nan")
            logger.debug(
                "Camera %d: angular_dist=%.1f° angular_weight=%.4f "
                "confidence=%.2f final_weight=%.4f",
                d["camera_id"], ang_dist_deg, aw,
                d["confidence"], combined_weights[id(d)],
            )

        logger.info(
            "Fused %d cameras: (%.1f, %.1f) conf=%.2f cameras=%s",
            len(inliers), fx, fy, combined_confidence, cameras_used,
        )
        return (fx, fy, combined_confidence, cameras_used)


    def reject_outliers(self, detections: list[dict]) -> list[dict]:
        """Reject detections that are far from the median position.

        Computes the median X and Y across all detections, then keeps only
        those within outlier_threshold_mm of the median.

        Args:
            detections: List of detection dicts with 'board' and 'camera_id'.

        Returns:
            List of inlier detections.
        """
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

    def reject_outliers_pairwise(self, detections: list[dict]) -> list[dict]:
        """Reject the lower-confidence detection when two detections disagree.

        For exactly 2 detections, computes the Euclidean distance between their
        board positions. If the distance exceeds the pairwise rejection threshold,
        the detection with lower confidence is discarded.

        Args:
            detections: List of exactly 2 detection dicts with 'board',
                'confidence', and 'camera_id'.

        Returns:
            List of 1 or 2 inlier detections.
        """
        d0, d1 = detections
        dx = d0["board"][0] - d1["board"][0]
        dy = d0["board"][1] - d1["board"][1]
        dist = math.sqrt(dx * dx + dy * dy)

        if dist <= self.pairwise_rejection_mm:
            return [d0, d1]

        # Discard the lower-confidence detection
        if d0["confidence"] >= d1["confidence"]:
            rejected, kept = d1, d0
        else:
            rejected, kept = d0, d1

        logger.info(
            "Pairwise rejection: camera %d rejected (dist=%.1fmm, threshold=%.1f)",
            rejected["camera_id"], dist, self.pairwise_rejection_mm,
        )
        return [kept]

    def compute_angular_weight(self, board_angle_rad: float, camera_id: int) -> float:
        """Compute angular proximity weight for a camera given a board angle.

        Uses cosine-based falloff from the camera's anchor angle. Weight is 1.0
        when the dart is at the camera's anchor angle and approaches 0.0 at 180° away.

        Args:
            board_angle_rad: Estimated board angle of the dart in radians.
            camera_id: Camera identifier to look up anchor angle.

        Returns:
            Angular weight in [0.0, 1.0].
        """
        if camera_id not in self.camera_anchors:
            logger.warning(
                "camera_id %d not in camera_anchors; using neutral weight 0.5",
                camera_id,
            )
            return 0.5

        anchor_deg = self.camera_anchors[camera_id]
        anchor_rad = math.radians(anchor_deg)
        delta = abs(board_angle_rad - anchor_rad)
        delta = min(delta, 2 * math.pi - delta)  # shortest arc
        weight = ((1 + math.cos(delta)) / 2) ** self.angular_falloff
        return max(weight, 0.0)

    def compute_weighted_average(
        self, detections: list[dict], weights: dict | None = None
    ) -> tuple[float, float]:
        """Compute weighted average position.

        If weights is None, uses confidence-only weighting (backward compatible).
        If weights is provided, uses weights[id(d)] as the weight for each detection.
        Falls back to simple arithmetic mean if total weight is zero.

        Args:
            detections: List of detection dicts with 'board' and 'confidence'.
            weights: Optional dict mapping id(d) -> weight for each detection.
                If None, each detection's confidence is used as its weight.

        Returns:
            Tuple of (weighted_x, weighted_y).
        """
        if weights is None:
            weights = {id(d): d["confidence"] for d in detections}

        total_w = sum(weights[id(d)] for d in detections)

        if total_w == 0:
            logger.warning(
                "Total weight is zero; falling back to simple arithmetic mean"
            )
            n = len(detections)
            wx = sum(d["board"][0] for d in detections) / n
            wy = sum(d["board"][1] for d in detections) / n
            return (wx, wy)

        wx = sum(d["board"][0] * weights[id(d)] for d in detections) / total_w
        wy = sum(d["board"][1] * weights[id(d)] for d in detections) / total_w

        return (wx, wy)
