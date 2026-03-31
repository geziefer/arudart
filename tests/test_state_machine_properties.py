"""
Property-based tests for the state machine module.

Tests:
- Property 4: Dart Count Invariant

**Validates: Requirements AC-8.2.1, AC-8.2.4**
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.state_machine.dart_tracker import DartTracker


# ---------------------------------------------------------------------------
# Reusable strategies
# ---------------------------------------------------------------------------

position_strategy = st.tuples(
    st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False),
)

# Operations: "add" with a position, "remove" with a dart_id index, "bounce_out"
operation_strategy = st.one_of(
    st.tuples(st.just("add"), position_strategy),
    st.tuples(st.just("remove"), st.integers(min_value=0, max_value=10)),
    st.tuples(st.just("bounce_out"), st.just(None)),
)


class TestDartCountInvariant:
    """Property 4: Dart Count Invariant.

    For any sequence of add/remove/bounce_out operations:
    - detected_count == len(known_positions)
    - detected_count >= 0
    - detected_count <= 3 (never add beyond capacity)
    - total_count == detected_count + bounce_out_count

    **Validates: Requirements AC-8.2.1, AC-8.2.4**
    """

    @settings(max_examples=100, deadline=None)
    @given(operations=st.lists(operation_strategy, min_size=1, max_size=30))
    def test_dart_count_invariant(
        self, operations: list[tuple]
    ) -> None:
        tracker = DartTracker()
        added_ids: list[int] = []

        for op_type, payload in operations:
            if op_type == "add":
                # Only add if not at capacity
                if not tracker.is_at_capacity():
                    dart_id = tracker.add_dart(payload)
                    added_ids.append(dart_id)
            elif op_type == "remove":
                if added_ids:
                    # Pick a valid index into added_ids
                    idx = payload % len(added_ids)
                    dart_id = added_ids.pop(idx)
                    tracker.remove_dart(dart_id)
            elif op_type == "bounce_out":
                if not tracker.is_at_capacity():
                    tracker.increment_bounce_out_count()

            # Invariant checks after every operation
            detected = tracker.get_detected_dart_count()
            positions = tracker.get_known_positions()
            bounce_outs = tracker.get_bounce_out_count()
            total = tracker.get_total_dart_count()

            # Count equals length of known positions
            assert detected == len(positions), (
                f"detected_count ({detected}) != len(positions) ({len(positions)})"
            )

            # Detected count never negative
            assert detected >= 0, f"detected_count ({detected}) is negative"

            # Detected count never exceeds 3
            assert detected <= 3, f"detected_count ({detected}) exceeds 3"

            # Total = detected + bounce_outs
            assert total == detected + bounce_outs, (
                f"total ({total}) != detected ({detected}) + bounce_outs ({bounce_outs})"
            )


# ---------------------------------------------------------------------------
# Motion classification strategies
# ---------------------------------------------------------------------------

from src.state_machine.events import MotionType
from src.state_machine.motion_classifier import MotionClassifier

# Default config matching the design document thresholds.
_DEFAULT_CONFIG: dict = {
    "motion_classification": {
        "dart_speed_threshold_px_per_s": 500,
        "hand_speed_threshold_px_per_s": 200,
        "dart_size_threshold_px2": 100,
        "hand_size_threshold_px2": 500,
        "dart_duration_threshold_ms": 200,
        "hand_duration_threshold_ms": 500,
    }
}

# Strategies that generate motion data clearly in the DART region.
dart_speed = st.floats(min_value=500.01, max_value=5000.0, allow_nan=False, allow_infinity=False)
dart_size = st.floats(min_value=0.0, max_value=99.99, allow_nan=False, allow_infinity=False)
dart_duration = st.floats(min_value=0.0, max_value=199.99, allow_nan=False, allow_infinity=False)

# Strategies that generate motion data clearly in the HAND region.
hand_speed = st.floats(min_value=0.0, max_value=199.99, allow_nan=False, allow_infinity=False)
hand_size = st.floats(min_value=500.01, max_value=10000.0, allow_nan=False, allow_infinity=False)
hand_duration = st.floats(min_value=500.01, max_value=10000.0, allow_nan=False, allow_infinity=False)


class TestMotionClassificationCorrectness:
    """Property: Motion Classification Correctness.

    For any motion with speed >500, size <100, duration <200 → DART.
    For any motion with speed <200, size >500, duration >500 → HAND.

    **Validates: Requirements AC-8.3.1, AC-8.3.2**
    """

    @settings(max_examples=100, deadline=None)
    @given(speed=dart_speed, size=dart_size, duration=dart_duration)
    def test_dart_motion_always_classified_as_dart(
        self, speed: float, size: float, duration: float
    ) -> None:
        classifier = MotionClassifier(_DEFAULT_CONFIG)
        motion_data = {"speed": speed, "size": size, "duration": duration}
        result = classifier.classify_motion(motion_data)
        assert result == MotionType.DART, (
            f"Expected DART for speed={speed}, size={size}, duration={duration}, got {result}"
        )

    @settings(max_examples=100, deadline=None)
    @given(speed=hand_speed, size=hand_size, duration=hand_duration)
    def test_hand_motion_always_classified_as_hand(
        self, speed: float, size: float, duration: float
    ) -> None:
        classifier = MotionClassifier(_DEFAULT_CONFIG)
        motion_data = {"speed": speed, "size": size, "duration": duration}
        result = classifier.classify_motion(motion_data)
        assert result == MotionType.HAND, (
            f"Expected HAND for speed={speed}, size={size}, duration={duration}, got {result}"
        )


# ---------------------------------------------------------------------------
# Property 1: State Transition Correctness
# ---------------------------------------------------------------------------

from src.state_machine.events import State
from src.state_machine.throw_state_machine import ThrowStateMachine
from src.fusion.dart_hit_event import DartHitEvent, Score

# Valid transitions as defined by the state diagram.
VALID_TRANSITIONS: dict[State, set[State]] = {
    State.WaitForThrow: {State.WaitForThrow, State.ThrowDetected, State.PullOutStarted, State.ThrowFinished},
    State.ThrowDetected: {State.ThrowDetected, State.WaitForThrow, State.ThrowFinished},
    State.ThrowFinished: {State.ThrowFinished, State.PullOutStarted},
    State.PullOutStarted: {State.PullOutStarted, State.WaitForThrow},
}

_SM_CONFIG: dict = {
    "state_machine": {
        "settled_timeout_ms": 500,
        "throw_timeout_ms": 2000,
        "pull_out_timeout_ms": 5000,
    },
    "bounce_out_detection": {
        "check_interval_ms": 1000,
    },
    "motion_classification": {
        "dart_speed_threshold_px_per_s": 500,
        "hand_speed_threshold_px_per_s": 200,
        "dart_size_threshold_px2": 100,
        "hand_size_threshold_px2": 500,
        "dart_duration_threshold_ms": 200,
        "hand_duration_threshold_ms": 500,
    },
}


def _make_dart_hit(board_x: float = 50.0, board_y: float = 50.0) -> DartHitEvent:
    """Create a minimal DartHitEvent for testing."""
    return DartHitEvent(
        timestamp="2024-01-01T00:00:00+00:00",
        board_x=board_x,
        board_y=board_y,
        radius=70.7,
        angle_rad=0.785,
        angle_deg=45.0,
        score=Score(base=20, multiplier=1, total=20, ring="big_single", sector=20),
        fusion_confidence=0.9,
        cameras_used=[0, 1],
        num_cameras=2,
        detections=[],
    )


# Strategy: generate a sequence of "actions" the caller can take each cycle.
action_strategy = st.one_of(
    st.just("dart_motion"),       # motion_detected=True, dart-like motion data
    st.just("hand_motion"),       # motion_detected=True, hand-like motion data
    st.just("no_motion"),         # motion_detected=False, no detection
    st.just("no_motion_with_hit"),  # motion_detected=False, detection_result present
    st.just("wait"),              # advance time by 0.6s (let settling happen)
    st.just("long_wait"),         # advance time by 2.5s (trigger timeout)
)


class TestStateTransitionCorrectness:
    """Property 1: State Transition Correctness.

    For any valid sequence of motion and detection events, the state machine
    should only perform transitions that appear in the valid transition map.

    **Validates: Requirements AC-8.1.1, AC-8.3.1**
    """

    @settings(max_examples=100, deadline=None)
    @given(actions=st.lists(action_strategy, min_size=1, max_size=30))
    def test_state_transitions_follow_diagram(self, actions: list[str]) -> None:
        sm = ThrowStateMachine(_SM_CONFIG)
        t = 1000.0  # arbitrary start time

        dart_motion_data = {"speed": 600.0, "size": 50.0, "duration": 100.0}
        hand_motion_data = {"speed": 100.0, "size": 800.0, "duration": 700.0}
        no_motion_data = {"speed": 0.0, "size": 0.0, "duration": 0.0}

        for action in actions:
            prev_state = sm.current_state

            if action == "dart_motion":
                sm.process(True, dart_motion_data, None, t)
            elif action == "hand_motion":
                sm.process(True, hand_motion_data, None, t)
            elif action == "no_motion":
                sm.process(False, no_motion_data, None, t)
            elif action == "no_motion_with_hit":
                sm.process(False, no_motion_data, _make_dart_hit(), t)
            elif action == "wait":
                t += 0.6
                sm.process(False, no_motion_data, _make_dart_hit(), t)
            elif action == "long_wait":
                t += 2.5
                sm.process(False, no_motion_data, None, t)

            new_state = sm.current_state
            assert new_state in VALID_TRANSITIONS[prev_state], (
                f"Invalid transition {prev_state.value} → {new_state.value} "
                f"after action '{action}'"
            )

            t += 0.01  # small time increment between actions
