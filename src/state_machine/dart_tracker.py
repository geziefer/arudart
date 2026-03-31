"""DartTracker class for tracking dart positions and counts.

Tracks known dart positions on the board, counts detected darts and
bounce-outs, and provides methods for dart lifecycle management.

Requirements: AC-8.2.1, AC-8.2.2, AC-8.2.3
"""

import math
import time


class DartTracker:
    """Track known dart positions, count total darts, and manage dart lifecycle.

    Attributes:
        known_darts: Dictionary mapping dart_id to (x, y, timestamp).
        bounce_out_count: Number of darts that bounced out.
        next_dart_id: Auto-incrementing dart ID counter.
    """

    def __init__(self) -> None:
        self.known_darts: dict[int, tuple[float, float, float]] = {}
        self.bounce_out_count: int = 0
        self.next_dart_id: int = 0

    def add_dart(self, position: tuple[float, float]) -> int:
        """Add a dart at the given board position.

        Args:
            position: Board coordinates (x, y) in mm.

        Returns:
            Unique dart ID for the added dart.
        """
        dart_id = self.next_dart_id
        self.next_dart_id += 1
        self.known_darts[dart_id] = (position[0], position[1], time.time())
        return dart_id

    def remove_dart(self, dart_id: int) -> None:
        """Remove a dart from the tracker.

        Args:
            dart_id: ID of the dart to remove.
        """
        self.known_darts.pop(dart_id, None)

    def increment_bounce_out_count(self) -> None:
        """Increment the bounce-out counter by 1."""
        self.bounce_out_count += 1

    def get_total_dart_count(self) -> int:
        """Return total dart count (detected + bounced out).

        Returns:
            Sum of detected darts and bounce-outs.
        """
        return len(self.known_darts) + self.bounce_out_count

    def get_detected_dart_count(self) -> int:
        """Return the number of currently detected darts on the board.

        Returns:
            Number of darts in known_darts.
        """
        return len(self.known_darts)

    def get_bounce_out_count(self) -> int:
        """Return the number of darts that bounced out.

        Returns:
            Bounce-out count.
        """
        return self.bounce_out_count

    def get_known_positions(self) -> list[tuple[float, float]]:
        """Return positions of all known darts.

        Returns:
            List of (x, y) positions.
        """
        return [(x, y) for x, y, _ in self.known_darts.values()]

    def clear_all(self) -> None:
        """Reset all tracker state."""
        self.known_darts.clear()
        self.bounce_out_count = 0
        self.next_dart_id = 0

    def is_at_capacity(self) -> bool:
        """Check if total dart count has reached 3.

        Returns:
            True if total_dart_count >= 3.
        """
        return self.get_total_dart_count() >= 3

    def get_dart_position(self, dart_id: int) -> tuple[float, float] | None:
        """Return position of a specific dart.

        Args:
            dart_id: ID of the dart to look up.

        Returns:
            (x, y) position or None if not found.
        """
        entry = self.known_darts.get(dart_id)
        if entry is None:
            return None
        return (entry[0], entry[1])

    def find_matching_dart(
        self, position: tuple[float, float], threshold: float = 30.0
    ) -> int | None:
        """Find a dart within threshold distance of the given position.

        Args:
            position: Board coordinates (x, y) to search near.
            threshold: Maximum distance in mm to consider a match.

        Returns:
            dart_id of the closest matching dart, or None if no match.
        """
        best_id: int | None = None
        best_dist = float("inf")
        for dart_id, (x, y, _) in self.known_darts.items():
            dist = math.sqrt((x - position[0]) ** 2 + (y - position[1]) ** 2)
            if dist <= threshold and dist < best_dist:
                best_id = dart_id
                best_dist = dist
        return best_id
