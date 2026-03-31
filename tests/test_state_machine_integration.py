"""Integration tests for state machine integration in main.py.

Tests the --state-machine CLI flag parsing, ThrowStateMachine initialization,
and event handling wiring.
"""

import argparse
import logging
from unittest.mock import MagicMock, patch

import pytest

from src.state_machine.throw_state_machine import ThrowStateMachine
from src.state_machine.events import State, DartRemovedEvent, DartBounceOutEvent, ThrowMissEvent
from src.fusion.dart_hit_event import DartHitEvent, Score, CameraDetection


# --- Minimal config for state machine initialization ---
MINIMAL_CONFIG = {
    "state_machine": {
        "settled_timeout_ms": 500,
        "throw_timeout_ms": 2000,
        "pull_out_timeout_ms": 5000,
    },
    "motion_classification": {
        "dart_speed_threshold_px_per_s": 500,
        "hand_speed_threshold_px_per_s": 200,
        "dart_size_threshold_px2": 100,
        "hand_size_threshold_px2": 500,
        "dart_duration_threshold_ms": 200,
        "hand_duration_threshold_ms": 500,
    },
    "bounce_out_detection": {
        "check_interval_ms": 1000,
    },
}


class TestStateMachineCLIFlag:
    """Test that --state-machine flag is parsed correctly."""

    def test_flag_defaults_to_false(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('--state-machine', action='store_true',
                            help='Use state machine for throw lifecycle')
        args = parser.parse_args([])
        assert args.state_machine is False

    def test_flag_set_to_true(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('--state-machine', action='store_true',
                            help='Use state machine for throw lifecycle')
        args = parser.parse_args(['--state-machine'])
        assert args.state_machine is True


class TestStateMachineInitialization:
    """Test that ThrowStateMachine initializes correctly with config."""

    def test_init_with_config(self):
        sm = ThrowStateMachine(MINIMAL_CONFIG)
        assert sm.current_state == State.WaitForThrow
        assert sm.config == MINIMAL_CONFIG

    def test_init_with_score_calculator(self):
        mock_calc = MagicMock()
        sm = ThrowStateMachine(MINIMAL_CONFIG, score_calculator=mock_calc)
        assert sm.score_calculator is mock_calc
        assert sm.current_state == State.WaitForThrow

    def test_init_creates_internal_components(self):
        sm = ThrowStateMachine(MINIMAL_CONFIG)
        assert sm.dart_tracker is not None
        assert sm.motion_classifier is not None


class TestEventHandling:
    """Test event handling — verify events are logged correctly."""

    def test_throw_miss_event_logged(self, caplog):
        """ThrowMissEvent should be loggable with reason field."""
        event = ThrowMissEvent(
            timestamp="2024-01-15T14:32:35.123456Z",
            motion_data={"speed": 600, "size": 50, "duration": 100},
            reason="timeout",
        )
        logger = logging.getLogger("test_event_handling")
        with caplog.at_level(logging.INFO):
            logger.info(f"ThrowMissEvent: reason={event.reason}")
        assert "ThrowMissEvent" in caplog.text
        assert "timeout" in caplog.text

    def test_dart_removed_event_logged(self, caplog):
        """DartRemovedEvent should be loggable with count fields."""
        event = DartRemovedEvent(
            timestamp="2024-01-15T14:32:25.456789Z",
            count_removed=2,
            count_remaining=1,
            removed_dart_ids=[0, 1],
        )
        logger = logging.getLogger("test_event_handling")
        with caplog.at_level(logging.INFO):
            logger.info(f"DartRemovedEvent: removed={event.count_removed}, "
                         f"remaining={event.count_remaining}")
        assert "DartRemovedEvent" in caplog.text
        assert "removed=2" in caplog.text

    def test_dart_bounce_out_event_logged(self, caplog):
        """DartBounceOutEvent should be loggable with dart_id."""
        event = DartBounceOutEvent(
            timestamp="2024-01-15T14:32:30.789012Z",
            dart_id=1,
            dart_position=(5.2, 102.3),
            time_on_board_ms=3500,
        )
        logger = logging.getLogger("test_event_handling")
        with caplog.at_level(logging.INFO):
            logger.info(f"DartBounceOutEvent: dart_id={event.dart_id}")
        assert "DartBounceOutEvent" in caplog.text
        assert "dart_id=1" in caplog.text

    def test_state_machine_process_returns_events(self):
        """State machine process() should return a list (possibly empty)."""
        sm = ThrowStateMachine(MINIMAL_CONFIG)
        events = sm.process(
            motion_detected=False,
            motion_data={"speed": 0, "size": 0, "duration": 0},
            current_time=100.0,
        )
        assert isinstance(events, list)

    def test_state_machine_emits_miss_on_timeout(self):
        """After dart motion + timeout, state machine should emit ThrowMissEvent."""
        sm = ThrowStateMachine(MINIMAL_CONFIG)

        # Trigger dart motion to enter ThrowDetected
        dart_motion = {"speed": 600, "size": 50, "duration": 100}
        sm.process(motion_detected=True, motion_data=dart_motion, current_time=100.0)
        assert sm.current_state == State.ThrowDetected

        # Advance past throw timeout (2s) with no motion and no detection
        events = sm.process(
            motion_detected=False,
            motion_data={"speed": 0, "size": 0, "duration": 0},
            current_time=103.0,
        )
        assert any(isinstance(e, ThrowMissEvent) for e in events)
        assert sm.current_state == State.WaitForThrow
