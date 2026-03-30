"""
Property-based tests for Fusion Accuracy Improvements.

# Feature: step-7.1-fusion-accuracy

Tests:
- Property 1: Pairwise Rejection Correctness

**Validates: Requirements 1.1, 1.2**
"""

import math

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.fusion.coordinate_fusion import CoordinateFusion


# --- Shared config and helpers ---

DEFAULT_CONFIG = {
    "fusion": {
        "outlier_threshold_mm": 25.0,
        "min_confidence": 0.3,
        "pairwise_rejection_mm": 20.0,
        "angular_falloff": 1.0,
        "camera_anchors": {"cam0": 81, "cam1": 257, "cam2": 153},
    }
}

FLOAT_TOLERANCE = 1e-6


def make_detection(camera_id: int, x: float, y: float, confidence: float) -> dict:
    """Create a detection dict."""
    return {"camera_id": camera_id, "board": (x, y), "confidence": confidence}


# --- Strategies ---

# Confidence above min_confidence threshold so detections aren't filtered out
valid_confidence = st.floats(
    min_value=0.3, max_value=1.0, allow_nan=False, allow_infinity=False
)

# Board coordinates in a reasonable range
board_coord = st.floats(
    min_value=-170.0, max_value=170.0, allow_nan=False, allow_infinity=False
)


@st.composite
def pairwise_detections_strategy(draw):
    """Generate a pair of detections with random positions and confidences."""
    x0 = draw(board_coord)
    y0 = draw(board_coord)
    x1 = draw(board_coord)
    y1 = draw(board_coord)
    conf0 = draw(valid_confidence)
    conf1 = draw(valid_confidence)

    d0 = make_detection(0, x0, y0, conf0)
    d1 = make_detection(1, x1, y1, conf1)
    return [d0, d1]


# --- Property 1: Pairwise Rejection Correctness ---


class TestPairwiseRejectionCorrectness:
    """
    Property 1: Pairwise Rejection Correctness

    For any two detections with valid confidence, if the Euclidean distance
    between their board positions exceeds the pairwise rejection threshold,
    reject_outliers_pairwise should return exactly one detection (the one
    with higher confidence). If the distance is within the threshold, it
    should return both detections unchanged.

    **Validates: Requirements 1.1, 1.2**
    """

    @given(detections=pairwise_detections_strategy())
    @settings(max_examples=100, deadline=None)
    def test_pairwise_rejection_correctness(self, detections: list[dict]) -> None:
        """
        Feature: step-7.1-fusion-accuracy, Property 1: Pairwise Rejection Correctness

        Generate random pairs of detections with random positions and confidences.
        If distance > threshold: verify only the higher-confidence detection is returned.
        If distance <= threshold: verify both detections are returned unchanged.

        **Validates: Requirements 1.1, 1.2**
        """
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        threshold = fusion.pairwise_rejection_mm

        d0, d1 = detections
        dx = d0["board"][0] - d1["board"][0]
        dy = d0["board"][1] - d1["board"][1]
        dist = math.sqrt(dx * dx + dy * dy)

        result = fusion.reject_outliers_pairwise(detections)

        if dist <= threshold:
            # Both detections should be returned unchanged
            assert len(result) == 2, (
                f"Expected 2 detections when dist={dist:.2f} <= threshold={threshold}, "
                f"got {len(result)}"
            )
            assert result[0] is d0
            assert result[1] is d1
        else:
            # Only the higher-confidence detection should be returned
            assert len(result) == 1, (
                f"Expected 1 detection when dist={dist:.2f} > threshold={threshold}, "
                f"got {len(result)}"
            )
            if d0["confidence"] >= d1["confidence"]:
                assert result[0] is d0, (
                    f"Expected higher-confidence detection (cam {d0['camera_id']}, "
                    f"conf={d0['confidence']}) but got cam {result[0]['camera_id']}"
                )
            else:
                assert result[0] is d1, (
                    f"Expected higher-confidence detection (cam {d1['camera_id']}, "
                    f"conf={d1['confidence']}) but got cam {result[0]['camera_id']}"
                )


# --- Strategies for Property 2 ---


@st.composite
def three_detections_strategy(draw):
    """Generate exactly 3 detections with random positions and confidences."""
    detections = []
    for cam_id in range(3):
        x = draw(board_coord)
        y = draw(board_coord)
        conf = draw(valid_confidence)
        detections.append(make_detection(cam_id, x, y, conf))
    return detections


# --- Property 2: Median-Based Outlier Rejection Correctness ---


class TestMedianBasedOutlierRejectionCorrectness:
    """
    Property 2: Median-Based Outlier Rejection Correctness

    For any set of 3 detections, reject_outliers should retain exactly those
    detections whose Euclidean distance from the median (x, y) position is
    <= the outlier threshold, and reject all others.

    **Validates: Requirements 2.1**
    """

    @given(detections=three_detections_strategy())
    @settings(max_examples=100, deadline=None)
    def test_median_based_outlier_rejection_correctness(self, detections: list[dict]) -> None:
        """
        Feature: step-7.1-fusion-accuracy, Property 2: Median-Based Outlier Rejection Correctness

        Generate 3 random detections; compute median position manually.
        Verify retained detections are exactly those within outlier_threshold_mm of median.

        **Validates: Requirements 2.1**
        """
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        threshold = fusion.outlier_threshold_mm

        # Compute expected median position
        xs = [d["board"][0] for d in detections]
        ys = [d["board"][1] for d in detections]
        median_x = sorted(xs)[1]  # median of 3 values
        median_y = sorted(ys)[1]

        # Determine which detections should be kept
        expected_inliers = []
        for d in detections:
            dx = d["board"][0] - median_x
            dy = d["board"][1] - median_y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= threshold:
                expected_inliers.append(d)

        # Run the actual method
        result = fusion.reject_outliers(detections)

        # Verify the result matches expected inliers exactly
        assert len(result) == len(expected_inliers), (
            f"Expected {len(expected_inliers)} inliers but got {len(result)}. "
            f"Threshold={threshold}, median=({median_x:.2f}, {median_y:.2f})"
        )
        for d in result:
            assert d in expected_inliers, (
                f"Detection cam {d['camera_id']} at {d['board']} was returned "
                f"but should not be an inlier (threshold={threshold})"
            )
        for d in expected_inliers:
            assert d in result, (
                f"Detection cam {d['camera_id']} at {d['board']} should be an "
                f"inlier but was not returned (threshold={threshold})"
            )


# --- Strategies for Property 4 ---

# Board angle in full circle [0, 2π)
board_angle_rad = st.floats(
    min_value=0.0, max_value=2 * math.pi, allow_nan=False, allow_infinity=False
)

camera_id_strategy = st.sampled_from([0, 1, 2])


# --- Property 4: Angular Weight Formula ---


class TestAngularWeightFormula:
    """
    Property 4: Angular Weight Formula

    For any board angle and any camera ID, compute_angular_weight should return
    ((1 + cos(shortest_arc)) / 2) ** falloff where shortest_arc is the minimum
    arc between the board angle and the camera's anchor angle. The result is 1.0
    when the dart is at the camera's anchor angle and approaches 0.0 at 180° away.

    **Validates: Requirements 3.2, 3.3, 3.4**
    """

    @given(angle=board_angle_rad, cam_id=camera_id_strategy)
    @settings(max_examples=100, deadline=None)
    def test_angular_weight_matches_formula(self, angle: float, cam_id: int) -> None:
        """
        Feature: step-7.1-fusion-accuracy, Property 4: Angular Weight Formula

        Generate random board angles and camera IDs (0, 1, 2).
        Verify result matches ((1 + cos(shortest_arc)) / 2) ** falloff.

        **Validates: Requirements 3.2, 3.3, 3.4**
        """
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        anchor_deg = DEFAULT_CONFIG["fusion"]["camera_anchors"][f"cam{cam_id}"]
        anchor_rad = math.radians(anchor_deg)

        # Compute expected shortest arc
        delta = abs(angle - anchor_rad)
        delta = min(delta, 2 * math.pi - delta)

        expected = ((1 + math.cos(delta)) / 2) ** fusion.angular_falloff
        result = fusion.compute_angular_weight(angle, cam_id)

        assert abs(result - expected) < FLOAT_TOLERANCE, (
            f"Angular weight mismatch for angle={math.degrees(angle):.1f}°, "
            f"cam{cam_id} (anchor={anchor_deg}°): got {result}, expected {expected}"
        )

    def test_angular_weight_is_one_at_anchor(self) -> None:
        """Verify result is 1.0 when dart angle equals camera anchor angle.

        **Validates: Requirements 3.2, 3.3**
        """
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        for cam_id in [0, 1, 2]:
            anchor_deg = DEFAULT_CONFIG["fusion"]["camera_anchors"][f"cam{cam_id}"]
            anchor_rad = math.radians(anchor_deg)
            result = fusion.compute_angular_weight(anchor_rad, cam_id)
            assert abs(result - 1.0) < FLOAT_TOLERANCE, (
                f"Expected weight=1.0 at anchor for cam{cam_id}, got {result}"
            )

    def test_angular_weight_approaches_zero_at_180(self) -> None:
        """Verify result approaches 0.0 at 180° away from anchor.

        **Validates: Requirements 3.2, 3.3**
        """
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        for cam_id in [0, 1, 2]:
            anchor_deg = DEFAULT_CONFIG["fusion"]["camera_anchors"][f"cam{cam_id}"]
            opposite_rad = math.radians((anchor_deg + 180) % 360)
            result = fusion.compute_angular_weight(opposite_rad, cam_id)
            assert result < 1e-9, (
                f"Expected weight≈0.0 at 180° from anchor for cam{cam_id}, got {result}"
            )


# --- Strategies for Property 3 ---


@st.composite
def all_outlier_detections_strategy(draw):
    """Generate 3 detections that are all far from each other.

    Places detections at 120° intervals on a circle of radius 80mm from origin,
    with small random offsets. This ensures all 3 are far from the median and
    will all be rejected by the 25mm outlier threshold.
    """
    # Base radius large enough that all points are >25mm from median
    base_radius = draw(st.floats(min_value=80.0, max_value=150.0,
                                  allow_nan=False, allow_infinity=False))
    # Small random offset to add variety without breaking the "all far apart" property
    offset = st.floats(min_value=-5.0, max_value=5.0,
                       allow_nan=False, allow_infinity=False)

    detections = []
    for cam_id in range(3):
        angle = math.radians(cam_id * 120)
        x = base_radius * math.cos(angle) + draw(offset)
        y = base_radius * math.sin(angle) + draw(offset)
        conf = draw(valid_confidence)
        detections.append(make_detection(cam_id, x, y, conf))

    return detections


# --- Property 3: Total Rejection Fallback ---


class TestTotalRejectionFallback:
    """
    Property 3: Total Rejection Fallback

    For any set of 3 detections where all are rejected by median-based outlier
    rejection (all > threshold from median), fuse_detections should return a
    result using the detection with the highest confidence rather than returning
    None.

    **Validates: Requirements 2.4**
    """

    @given(detections=all_outlier_detections_strategy())
    @settings(max_examples=100, deadline=None)
    def test_total_rejection_fallback(self, detections: list[dict]) -> None:
        """
        Feature: step-7.1-fusion-accuracy, Property 3: Total Rejection Fallback

        Generate 3 detections all far apart (all > 25mm from median).
        Verify fuse_detections returns a non-None result using the
        highest-confidence detection's position.

        **Validates: Requirements 2.4**
        """
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        threshold = fusion.outlier_threshold_mm

        # Verify precondition: all detections are outliers from median
        from statistics import median as stat_median
        xs = [d["board"][0] for d in detections]
        ys = [d["board"][1] for d in detections]
        median_x = stat_median(xs)
        median_y = stat_median(ys)

        all_are_outliers = all(
            math.sqrt((d["board"][0] - median_x) ** 2 + (d["board"][1] - median_y) ** 2)
            > threshold
            for d in detections
        )
        assume(all_are_outliers)

        # Run fuse_detections
        result = fusion.fuse_detections(detections)

        # Must not be None — fallback should kick in
        assert result is not None, (
            "fuse_detections returned None when all 3 detections were outliers; "
            "expected fallback to highest-confidence detection"
        )

        # Result should use the highest-confidence detection's position
        best = max(detections, key=lambda d: d["confidence"])
        fused_x, fused_y, fused_conf, cameras_used = result

        assert abs(fused_x - best["board"][0]) < FLOAT_TOLERANCE, (
            f"Fallback x mismatch: got {fused_x}, expected {best['board'][0]}"
        )
        assert abs(fused_y - best["board"][1]) < FLOAT_TOLERANCE, (
            f"Fallback y mismatch: got {fused_y}, expected {best['board'][1]}"
        )
        assert best["camera_id"] in cameras_used, (
            f"Highest-confidence camera {best['camera_id']} not in cameras_used={cameras_used}"
        )


# --- Strategies for Property 5 ---


@st.composite
def close_detections_strategy(draw):
    """Generate 2-3 detections clustered within a small area.

    All detections are within 15mm of each other (for 2-camera) or 20mm
    (for 3-camera), ensuring no outlier rejection occurs.
    """
    n = draw(st.integers(min_value=2, max_value=3))

    # Base position away from origin to get meaningful board angles
    base_x = draw(st.floats(min_value=30.0, max_value=150.0,
                             allow_nan=False, allow_infinity=False))
    base_y = draw(st.floats(min_value=30.0, max_value=150.0,
                             allow_nan=False, allow_infinity=False))

    # Max spread: 10mm to stay well within both pairwise (20mm) and outlier (25mm) thresholds
    small_offset = st.floats(min_value=-5.0, max_value=5.0,
                              allow_nan=False, allow_infinity=False)

    detections = []
    for cam_id in range(n):
        x = base_x + draw(small_offset)
        y = base_y + draw(small_offset)
        conf = draw(valid_confidence)
        detections.append(make_detection(cam_id, x, y, conf))

    return detections


# --- Property 5: Two-Pass Fusion Weighted Average ---


class TestTwoPassFusionWeightedAverage:
    """
    Property 5: Two-Pass Fusion Weighted Average

    For any set of 2+ inlier detections with positive confidence, the fused
    position returned by fuse_detections should equal the weighted average of
    the inlier positions using combined weights (confidence × angular_weight),
    where the angular weights are computed from the board angle of the
    confidence-only preliminary position. The return value should always be a
    4-tuple (x, y, confidence, cameras_used) or None.

    **Validates: Requirements 3.5, 4.1, 6.4**
    """

    @given(detections=close_detections_strategy())
    @settings(max_examples=100, deadline=None)
    def test_two_pass_fusion_weighted_average(self, detections: list[dict]) -> None:
        """
        Feature: step-7.1-fusion-accuracy, Property 5: Two-Pass Fusion Weighted Average

        Generate 2-3 close detections (within pairwise/outlier threshold).
        Manually compute expected result: pass 1 confidence-only avg → board angle
        → angular weights → pass 2 weighted avg.
        Verify fuse_detections output matches within 1e-6 tolerance.

        **Validates: Requirements 3.5, 4.1, 6.4**
        """
        fusion = CoordinateFusion(DEFAULT_CONFIG)

        # Manually compute expected two-pass result

        # Pass 1: confidence-only weighted average
        total_conf = sum(d["confidence"] for d in detections)
        assume(total_conf > 0)

        px = sum(d["board"][0] * d["confidence"] for d in detections) / total_conf
        py = sum(d["board"][1] * d["confidence"] for d in detections) / total_conf

        # Board angle from preliminary position
        board_angle = math.atan2(py, px)

        # Compute angular weights for each detection
        angular_weights = {}
        combined_weights = {}
        for d in detections:
            cam_id = d["camera_id"]
            anchor_deg = DEFAULT_CONFIG["fusion"]["camera_anchors"][f"cam{cam_id}"]
            anchor_rad = math.radians(anchor_deg)
            delta = abs(board_angle - anchor_rad)
            delta = min(delta, 2 * math.pi - delta)
            aw = ((1 + math.cos(delta)) / 2) ** fusion.angular_falloff
            aw = max(aw, 0.0)
            angular_weights[id(d)] = aw
            combined_weights[id(d)] = d["confidence"] * aw

        # If all angular weights < min_angular_weight: use confidence-only weights
        if all(aw < fusion.min_angular_weight for aw in angular_weights.values()):
            combined_weights = {id(d): d["confidence"] for d in detections}

        # Pass 2: weighted average with combined weights
        total_w = sum(combined_weights[id(d)] for d in detections)
        assume(total_w > 0)

        expected_x = sum(d["board"][0] * combined_weights[id(d)] for d in detections) / total_w
        expected_y = sum(d["board"][1] * combined_weights[id(d)] for d in detections) / total_w

        # Run fuse_detections
        result = fusion.fuse_detections(detections)

        # Verify return type is a 4-tuple or None
        assert result is not None, "fuse_detections returned None for close detections"
        assert isinstance(result, tuple) and len(result) == 4, (
            f"Expected 4-tuple, got {type(result)} with length {len(result) if isinstance(result, tuple) else 'N/A'}"
        )

        fused_x, fused_y, fused_conf, cameras_used = result

        # Verify types
        assert isinstance(fused_x, float), f"fused_x should be float, got {type(fused_x)}"
        assert isinstance(fused_y, float), f"fused_y should be float, got {type(fused_y)}"
        assert isinstance(fused_conf, float), f"fused_conf should be float, got {type(fused_conf)}"
        assert isinstance(cameras_used, list), f"cameras_used should be list, got {type(cameras_used)}"
        assert all(isinstance(c, int) for c in cameras_used), "cameras_used should contain ints"

        # Verify fused position matches manual computation within tolerance
        assert abs(fused_x - expected_x) < FLOAT_TOLERANCE, (
            f"Fused x mismatch: got {fused_x}, expected {expected_x}, "
            f"diff={abs(fused_x - expected_x)}"
        )
        assert abs(fused_y - expected_y) < FLOAT_TOLERANCE, (
            f"Fused y mismatch: got {fused_y}, expected {expected_y}, "
            f"diff={abs(fused_y - expected_y)}"
        )
