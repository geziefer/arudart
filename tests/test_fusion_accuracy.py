"""
Unit tests for fusion accuracy improvements.

Tests pairwise rejection, tighter 3-camera threshold, angular weighting,
backward compatibility, and return type correctness.

**Validates: Requirements 1.1, 1.2, 2.1, 2.2, 2.4, 3.2, 3.3, 3.7, 6.1, 6.2, 6.4**
"""

import math

import pytest

from src.fusion.coordinate_fusion import CoordinateFusion


NEW_CONFIG = {
    "fusion": {
        "outlier_threshold_mm": 25.0,
        "min_confidence": 0.3,
        "pairwise_rejection_mm": 20.0,
        "angular_falloff": 1.0,
        "camera_anchors": {"cam0": 81, "cam1": 257, "cam2": 153},
    }
}


def make_detection(camera_id: int, x: float, y: float, confidence: float) -> dict:
    """Create a detection dict."""
    return {"camera_id": camera_id, "board": (x, y), "confidence": confidence}


class TestPairwiseRejection:
    """Tests for 2-camera pairwise outlier rejection."""

    def test_pairwise_rejection_lower_confidence_rejected(self) -> None:
        """Two detections 30mm apart: lower confidence rejected.

        **Validates: Requirements 1.1**
        """
        fusion = CoordinateFusion(NEW_CONFIG)
        d0 = make_detection(0, 0.0, 0.0, 0.9)
        d1 = make_detection(1, 30.0, 0.0, 0.6)

        result = fusion.reject_outliers_pairwise([d0, d1])

        assert len(result) == 1
        assert result[0]["camera_id"] == 0

    def test_pairwise_rejection_within_threshold_both_kept(self) -> None:
        """Two detections 15mm apart: both kept.

        **Validates: Requirements 1.2**
        """
        fusion = CoordinateFusion(NEW_CONFIG)
        d0 = make_detection(0, 0.0, 0.0, 0.9)
        d1 = make_detection(1, 15.0, 0.0, 0.6)

        result = fusion.reject_outliers_pairwise([d0, d1])

        assert len(result) == 2


class TestThreeCameraOutlierRejection:
    """Tests for tighter 3-camera median-based outlier rejection."""

    def test_tighter_3camera_threshold_rejects_30mm_outlier(self) -> None:
        """cam2 at 32mm from median rejected with 25mm threshold (would pass old 50mm).

        **Validates: Requirements 2.1, 2.2**
        """
        fusion = CoordinateFusion(NEW_CONFIG)
        d0 = make_detection(0, 0.0, 0.0, 0.8)
        d1 = make_detection(1, 2.0, 0.0, 0.8)
        d2 = make_detection(2, 32.0, 0.0, 0.8)

        # Median x = 2.0, median y = 0.0
        # cam2 distance from median = |32 - 2| = 30mm > 25mm threshold
        result = fusion.reject_outliers([d0, d1, d2])

        kept_ids = [d["camera_id"] for d in result]
        assert 2 not in kept_ids, "cam2 should be rejected (30mm > 25mm threshold)"
        assert 0 in kept_ids
        assert 1 in kept_ids

    def test_total_rejection_fallback_returns_highest_confidence(self) -> None:
        """All 3 detections >25mm from median → highest confidence returned.

        **Validates: Requirements 2.4**
        """
        fusion = CoordinateFusion(NEW_CONFIG)
        d0 = make_detection(0, -100.0, 0.0, 0.7)
        d1 = make_detection(1, 0.0, 100.0, 0.9)
        d2 = make_detection(2, 100.0, 0.0, 0.5)

        result = fusion.fuse_detections([d0, d1, d2])

        assert result is not None
        x, y, conf, cameras = result
        assert cameras == [1], "cam1 has highest confidence (0.9)"
        assert x == 0.0
        assert y == 100.0


class TestAngularWeight:
    """Tests for angular proximity weighting."""

    def test_angular_weight_at_known_angles(self) -> None:
        """Verify angular weight at 0°, 90°, and 180° from cam0 anchor (81°).

        **Validates: Requirements 3.2, 3.3**
        """
        fusion = CoordinateFusion(NEW_CONFIG)

        # Dart at 81° (same as cam0 anchor) → weight = 1.0
        w_same = fusion.compute_angular_weight(math.radians(81), 0)
        assert abs(w_same - 1.0) < 1e-9, f"Expected 1.0 at anchor angle, got {w_same}"

        # Dart at 261° (180° from cam0 anchor) → weight ≈ 0.0
        w_opposite = fusion.compute_angular_weight(math.radians(261), 0)
        assert abs(w_opposite) < 1e-9, f"Expected ≈0.0 at 180° away, got {w_opposite}"

        # Dart at 171° (90° from cam0 anchor) → weight = (1 + cos(90°)) / 2 = 0.5
        w_90 = fusion.compute_angular_weight(math.radians(171), 0)
        assert abs(w_90 - 0.5) < 1e-9, f"Expected 0.5 at 90° away, got {w_90}"

    def test_angular_weight_fallback_uses_confidence_only(self) -> None:
        """All cameras at 0° anchor, dart at 180° → all weights < 0.1 → fallback.

        **Validates: Requirements 3.7**
        """
        fallback_config = {
            "fusion": {
                "outlier_threshold_mm": 25.0,
                "min_confidence": 0.3,
                "pairwise_rejection_mm": 20.0,
                "angular_falloff": 1.0,
                "camera_anchors": {"cam0": 0, "cam1": 0, "cam2": 0},
            }
        }
        fusion = CoordinateFusion(fallback_config)

        # Two close detections at board angle ≈ 180° (negative x)
        d0 = make_detection(0, -50.0, 0.0, 0.8)
        d1 = make_detection(1, -52.0, 0.0, 0.7)

        result = fusion.fuse_detections([d0, d1])

        assert result is not None, "Fallback should prevent None from zero-weight crash"


class TestBackwardCompatibility:
    """Tests for backward compatibility with old config format."""

    def test_backward_compatibility_old_config(self) -> None:
        """Old config (no new keys) → defaults applied, fusion works.

        **Validates: Requirements 6.1, 6.2**
        """
        old_config = {"fusion": {"outlier_threshold_mm": 50.0, "min_confidence": 0.3}}
        fusion = CoordinateFusion(old_config)

        # Verify defaults for new parameters
        assert fusion.pairwise_rejection_mm == 20.0
        assert fusion.angular_falloff == 1.0
        assert fusion.camera_anchors == {0: 81, 1: 257, 2: 153}

        # Verify fusion still works with two close detections
        d0 = make_detection(0, 10.0, 10.0, 0.8)
        d1 = make_detection(1, 12.0, 11.0, 0.7)

        result = fusion.fuse_detections([d0, d1])
        assert result is not None


class TestReturnType:
    """Tests for return type correctness."""

    def test_return_type_always_correct(self) -> None:
        """fuse_detections returns (float, float, float, list) or None.

        **Validates: Requirements 6.4**
        """
        fusion = CoordinateFusion(NEW_CONFIG)

        # Empty list → None
        assert fusion.fuse_detections([]) is None

        # Single detection → tuple
        result = fusion.fuse_detections([make_detection(0, 10.0, 20.0, 0.8)])
        assert result is not None
        x, y, conf, cameras = result
        assert isinstance(x, float)
        assert isinstance(y, float)
        assert isinstance(conf, float)
        assert isinstance(cameras, list)

        # Two close detections → tuple
        result = fusion.fuse_detections([
            make_detection(0, 10.0, 20.0, 0.8),
            make_detection(1, 12.0, 21.0, 0.7),
        ])
        assert result is not None
        x, y, conf, cameras = result
        assert isinstance(x, float)
        assert isinstance(y, float)
        assert isinstance(conf, float)
        assert isinstance(cameras, list)

        # Three close detections → tuple
        result = fusion.fuse_detections([
            make_detection(0, 10.0, 20.0, 0.8),
            make_detection(1, 12.0, 21.0, 0.7),
            make_detection(2, 11.0, 20.5, 0.9),
        ])
        assert result is not None
        x, y, conf, cameras = result
        assert isinstance(x, float)
        assert isinstance(y, float)
        assert isinstance(conf, float)
        assert isinstance(cameras, list)
