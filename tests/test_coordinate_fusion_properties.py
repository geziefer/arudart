"""
Property-based tests for CoordinateFusion.

# Feature: step-7-multi-camera-fusion

Tests:
- Property 3: Weighted Average Fusion Correctness
- Property 5: Outlier Rejection Correctness

**Validates: Requirements AC-7.1.3, AC-7.1.4, AC-7.1.5**
"""

import math

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.fusion.coordinate_fusion import CoordinateFusion


# --- Shared config and helpers ---

DEFAULT_CONFIG = {"fusion": {"outlier_threshold_mm": 50.0, "min_confidence": 0.3}}
FLOAT_TOLERANCE = 1e-6


def make_detection(camera_id: int, x: float, y: float, confidence: float) -> dict:
    """Create a detection dict."""
    return {"camera_id": camera_id, "board": (x, y), "confidence": confidence}


# --- Strategies ---

# Confidence above min_confidence threshold so detections aren't filtered out
valid_confidence = st.floats(min_value=0.3, max_value=1.0, allow_nan=False, allow_infinity=False)

# Coordinates within a small cluster (within 50mm of each other) to avoid outlier rejection
# We use a base position and small offsets
base_coord = st.floats(min_value=-150.0, max_value=150.0, allow_nan=False, allow_infinity=False)
small_offset = st.floats(min_value=-20.0, max_value=20.0, allow_nan=False, allow_infinity=False)


@st.composite
def close_detections_strategy(draw):
    """Generate 2-3 detections with positions close together (within 50mm).

    All detections are within a small cluster so outlier rejection won't
    discard any of them, allowing us to test pure weighted average logic.
    """
    base_x = draw(base_coord)
    base_y = draw(base_coord)
    num_detections = draw(st.integers(min_value=2, max_value=3))

    detections = []
    for i in range(num_detections):
        offset_x = draw(small_offset)
        offset_y = draw(small_offset)
        conf = draw(valid_confidence)
        detections.append(make_detection(i, base_x + offset_x, base_y + offset_y, conf))

    return detections


@st.composite
def outlier_detections_strategy(draw):
    """Generate 3 detections where at least one is >50mm from the median.

    Creates 2 inliers close together and 1 outlier far away.
    """
    # Two inliers close together
    base_x = draw(st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    base_y = draw(st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False))

    offset1_x = draw(st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False))
    offset1_y = draw(st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False))

    conf0 = draw(valid_confidence)
    conf1 = draw(valid_confidence)
    conf2 = draw(valid_confidence)

    inlier0 = make_detection(0, base_x, base_y, conf0)
    inlier1 = make_detection(1, base_x + offset1_x, base_y + offset1_y, conf1)

    # Outlier: at least 60mm away from both inliers (guarantees >50mm from median)
    outlier_angle = draw(st.floats(min_value=0.0, max_value=2 * math.pi, allow_nan=False, allow_infinity=False))
    outlier_dist = draw(st.floats(min_value=80.0, max_value=200.0, allow_nan=False, allow_infinity=False))
    outlier_x = base_x + outlier_dist * math.cos(outlier_angle)
    outlier_y = base_y + outlier_dist * math.sin(outlier_angle)
    outlier = make_detection(2, outlier_x, outlier_y, conf2)

    return [inlier0, inlier1, outlier]


# --- Property 3: Weighted Average Fusion Correctness ---


class TestWeightedAverageFusionCorrectness:
    """
    Property 3: Weighted Average Fusion Correctness

    For any set of 2+ valid detections with positive confidences, the fused
    coordinate should be the confidence-weighted average of the input
    coordinates, and the combined confidence should be the average of
    individual confidences.

    **Validates: Requirements AC-7.1.3, AC-7.1.5**
    """

    @given(detections=close_detections_strategy())
    @settings(max_examples=200, deadline=None)
    def test_fused_position_is_weighted_average(self, detections: list[dict]) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 3: Weighted Average Fusion Correctness

        For close detections (no outlier rejection), the fused position must
        equal the confidence-weighted average of input coordinates.

        **Validates: Requirements AC-7.1.3, AC-7.1.5**
        """
        fusion = CoordinateFusion(DEFAULT_CONFIG)

        # Compute expected weighted average manually
        total_conf = sum(d["confidence"] for d in detections)
        assume(total_conf > 0)

        expected_x = sum(d["board"][0] * d["confidence"] for d in detections) / total_conf
        expected_y = sum(d["board"][1] * d["confidence"] for d in detections) / total_conf
        expected_confidence = sum(d["confidence"] for d in detections) / len(detections)

        result = fusion.fuse_detections(detections)
        assert result is not None, "Fusion should not return None for valid detections"

        fused_x, fused_y, confidence, cameras_used = result

        # Verify weighted average position
        assert abs(fused_x - expected_x) < FLOAT_TOLERANCE, (
            f"Fused X {fused_x} != expected {expected_x}"
        )
        assert abs(fused_y - expected_y) < FLOAT_TOLERANCE, (
            f"Fused Y {fused_y} != expected {expected_y}"
        )

        # Verify combined confidence is average of individual confidences
        assert abs(confidence - expected_confidence) < FLOAT_TOLERANCE, (
            f"Combined confidence {confidence} != expected {expected_confidence}"
        )

        # Verify all cameras are used (no outlier rejection for close detections)
        expected_cameras = sorted([d["camera_id"] for d in detections])
        assert sorted(cameras_used) == expected_cameras

    @given(detections=close_detections_strategy())
    @settings(max_examples=200, deadline=None)
    def test_weighted_average_method_directly(self, detections: list[dict]) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 3: Weighted Average Fusion Correctness

        The compute_weighted_average method should return the confidence-weighted
        average of the input coordinates.

        **Validates: Requirements AC-7.1.3**
        """
        fusion = CoordinateFusion(DEFAULT_CONFIG)

        total_conf = sum(d["confidence"] for d in detections)
        assume(total_conf > 0)

        expected_x = sum(d["board"][0] * d["confidence"] for d in detections) / total_conf
        expected_y = sum(d["board"][1] * d["confidence"] for d in detections) / total_conf

        wx, wy = fusion.compute_weighted_average(detections)

        assert abs(wx - expected_x) < FLOAT_TOLERANCE, (
            f"Weighted X {wx} != expected {expected_x}"
        )
        assert abs(wy - expected_y) < FLOAT_TOLERANCE, (
            f"Weighted Y {wy} != expected {expected_y}"
        )


# --- Property 5: Outlier Rejection Correctness ---


class TestOutlierRejectionCorrectness:
    """
    Property 5: Outlier Rejection Correctness

    For any set of 3+ detections where one or more are >50mm from the median
    position, the outlier rejection algorithm should discard exactly those
    detections that exceed the threshold, and retain all inliers.

    **Validates: Requirements AC-7.1.4**
    """

    @given(data=outlier_detections_strategy())
    @settings(max_examples=200, deadline=None)
    def test_outlier_rejected_inliers_retained(self, data: list[dict]) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 5: Outlier Rejection Correctness

        Given 3 detections (2 close inliers + 1 far outlier), the outlier
        rejection should discard exactly the outlier and retain the inliers.

        **Validates: Requirements AC-7.1.4**
        """
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        threshold = fusion.outlier_threshold_mm

        # Compute median position
        xs = [d["board"][0] for d in data]
        ys = [d["board"][1] for d in data]
        median_x = sorted(xs)[len(xs) // 2]
        median_y = sorted(ys)[len(ys) // 2]

        # Classify each detection as inlier or outlier based on distance from median
        expected_inliers = []
        expected_outliers = []
        for d in data:
            dx = d["board"][0] - median_x
            dy = d["board"][1] - median_y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= threshold:
                expected_inliers.append(d["camera_id"])
            else:
                expected_outliers.append(d["camera_id"])

        # At least one outlier must exist for this test to be meaningful
        assume(len(expected_outliers) >= 1)
        assume(len(expected_inliers) >= 1)

        # Run outlier rejection
        inliers = fusion.reject_outliers(data)

        # Verify correct cameras retained
        actual_inlier_ids = sorted([d["camera_id"] for d in inliers])
        assert actual_inlier_ids == sorted(expected_inliers), (
            f"Inlier cameras {actual_inlier_ids} != expected {sorted(expected_inliers)}"
        )

    @given(data=outlier_detections_strategy())
    @settings(max_examples=200, deadline=None)
    def test_all_inliers_within_threshold(self, data: list[dict]) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 5: Outlier Rejection Correctness

        All retained detections must be within the outlier threshold distance
        from the median position.

        **Validates: Requirements AC-7.1.4**
        """
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        threshold = fusion.outlier_threshold_mm

        inliers = fusion.reject_outliers(data)

        if not inliers:
            return  # Nothing to check

        # Compute median from original data
        xs = [d["board"][0] for d in data]
        ys = [d["board"][1] for d in data]
        median_x = sorted(xs)[len(xs) // 2]
        median_y = sorted(ys)[len(ys) // 2]

        # Every inlier must be within threshold
        for d in inliers:
            dx = d["board"][0] - median_x
            dy = d["board"][1] - median_y
            dist = math.sqrt(dx * dx + dy * dy)
            assert dist <= threshold + FLOAT_TOLERANCE, (
                f"Inlier camera {d['camera_id']} at distance {dist:.1f}mm "
                f"exceeds threshold {threshold}mm"
            )
