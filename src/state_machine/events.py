"""Event dataclasses and enums for the throw state machine.

Defines the State enum for state machine states, MotionType enum for
motion classification, and event dataclasses for dart removal, bounce-out,
and throw miss events. DartHitEvent lives in src/fusion/dart_hit_event.py.
"""

from dataclasses import dataclass
from enum import Enum


class State(Enum):
    """State machine states for the dart throw lifecycle."""

    WaitForThrow = "wait_for_throw"
    ThrowDetected = "throw_detected"
    ThrowFinished = "throw_finished"
    PullOutStarted = "pull_out_started"


class MotionType(Enum):
    """Classification of detected motion."""

    DART = "dart"
    HAND = "hand"
    UNKNOWN = "unknown"


@dataclass
class DartRemovedEvent:
    """Event emitted when darts are removed from the board.

    Attributes:
        timestamp: ISO 8601 formatted timestamp.
        count_removed: Number of darts removed in this event.
        count_remaining: Number of darts still on the board.
        removed_dart_ids: IDs of the removed darts.
    """

    timestamp: str
    count_removed: int
    count_remaining: int
    removed_dart_ids: list[int]

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "event_type": "dart_removed",
            "timestamp": self.timestamp,
            "count_removed": self.count_removed,
            "count_remaining": self.count_remaining,
            "removed_dart_ids": self.removed_dart_ids,
        }


@dataclass
class DartBounceOutEvent:
    """Event emitted when a dart bounces out of the board.

    Attributes:
        timestamp: ISO 8601 formatted timestamp.
        dart_id: ID of the dart that bounced out.
        dart_position: Last known position as (x_mm, y_mm).
        time_on_board_ms: Time the dart was on the board in milliseconds.
    """

    timestamp: str
    dart_id: int
    dart_position: tuple[float, float]
    time_on_board_ms: int

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "event_type": "dart_bounce_out",
            "timestamp": self.timestamp,
            "dart_id": self.dart_id,
            "dart_position": {
                "x_mm": self.dart_position[0],
                "y_mm": self.dart_position[1],
            },
            "time_on_board_ms": self.time_on_board_ms,
        }


@dataclass
class ThrowMissEvent:
    """Event emitted when a throw misses the board.

    Attributes:
        timestamp: ISO 8601 formatted timestamp.
        motion_data: Motion detection data from the throw.
        reason: Why the miss was detected ("timeout" or "no_dart_detected").
    """

    timestamp: str
    motion_data: dict
    reason: str

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "event_type": "throw_miss",
            "timestamp": self.timestamp,
            "motion_data": self.motion_data,
            "reason": self.reason,
        }
