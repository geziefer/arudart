"""RoundTracker — accumulates dart hits per round and emits SSE event dicts.

Converts DartHitEvent objects into dart_scored and round_complete payloads.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5
"""

from __future__ import annotations

from src.fusion.dart_hit_event import DartHitEvent


def score_to_label(score) -> str:
    """Convert a Score to a short label string (e.g. T20, D16, SB, Miss).

    Args:
        score: Score dataclass with ring, sector, and total attributes.

    Returns:
        Short label string without points suffix.
    """
    ring = score.ring
    sector = score.sector

    if ring == "miss":
        return "Miss"
    elif ring == "bull":
        return "DB"
    elif ring == "single_bull":
        return "SB"
    elif ring == "triple":
        return f"T{sector}"
    elif ring == "double":
        return f"D{sector}"
    elif ring == "single":
        return f"S{sector}"
    else:
        return f"{ring}{sector}"


class RoundTracker:
    """Tracks darts within a round and emits dart_scored / round_complete dicts."""

    def __init__(self) -> None:
        self._throws: list[dict] = []

    def process_hit(self, dart_hit: DartHitEvent) -> list[dict]:
        """Process a dart hit and return SSE event dicts.

        Args:
            dart_hit: DartHitEvent from the state machine.

        Returns:
            [dart_scored_dict] for darts 1 and 2.
            [dart_scored_dict, round_complete_dict] for dart 3.
        """
        dart_number = len(self._throws) + 1
        label = score_to_label(dart_hit.score)
        points = dart_hit.score.total

        dart_scored: dict = {
            "event": "dart_scored",
            "dart_number": dart_number,
            "label": label,
            "points": points,
        }
        self._throws.append({
            "dart_number": dart_number,
            "label": label,
            "points": points,
        })

        result: list[dict] = [dart_scored]

        if dart_number == 3:
            total = sum(t["points"] for t in self._throws)
            round_complete: dict = {
                "event": "round_complete",
                "throws": list(self._throws),
                "total": total,
            }
            result.append(round_complete)

        return result

    def reset(self) -> None:
        """Clear accumulated throws and reset dart counter."""
        self._throws = []

    @property
    def dart_count(self) -> int:
        """Current number of darts in this round (0–3)."""
        return len(self._throws)
