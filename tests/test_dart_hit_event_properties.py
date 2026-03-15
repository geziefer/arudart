"""
Property-based tests for DartHitEvent JSON serialization.

# Feature: step-7-multi-camera-fusion, Property 7: Event JSON Serialization Round Trip

Tests:
- Round-trip: to_dict() then from_dict() produces an equivalent DartHitEvent
  with all fields matching within floating-point tolerance.

**Validates: Requirements AC-7.6.7**
"""

import math

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from src.fusion.dart_hit_event import CameraDetection, DartHitEvent, Score


# --- Strategies ---

VALID_RING_NAMES = [
    "bull",
    "single_bull",
    "triple",
    "double",
    "single",
    "out_of_bounds",
]


@st.composite
def score_strategy(draw):
    """Generate a random valid Score object."""
    base = draw(st.integers(min_value=0, max_value=20))
    multiplier = draw(st.integers(min_value=0, max_value=3))
    total = base * multiplier
    ring = draw(st.sampled_from(VALID_RING_NAMES))
    sector = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=20)))
    return Score(
        base=base,
        multiplier=multiplier,
        total=total,
        ring=ring,
        sector=sector,
    )


@st.composite
def camera_detection_strategy(draw):
    """Generate a random valid CameraDetection object."""
    camera_id = draw(st.integers(min_value=0, max_value=2))
    pixel_x = draw(st.floats(min_value=0, max_value=1280, allow_nan=False, allow_infinity=False))
    pixel_y = draw(st.floats(min_value=0, max_value=720, allow_nan=False, allow_infinity=False))
    board_x = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    board_y = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    confidence = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    return CameraDetection(
        camera_id=camera_id,
        pixel_x=pixel_x,
        pixel_y=pixel_y,
        board_x=board_x,
        board_y=board_y,
        confidence=confidence,
    )


@st.composite
def dart_hit_event_strategy(draw):
    """Generate a random valid DartHitEvent object."""
    timestamp = draw(st.from_regex(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z",
        fullmatch=True,
    ))
    board_x = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    board_y = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    radius = draw(st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False))
    angle_rad = draw(st.floats(min_value=0, max_value=2 * math.pi, allow_nan=False, allow_infinity=False))
    angle_deg = draw(st.floats(min_value=0, max_value=360, allow_nan=False, allow_infinity=False))
    score = draw(score_strategy())
    fusion_confidence = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))

    num_cameras = draw(st.integers(min_value=1, max_value=3))
    cameras_used = draw(
        st.lists(
            st.integers(min_value=0, max_value=2),
            min_size=num_cameras,
            max_size=num_cameras,
            unique=True,
        )
    )

    detections = draw(
        st.lists(camera_detection_strategy(), min_size=1, max_size=3)
    )

    image_paths = draw(
        st.dictionaries(
            keys=st.sampled_from(["0", "1", "2"]),
            values=st.from_regex(r"data/throws/cam[012]_annotated_\d{8}_\d{6}\.jpg", fullmatch=True),
            min_size=0,
            max_size=3,
        )
    )

    return DartHitEvent(
        timestamp=timestamp,
        board_x=board_x,
        board_y=board_y,
        radius=radius,
        angle_rad=angle_rad,
        angle_deg=angle_deg,
        score=score,
        fusion_confidence=fusion_confidence,
        cameras_used=cameras_used,
        num_cameras=num_cameras,
        detections=detections,
        image_paths=image_paths,
    )



# --- Property 7: Event JSON Serialization Round Trip ---


class TestEventJsonSerializationRoundTrip:
    """
    Property 7: Event JSON Serialization Round Trip

    For any valid DartHitEvent, serializing to JSON then deserializing
    should produce an equivalent event with all fields matching within
    floating-point tolerance.

    **Validates: Requirements AC-7.6.7**
    """

    FLOAT_TOLERANCE = 1e-9

    def _assert_floats_close(self, a: float, b: float, label: str) -> None:
        """Assert two floats are equal within tolerance."""
        assert abs(a - b) < self.FLOAT_TOLERANCE, (
            f"{label}: {a} != {b} (diff={abs(a - b)})"
        )

    def _assert_score_equal(self, original: Score, restored: Score) -> None:
        """Assert two Score objects are equivalent."""
        assert original.base == restored.base, f"base: {original.base} != {restored.base}"
        assert original.multiplier == restored.multiplier
        assert original.total == restored.total
        assert original.ring == restored.ring
        assert original.sector == restored.sector

    def _assert_detection_equal(
        self, original: CameraDetection, restored: CameraDetection
    ) -> None:
        """Assert two CameraDetection objects are equivalent."""
        assert original.camera_id == restored.camera_id
        self._assert_floats_close(original.pixel_x, restored.pixel_x, "pixel_x")
        self._assert_floats_close(original.pixel_y, restored.pixel_y, "pixel_y")
        self._assert_floats_close(original.board_x, restored.board_x, "board_x")
        self._assert_floats_close(original.board_y, restored.board_y, "board_y")
        self._assert_floats_close(original.confidence, restored.confidence, "confidence")

    @given(event=dart_hit_event_strategy())
    @settings(max_examples=200, deadline=None)
    def test_dart_hit_event_round_trip(self, event: DartHitEvent) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 7: Event JSON Serialization Round Trip

        Serialize a DartHitEvent to dict, then deserialize back. All fields
        must match the original within floating-point tolerance.

        **Validates: Requirements AC-7.6.7**
        """
        serialized = event.to_dict()
        restored = DartHitEvent.from_dict(serialized)

        # Timestamp (exact string match)
        assert event.timestamp == restored.timestamp

        # Board coordinates
        self._assert_floats_close(event.board_x, restored.board_x, "board_x")
        self._assert_floats_close(event.board_y, restored.board_y, "board_y")

        # Polar coordinates
        self._assert_floats_close(event.radius, restored.radius, "radius")
        self._assert_floats_close(event.angle_rad, restored.angle_rad, "angle_rad")
        self._assert_floats_close(event.angle_deg, restored.angle_deg, "angle_deg")

        # Score
        self._assert_score_equal(event.score, restored.score)

        # Fusion metadata
        self._assert_floats_close(
            event.fusion_confidence, restored.fusion_confidence, "fusion_confidence"
        )
        assert event.cameras_used == restored.cameras_used
        assert event.num_cameras == restored.num_cameras

        # Per-camera detections
        assert len(event.detections) == len(restored.detections)
        for orig_det, rest_det in zip(event.detections, restored.detections):
            self._assert_detection_equal(orig_det, rest_det)

        # Image paths
        assert event.image_paths == restored.image_paths

    @given(score=score_strategy())
    @settings(max_examples=200, deadline=None)
    def test_score_round_trip(self, score: Score) -> None:
        """
        Score serialization round trip: to_dict() then from_dict()
        should produce an identical Score.

        **Validates: Requirements AC-7.6.7**
        """
        restored = Score.from_dict(score.to_dict())
        self._assert_score_equal(score, restored)

    @given(detection=camera_detection_strategy())
    @settings(max_examples=200, deadline=None)
    def test_camera_detection_round_trip(self, detection: CameraDetection) -> None:
        """
        CameraDetection serialization round trip: to_dict() then from_dict()
        should produce an identical CameraDetection.

        **Validates: Requirements AC-7.6.7**
        """
        restored = CameraDetection.from_dict(detection.to_dict())
        self._assert_detection_equal(detection, restored)
