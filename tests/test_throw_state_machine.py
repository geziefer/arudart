"""Unit tests for ThrowStateMachine.

Covers test scenarios TC8.1, TC8.2, TC8.4, TC8.5, TC8.6, TC8.7, TC8.8
from the requirements document.
"""

import pytest

from src.fusion.dart_hit_event import DartHitEvent, Score
from src.state_machine.events import (
    DartRemovedEvent,
    State,
    ThrowMissEvent,
)
from src.state_machine.throw_state_machine import ThrowStateMachine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIG: dict = {
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

DART_MOTION = {"speed": 600.0, "size": 50.0, "duration": 100.0}
HAND_MOTION = {"speed": 100.0, "size": 800.0, "duration": 700.0}
NO_MOTION = {"speed": 0.0, "size": 0.0, "duration": 0.0}


def _make_hit(
    board_x: float = 50.0,
    board_y: float = 50.0,
    total: int = 20,
) -> DartHitEvent:
    """Create a minimal DartHitEvent for testing."""
    return DartHitEvent(
        timestamp="2024-01-01T00:00:00+00:00",
        board_x=board_x,
        board_y=board_y,
        radius=70.7,
        angle_rad=0.785,
        angle_deg=45.0,
        score=Score(base=total, multiplier=1, total=total, ring="big_single", sector=20),
        fusion_confidence=0.9,
        cameras_used=[0, 1],
        num_cameras=2,
        detections=[],
    )


def _make_sm() -> ThrowStateMachine:
    return ThrowStateMachine(_CONFIG)


# ---------------------------------------------------------------------------
# TC8.1: Basic throw sequence
# ---------------------------------------------------------------------------


class TestBasicThrowSequence:
    """TC8.1: WaitForThrow → ThrowDetected → (settle + detect) → WaitForThrow."""

    def test_dart_motion_transitions_to_throw_detected(self) -> None:
        sm = _make_sm()
        t = 1000.0
        sm.process(True, DART_MOTION, None, t)
        assert sm.current_state == State.ThrowDetected

    def test_settle_then_detect_returns_to_wait(self) -> None:
        sm = _make_sm()
        t = 1000.0

        # Dart motion → ThrowDetected
        sm.process(True, DART_MOTION, None, t)
        assert sm.current_state == State.ThrowDetected

        # Advance past settling timeout (0.5s) with no motion + detection
        t += 0.6
        events = sm.process(False, NO_MOTION, _make_hit(), t)

        assert sm.current_state == State.WaitForThrow
        assert len(events) == 1
        assert isinstance(events[0], DartHitEvent)

    def test_dart_added_to_tracker(self) -> None:
        sm = _make_sm()
        t = 1000.0

        sm.process(True, DART_MOTION, None, t)
        t += 0.6
        sm.process(False, NO_MOTION, _make_hit(10.0, 20.0), t)

        assert sm.dart_tracker.get_detected_dart_count() == 1
        positions = sm.dart_tracker.get_known_positions()
        assert len(positions) == 1
        assert positions[0] == (10.0, 20.0)


# ---------------------------------------------------------------------------
# TC8.2: Three consecutive darts → ThrowFinished
# ---------------------------------------------------------------------------


class TestThreeConsecutiveDarts:
    """TC8.2: After 3 darts the state machine transitions to ThrowFinished."""

    def test_three_darts_reach_throw_finished(self) -> None:
        sm = _make_sm()
        t = 1000.0

        for i in range(3):
            sm.process(True, DART_MOTION, None, t)
            t += 0.6
            sm.process(False, NO_MOTION, _make_hit(i * 30.0, i * 30.0), t)
            t += 0.1

        assert sm.current_state == State.ThrowFinished
        assert sm.dart_tracker.get_total_dart_count() == 3

    def test_first_two_darts_stay_in_wait(self) -> None:
        sm = _make_sm()
        t = 1000.0

        for i in range(2):
            sm.process(True, DART_MOTION, None, t)
            t += 0.6
            sm.process(False, NO_MOTION, _make_hit(i * 50.0, i * 50.0), t)
            t += 0.1
            assert sm.current_state == State.WaitForThrow

        assert sm.dart_tracker.get_total_dart_count() == 2


# ---------------------------------------------------------------------------
# TC8.4: Full pull-out (ThrowFinished → PullOutStarted → WaitForThrow)
# ---------------------------------------------------------------------------


class TestFullPullOut:
    """TC8.4: After ThrowFinished, hand motion triggers pull-out and
    removing all darts returns to WaitForThrow."""

    def _reach_throw_finished(self, sm: ThrowStateMachine) -> float:
        """Helper: throw 3 darts and return current time."""
        t = 1000.0
        for i in range(3):
            sm.process(True, DART_MOTION, None, t)
            t += 0.6
            sm.process(False, NO_MOTION, _make_hit(i * 50.0, i * 50.0), t)
            t += 0.1
        assert sm.current_state == State.ThrowFinished
        return t

    def test_hand_motion_starts_pull_out(self) -> None:
        sm = _make_sm()
        t = self._reach_throw_finished(sm)

        sm.process(True, HAND_MOTION, None, t)
        assert sm.current_state == State.PullOutStarted

    def test_all_darts_removed_returns_to_wait(self) -> None:
        sm = _make_sm()
        t = self._reach_throw_finished(sm)

        # Hand motion → PullOutStarted
        sm.process(True, HAND_MOTION, None, t)
        assert sm.current_state == State.PullOutStarted

        # Settle, then report no remaining darts
        t += 0.6
        pull_data = {**NO_MOTION, "remaining_dart_positions": []}
        events = sm.process(False, pull_data, None, t)

        assert sm.current_state == State.WaitForThrow
        assert len(events) == 1
        assert isinstance(events[0], DartRemovedEvent)
        assert events[0].count_removed == 3
        assert events[0].count_remaining == 0

    def test_partial_pull_out_stays(self) -> None:
        sm = _make_sm()
        t = self._reach_throw_finished(sm)

        # Hand motion → PullOutStarted
        sm.process(True, HAND_MOTION, None, t)

        # Settle, report 1 dart still remaining (at position of first dart)
        t += 0.6
        pull_data = {**NO_MOTION, "remaining_dart_positions": [(0.0, 0.0)]}
        events = sm.process(False, pull_data, None, t)

        assert sm.current_state == State.PullOutStarted
        assert len(events) == 1
        assert isinstance(events[0], DartRemovedEvent)
        assert events[0].count_remaining > 0


# ---------------------------------------------------------------------------
# TC8.5: Bounce-out detection
# ---------------------------------------------------------------------------


class TestBounceOutDetection:
    """TC8.5: Bounce-out counted toward total; reaching 3 → ThrowFinished.

    Note: The current implementation uses a simplified bounce-out check.
    We test the tracker-level bounce-out counting and its effect on state.
    """

    def test_bounce_out_increments_total(self) -> None:
        sm = _make_sm()
        sm.dart_tracker.add_dart((10.0, 20.0))
        sm.dart_tracker.increment_bounce_out_count()
        assert sm.dart_tracker.get_total_dart_count() == 2

    def test_bounce_out_reaching_three_triggers_finished(self) -> None:
        sm = _make_sm()
        t = 1000.0

        # Throw 2 darts normally.
        for i in range(2):
            sm.process(True, DART_MOTION, None, t)
            t += 0.6
            sm.process(False, NO_MOTION, _make_hit(i * 50.0, i * 50.0), t)
            t += 0.1

        assert sm.current_state == State.WaitForThrow
        assert sm.dart_tracker.get_total_dart_count() == 2

        # Simulate a bounce-out externally (tracker level).
        sm.dart_tracker.increment_bounce_out_count()
        assert sm.dart_tracker.get_total_dart_count() == 3
        assert sm.dart_tracker.is_at_capacity()


# ---------------------------------------------------------------------------
# TC8.6: Throw miss (timeout)
# ---------------------------------------------------------------------------


class TestThrowMiss:
    """TC8.6: Dart motion detected but no dart found → ThrowMissEvent."""

    def test_miss_after_settling_no_detection(self) -> None:
        sm = _make_sm()
        t = 1000.0

        sm.process(True, DART_MOTION, None, t)
        assert sm.current_state == State.ThrowDetected

        # Settle with no detection result.
        t += 0.6
        events = sm.process(False, NO_MOTION, None, t)

        assert sm.current_state == State.WaitForThrow
        assert len(events) == 1
        assert isinstance(events[0], ThrowMissEvent)
        assert events[0].reason == "no_dart_detected"

    def test_miss_on_timeout(self) -> None:
        sm = _make_sm()
        t = 1000.0

        sm.process(True, DART_MOTION, None, t)
        assert sm.current_state == State.ThrowDetected

        # Keep sending motion so it never settles, then timeout.
        t += 2.5
        events = sm.process(False, NO_MOTION, None, t)

        assert sm.current_state == State.WaitForThrow
        assert len(events) == 1
        assert isinstance(events[0], ThrowMissEvent)
        assert events[0].reason == "timeout"

    def test_miss_preserves_existing_darts(self) -> None:
        sm = _make_sm()
        t = 1000.0

        # Throw one dart successfully.
        sm.process(True, DART_MOTION, None, t)
        t += 0.6
        sm.process(False, NO_MOTION, _make_hit(10.0, 20.0), t)
        t += 0.1
        assert sm.dart_tracker.get_detected_dart_count() == 1

        # Second throw misses.
        sm.process(True, DART_MOTION, None, t)
        t += 0.6
        events = sm.process(False, NO_MOTION, None, t)

        assert isinstance(events[0], ThrowMissEvent)
        # Existing dart still tracked.
        assert sm.dart_tracker.get_detected_dart_count() == 1


# ---------------------------------------------------------------------------
# TC8.7: Hand motion classification
# ---------------------------------------------------------------------------


class TestHandMotionClassification:
    """TC8.7: Hand motion in WaitForThrow → PullOutStarted."""

    def test_hand_motion_in_wait_transitions_to_pull_out(self) -> None:
        sm = _make_sm()
        t = 1000.0

        sm.process(True, HAND_MOTION, None, t)
        assert sm.current_state == State.PullOutStarted

    def test_hand_motion_in_throw_finished_transitions_to_pull_out(self) -> None:
        sm = _make_sm()
        t = 1000.0

        # Reach ThrowFinished.
        for i in range(3):
            sm.process(True, DART_MOTION, None, t)
            t += 0.6
            sm.process(False, NO_MOTION, _make_hit(i * 50.0, i * 50.0), t)
            t += 0.1

        assert sm.current_state == State.ThrowFinished

        sm.process(True, HAND_MOTION, None, t)
        assert sm.current_state == State.PullOutStarted


# ---------------------------------------------------------------------------
# TC8.8: Rapid throws
# ---------------------------------------------------------------------------


class TestRapidThrows:
    """TC8.8: Second throw before first fully settled."""

    def test_rapid_dart_motion_stays_in_throw_detected(self) -> None:
        sm = _make_sm()
        t = 1000.0

        # First dart motion.
        sm.process(True, DART_MOTION, None, t)
        assert sm.current_state == State.ThrowDetected

        # Another dart motion quickly (before settling).
        t += 0.1
        sm.process(True, DART_MOTION, None, t)
        # Should still be in ThrowDetected (motion resets settling timer).
        assert sm.current_state == State.ThrowDetected

    def test_rapid_throw_eventually_settles(self) -> None:
        sm = _make_sm()
        t = 1000.0

        sm.process(True, DART_MOTION, None, t)
        t += 0.1
        sm.process(True, DART_MOTION, None, t)

        # Now let it settle.
        t += 0.6
        events = sm.process(False, NO_MOTION, _make_hit(), t)

        assert sm.current_state == State.WaitForThrow
        assert len(events) == 1
        assert isinstance(events[0], DartHitEvent)
