"""
Property-based tests for ScoreCalculator.

# Feature: step-7-multi-camera-fusion

Tests:
- Property 6: Score Calculation Correctness
- Property 8: Event Structure Completeness

**Validates: Requirements AC-7.5.1, AC-7.5.2, AC-7.5.3, AC-7.5.4, AC-7.5.5,
AC-7.6.1, AC-7.6.2, AC-7.6.3, AC-7.6.4, AC-7.6.5, AC-7.6.6**
"""

import datetime

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.fusion.dart_hit_event import CameraDetection, DartHitEvent, Score
from src.fusion.score_calculator import ScoreCalculator


# --- Shared config and helpers ---

CONFIG = {
    "fusion": {"outlier_threshold_mm": 50.0, "min_confidence": 0.3},
    "board": {
        "bull_radius_mm": 6.35,
        "single_bull_radius_mm": 15.9,
        "triple_inner_mm": 99.0,
        "triple_outer_mm": 107.0,
        "double_inner_mm": 162.0,
        "double_outer_mm": 170.0,
        "sectors": {
            "sector_order": [
                20, 1, 18, 4, 13, 6, 10, 15, 2, 17,
                3, 19, 7, 16, 8, 11, 14, 9, 12, 5,
            ],
            "sector_width_deg": 18.0,
            "wire_gap_deg": 2.0,
            "sector_offset_deg": 0.0,
        },
    },
}

VALID_SECTORS = list(range(1, 21))
REGULAR_RINGS = ["single", "double", "triple"]
RING_MULTIPLIERS = {"single": 1, "double": 2, "triple": 3}
SPECIAL_RINGS = ["bull", "single_bull", "out_of_bounds"]


def _make_detection(camera_id: int, bx: float, by: float, conf: float = 0.8) -> dict:
    """Create a detection dict."""
    return {
        "camera_id": camera_id,
        "pixel": (400.0, 300.0),
        "board": (bx, by),
        "confidence": conf,
    }


# --- Strategies ---

sector_strategy = st.sampled_from(VALID_SECTORS)
regular_ring_strategy = st.sampled_from(REGULAR_RINGS)
special_ring_strategy = st.sampled_from(SPECIAL_RINGS)

# Board coordinates within the scoring area (0-170mm radius)
board_coord = st.floats(min_value=-165.0, max_value=165.0, allow_nan=False, allow_infinity=False)

# Confidence above min threshold
valid_confidence = st.floats(min_value=0.3, max_value=1.0, allow_nan=False, allow_infinity=False)


@st.composite
def valid_detections_strategy(draw):
    """Generate 1-3 detections with close board positions and valid confidence.

    Positions are clustered within a small area so fusion succeeds without
    outlier rejection discarding any of them.
    """
    base_x = draw(st.floats(min_value=-160.0, max_value=160.0, allow_nan=False, allow_infinity=False))
    base_y = draw(st.floats(min_value=-160.0, max_value=160.0, allow_nan=False, allow_infinity=False))
    num = draw(st.integers(min_value=1, max_value=3))

    detections = []
    for i in range(num):
        offset_x = draw(st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False))
        offset_y = draw(st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False))
        conf = draw(valid_confidence)
        detections.append(_make_detection(i, base_x + offset_x, base_y + offset_y, conf))

    return detections


# --- Property 6: Score Calculation Correctness ---


class TestScoreCalculationCorrectness:
    """
    Property 6: Score Calculation Correctness

    For any valid ring and sector combination, the total score should equal
    sector_number * multiplier for regular rings, or the fixed score (50/25/0)
    for bulls and misses.

    **Validates: Requirements AC-7.5.1, AC-7.5.2, AC-7.5.3**
    """

    def setup_method(self):
        self.calc = ScoreCalculator(CONFIG)

    @given(ring=regular_ring_strategy, sector=sector_strategy)
    @settings(max_examples=200, deadline=None)
    def test_regular_ring_score_equals_sector_times_multiplier(
        self, ring: str, sector: int
    ) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 6: Score Calculation Correctness

        For any regular ring (single/double/triple) and sector (1-20), the
        total score must equal sector_number * multiplier.

        **Validates: Requirements AC-7.5.3**
        """
        multiplier = RING_MULTIPLIERS[ring]
        score = self.calc.calculate_score(ring, multiplier, 0, sector)

        assert score.total == sector * multiplier, (
            f"{ring} {sector}: expected {sector * multiplier}, got {score.total}"
        )
        assert score.base == sector
        assert score.multiplier == multiplier
        assert score.ring == ring
        assert score.sector == sector

    @given(data=st.data())
    @settings(max_examples=200, deadline=None)
    def test_bull_score_is_always_50(self, data) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 6: Score Calculation Correctness

        Bull always scores 50 regardless of any other parameters.

        **Validates: Requirements AC-7.5.1**
        """
        score = self.calc.calculate_score("bull", 0, 50, None)

        assert score.total == 50
        assert score.base == 50
        assert score.multiplier == 0
        assert score.ring == "bull"
        assert score.sector is None

    @given(data=st.data())
    @settings(max_examples=200, deadline=None)
    def test_single_bull_score_is_always_25(self, data) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 6: Score Calculation Correctness

        Single bull always scores 25 regardless of any other parameters.

        **Validates: Requirements AC-7.5.2**
        """
        score = self.calc.calculate_score("single_bull", 0, 25, None)

        assert score.total == 25
        assert score.base == 25
        assert score.multiplier == 0
        assert score.ring == "single_bull"
        assert score.sector is None

    @given(data=st.data())
    @settings(max_examples=200, deadline=None)
    def test_out_of_bounds_score_is_always_0(self, data) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 6: Score Calculation Correctness

        Out of bounds always scores 0.

        **Validates: Requirements AC-7.5.1, AC-7.5.2, AC-7.5.3**
        """
        score = self.calc.calculate_score("out_of_bounds", 0, 0, None)

        assert score.total == 0
        assert score.base == 0
        assert score.multiplier == 0
        assert score.ring == "out_of_bounds"
        assert score.sector is None

    @given(
        ring=st.sampled_from(["bull", "single_bull", "out_of_bounds", "single", "double", "triple"]),
        sector=st.one_of(st.none(), sector_strategy),
    )
    @settings(max_examples=200, deadline=None)
    def test_score_total_is_non_negative(self, ring: str, sector) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 6: Score Calculation Correctness

        For any ring/sector combination, the total score is always non-negative.

        **Validates: Requirements AC-7.5.1, AC-7.5.2, AC-7.5.3**
        """
        if ring in SPECIAL_RINGS:
            multiplier = 0
            base_score = {"bull": 50, "single_bull": 25, "out_of_bounds": 0}[ring]
            sector_val = None
        else:
            assume(sector is not None)
            multiplier = RING_MULTIPLIERS[ring]
            base_score = 0
            sector_val = sector

        score = self.calc.calculate_score(ring, multiplier, base_score, sector_val)
        assert score.total >= 0


# --- Property 8: Event Structure Completeness ---


class TestEventStructureCompleteness:
    """
    Property 8: Event Structure Completeness

    For any DartHitEvent created from valid detections, the event should
    contain all required fields with valid values.

    **Validates: Requirements AC-7.5.4, AC-7.5.5, AC-7.6.1, AC-7.6.2,
    AC-7.6.3, AC-7.6.4, AC-7.6.5, AC-7.6.6**
    """

    def setup_method(self):
        self.calc = ScoreCalculator(CONFIG)

    @given(detections=valid_detections_strategy())
    @settings(max_examples=200, deadline=None)
    def test_event_has_valid_timestamp(self, detections: list[dict]) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 8: Event Structure Completeness

        Every event must have a valid ISO 8601 timestamp.

        **Validates: Requirements AC-7.6.1**
        """
        event = self.calc.process_detections(detections)
        assume(event is not None)

        assert isinstance(event.timestamp, str)
        # Must parse as valid ISO 8601
        parsed = datetime.datetime.fromisoformat(event.timestamp)
        assert parsed.tzinfo is not None  # Must be timezone-aware

    @given(detections=valid_detections_strategy())
    @settings(max_examples=200, deadline=None)
    def test_event_has_valid_board_coordinates(self, detections: list[dict]) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 8: Event Structure Completeness

        Every event must have float board coordinates.

        **Validates: Requirements AC-7.6.2**
        """
        event = self.calc.process_detections(detections)
        assume(event is not None)

        assert isinstance(event.board_x, float)
        assert isinstance(event.board_y, float)

    @given(detections=valid_detections_strategy())
    @settings(max_examples=200, deadline=None)
    def test_event_has_valid_polar_coordinates(self, detections: list[dict]) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 8: Event Structure Completeness

        Every event must have non-negative radius and angle in valid ranges.

        **Validates: Requirements AC-7.6.3**
        """
        event = self.calc.process_detections(detections)
        assume(event is not None)

        assert event.radius >= 0
        assert 0 <= event.angle_rad < 2 * 3.141592653589794
        assert 0 <= event.angle_deg < 360.0

    @given(detections=valid_detections_strategy())
    @settings(max_examples=200, deadline=None)
    def test_event_has_complete_score(self, detections: list[dict]) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 8: Event Structure Completeness

        Every event must have a Score with base, multiplier, total, and ring.

        **Validates: Requirements AC-7.5.4, AC-7.5.5, AC-7.6.4**
        """
        event = self.calc.process_detections(detections)
        assume(event is not None)

        score = event.score
        assert isinstance(score, Score)
        assert isinstance(score.base, int)
        assert isinstance(score.multiplier, int)
        assert isinstance(score.total, int)
        assert score.total >= 0
        assert score.ring in ("bull", "single_bull", "triple", "double", "single", "out_of_bounds")

        # If regular ring, sector must be present and valid
        if score.ring in ("single", "double", "triple"):
            assert score.sector in VALID_SECTORS
        else:
            assert score.sector is None

    @given(detections=valid_detections_strategy())
    @settings(max_examples=200, deadline=None)
    def test_event_has_valid_fusion_metadata(self, detections: list[dict]) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 8: Event Structure Completeness

        Every event must have fusion confidence, cameras_used, and num_cameras.

        **Validates: Requirements AC-7.6.5**
        """
        event = self.calc.process_detections(detections)
        assume(event is not None)

        assert 0 < event.fusion_confidence <= 1.0
        assert isinstance(event.cameras_used, list)
        assert len(event.cameras_used) >= 1
        assert event.num_cameras == len(event.cameras_used)

    @given(detections=valid_detections_strategy())
    @settings(max_examples=200, deadline=None)
    def test_event_has_per_camera_detections(self, detections: list[dict]) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 8: Event Structure Completeness

        Every event must include per-camera detection data matching the input.

        **Validates: Requirements AC-7.6.5**
        """
        event = self.calc.process_detections(detections)
        assume(event is not None)

        assert len(event.detections) >= 1
        for det in event.detections:
            assert isinstance(det, CameraDetection)
            assert isinstance(det.camera_id, int)
            assert isinstance(det.pixel_x, float)
            assert isinstance(det.pixel_y, float)
            assert isinstance(det.board_x, float)
            assert isinstance(det.board_y, float)
            assert 0 <= det.confidence <= 1.0

    @given(detections=valid_detections_strategy())
    @settings(max_examples=200, deadline=None)
    def test_event_has_image_paths_dict(self, detections: list[dict]) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 8: Event Structure Completeness

        Every event must have an image_paths dict (may be empty).

        **Validates: Requirements AC-7.6.6**
        """
        event = self.calc.process_detections(detections)
        assume(event is not None)

        assert isinstance(event.image_paths, dict)
