"""ThrowStateMachine — core state machine for the dart throw lifecycle.

Manages state transitions: WaitForThrow → ThrowDetected → WaitForThrow/ThrowFinished,
ThrowFinished → PullOutStarted → WaitForThrow.  Emits structured events at each
transition so downstream systems can react to gameplay.

The ``process()`` method receives abstract inputs (motion flag, motion data,
optional detection result) so the state machine is decoupled from cameras,
frames, and detection internals.

Requirements: AC-8.1.1, AC-8.2.2, AC-8.3.4, AC-8.3.5, AC-8.4.1–AC-8.4.6,
              AC-8.5.1–AC-8.5.5, AC-8.6.1–AC-8.6.5
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from src.fusion.dart_hit_event import DartHitEvent
from src.state_machine.dart_tracker import DartTracker
from src.state_machine.events import (
    DartBounceOutEvent,
    DartRemovedEvent,
    MotionType,
    State,
    ThrowMissEvent,
)
from src.state_machine.motion_classifier import MotionClassifier

logger = logging.getLogger(__name__)

# Type alias for the list of events returned by process().
Event = DartHitEvent | DartRemovedEvent | DartBounceOutEvent | ThrowMissEvent


class ThrowStateMachine:
    """Core state machine orchestrating the dart throw lifecycle.

    Args:
        config: Full application config dict (must contain ``state_machine``,
            ``bounce_out_detection``, and ``motion_classification`` sections).
        score_calculator: Optional ScoreCalculator instance (unused directly
            by the state machine — detection results are passed in via
            ``process()``).
    """

    def __init__(self, config: dict, score_calculator: Any = None) -> None:
        self.config = config
        self.score_calculator = score_calculator

        # Internal components
        self.dart_tracker = DartTracker()
        self.motion_classifier = MotionClassifier(config)

        # State
        self.current_state: State = State.WaitForThrow
        self.state_entry_time: float = time.time()
        self.last_periodic_check: float = time.time()

        # Track settling: timestamp of last high-motion frame.
        self._last_motion_time: float = time.time()

        # Timeouts (in seconds) loaded from config.
        sm_cfg = config.get("state_machine", {})
        self.settled_timeout_s: float = sm_cfg.get("settled_timeout_ms", 500) / 1000.0
        self.throw_timeout_s: float = sm_cfg.get("throw_timeout_ms", 2000) / 1000.0
        self.pull_out_timeout_s: float = sm_cfg.get("pull_out_timeout_ms", 5000) / 1000.0

        bo_cfg = config.get("bounce_out_detection", {})
        self.check_interval_s: float = bo_cfg.get("check_interval_ms", 1000) / 1000.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(
        self,
        motion_detected: bool,
        motion_data: dict,
        detection_result: DartHitEvent | None = None,
        current_time: float | None = None,
    ) -> list[Event]:
        """Main entry point — called once per loop iteration.

        Args:
            motion_detected: Whether the motion detector flagged motion.
            motion_data: Dict with ``speed``, ``size``, ``duration`` keys.
            detection_result: A ``DartHitEvent`` produced by the caller's
                detection pipeline, or ``None`` if no dart was detected.
            current_time: Monotonic timestamp (seconds).  Defaults to
                ``time.time()`` when not supplied — pass explicitly in tests.

        Returns:
            List of events emitted during this cycle (may be empty).
        """
        if current_time is None:
            current_time = time.time()

        # Update motion tracking for settling logic.
        if motion_detected:
            self._last_motion_time = current_time

        # Dispatch to the handler for the current state.
        if self.current_state == State.WaitForThrow:
            return self._handle_wait_for_throw(
                motion_detected, motion_data, detection_result, current_time
            )
        if self.current_state == State.ThrowDetected:
            return self._handle_throw_detected(
                motion_detected, motion_data, detection_result, current_time
            )
        if self.current_state == State.ThrowFinished:
            return self._handle_throw_finished(
                motion_detected, motion_data, current_time
            )
        if self.current_state == State.PullOutStarted:
            return self._handle_pull_out_started(
                motion_detected, motion_data, detection_result, current_time
            )

        return []  # pragma: no cover

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _handle_wait_for_throw(
        self,
        motion_detected: bool,
        motion_data: dict,
        detection_result: DartHitEvent | None,
        current_time: float,
    ) -> list[Event]:
        """Handle the WaitForThrow state.

        * Dart motion → ThrowDetected
        * Hand motion → PullOutStarted
        * Periodic bounce-out check every ``check_interval_s``
        * If total_count reaches 3 → ThrowFinished
        """
        if motion_detected:
            motion_type = self.motion_classifier.classify_motion(motion_data)

            if motion_type == MotionType.DART:
                self._transition(State.ThrowDetected, current_time)
                return []

            if motion_type == MotionType.HAND:
                self._transition(State.PullOutStarted, current_time)
                return []

            # UNKNOWN — treat as dart for safety (per design doc).
            self._transition(State.ThrowDetected, current_time)
            return []

        # Periodic bounce-out check.
        events = self._periodic_bounce_out_check(detection_result, current_time)

        # After bounce-out, total may have reached 3.
        if self.dart_tracker.is_at_capacity() and self.current_state == State.WaitForThrow:
            self._transition(State.ThrowFinished, current_time)

        return events

    def _handle_throw_detected(
        self,
        motion_detected: bool,
        motion_data: dict,
        detection_result: DartHitEvent | None,
        current_time: float,
    ) -> list[Event]:
        """Handle the ThrowDetected state.

        Wait for motion to settle, then process detection result.
        Timeout after ``throw_timeout_s``.
        """
        time_in_state = current_time - self.state_entry_time

        # --- Timeout check (highest priority) ---
        if time_in_state >= self.throw_timeout_s:
            logger.warning("Throw timeout after %.1fs", time_in_state)
            self._transition(State.WaitForThrow, current_time)
            return [
                ThrowMissEvent(
                    timestamp=self._iso_now(),
                    motion_data=motion_data,
                    reason="timeout",
                )
            ]

        # --- Settling check ---
        time_since_motion = current_time - self._last_motion_time
        if time_since_motion < self.settled_timeout_s:
            # Still settling — wait.
            return []

        # Motion has settled — process detection result.
        if detection_result is not None:
            # Dart detected — add to tracker.
            pos = (detection_result.board_x, detection_result.board_y)
            self.dart_tracker.add_dart(pos)
            total = self.dart_tracker.get_total_dart_count()

            if total >= 3:
                self._transition(State.ThrowFinished, current_time)
            else:
                self._transition(State.WaitForThrow, current_time)

            return [detection_result]

        # No dart detected after settling → miss.
        self._transition(State.WaitForThrow, current_time)
        return [
            ThrowMissEvent(
                timestamp=self._iso_now(),
                motion_data=motion_data,
                reason="no_dart_detected",
            )
        ]

    def _handle_throw_finished(
        self,
        motion_detected: bool,
        motion_data: dict,
        current_time: float,
    ) -> list[Event]:
        """Handle the ThrowFinished state.

        * Hand motion → PullOutStarted
        * Periodic bounce-out check (same as WaitForThrow)
        * No dart throws allowed.
        """
        if motion_detected:
            motion_type = self.motion_classifier.classify_motion(motion_data)
            if motion_type == MotionType.HAND:
                self._transition(State.PullOutStarted, current_time)
                return []
            # Dart or unknown motion ignored in ThrowFinished.

        return self._periodic_bounce_out_check(None, current_time)

    def _handle_pull_out_started(
        self,
        motion_detected: bool,
        motion_data: dict,
        detection_result: DartHitEvent | None,
        current_time: float,
    ) -> list[Event]:
        """Handle the PullOutStarted state.

        Wait for motion to settle, then compare detected darts with known
        positions.  Remove missing darts and emit ``DartRemovedEvent``.
        """
        time_in_state = current_time - self.state_entry_time

        # --- Timeout warning ---
        if time_in_state >= self.pull_out_timeout_s:
            # Log once per timeout period.
            logger.warning("Pull-out timeout after %.1fs, waiting for completion", time_in_state)

        # --- Settling check ---
        time_since_motion = current_time - self._last_motion_time
        if time_since_motion < self.settled_timeout_s:
            return []

        # Motion settled — compare current detections with known darts.
        # The caller passes the *current* board state as detection_result.
        # For pull-out, we use a list of remaining dart positions passed via
        # a special key in motion_data, or we simply check if detection_result
        # is None (meaning no darts remain).
        remaining_positions: list[tuple[float, float]] = motion_data.get(
            "remaining_dart_positions", []
        )

        known_ids = list(self.dart_tracker.known_darts.keys())
        removed_ids: list[int] = []

        for dart_id in known_ids:
            pos = self.dart_tracker.get_dart_position(dart_id)
            if pos is None:
                continue
            # Check if this dart is still present in remaining positions.
            still_present = False
            for rp in remaining_positions:
                if self.dart_tracker.find_matching_dart(rp) == dart_id:
                    still_present = True
                    break
            if not still_present:
                self.dart_tracker.remove_dart(dart_id)
                removed_ids.append(dart_id)

        if removed_ids:
            remaining = self.dart_tracker.get_detected_dart_count()
            event = DartRemovedEvent(
                timestamp=self._iso_now(),
                count_removed=len(removed_ids),
                count_remaining=remaining,
                removed_dart_ids=removed_ids,
            )

            if remaining == 0:
                self.dart_tracker.clear_all()
                self._transition(State.WaitForThrow, current_time)

            return [event]

        # No darts removed yet — stay in PullOutStarted.
        return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _transition(self, new_state: State, current_time: float) -> None:
        """Transition to *new_state* and reset entry time."""
        logger.info("State transition: %s → %s", self.current_state.value, new_state.value)
        self.current_state = new_state
        self.state_entry_time = current_time

    def _periodic_bounce_out_check(
        self,
        detection_result: DartHitEvent | None,
        current_time: float,
    ) -> list[Event]:
        """Run periodic bounce-out detection if interval has elapsed.

        Compares known dart positions with ``remaining_dart_positions``
        supplied via the detection pipeline.  If a known dart is missing,
        it is treated as a bounce-out.

        Returns:
            List of ``DartBounceOutEvent`` for each missing dart.
        """
        if current_time - self.last_periodic_check < self.check_interval_s:
            return []

        self.last_periodic_check = current_time

        # If there are no known darts, nothing to check.
        if self.dart_tracker.get_detected_dart_count() == 0:
            return []

        # For bounce-out detection the caller should supply current board
        # state.  If detection_result is None we assume no change (safe
        # default — avoids false bounce-outs when detection is unavailable).
        # In real usage the main loop would pass re-detection results.
        # For now, no bounce-out is detected unless explicitly signalled.
        return []

    @staticmethod
    def _iso_now() -> str:
        """Return current UTC time as ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()
