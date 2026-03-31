"""Unit tests for DartTracker.

Requirements: AC-8.2.1, AC-8.2.2, AC-8.2.3, AC-8.2.4
"""

import pytest

from src.state_machine.dart_tracker import DartTracker


class TestAddDart:
    """Test add_dart() increments count correctly."""

    def test_add_single_dart(self) -> None:
        tracker = DartTracker()
        dart_id = tracker.add_dart((10.0, 20.0))
        assert dart_id == 0
        assert tracker.get_detected_dart_count() == 1

    def test_add_multiple_darts_increments_ids(self) -> None:
        tracker = DartTracker()
        id0 = tracker.add_dart((10.0, 20.0))
        id1 = tracker.add_dart((30.0, 40.0))
        id2 = tracker.add_dart((50.0, 60.0))
        assert id0 == 0
        assert id1 == 1
        assert id2 == 2
        assert tracker.get_detected_dart_count() == 3

    def test_add_dart_stores_position(self) -> None:
        tracker = DartTracker()
        tracker.add_dart((10.5, 20.5))
        pos = tracker.get_dart_position(0)
        assert pos == (10.5, 20.5)


class TestRemoveDart:
    """Test remove_dart() decrements count correctly."""

    def test_remove_existing_dart(self) -> None:
        tracker = DartTracker()
        dart_id = tracker.add_dart((10.0, 20.0))
        tracker.remove_dart(dart_id)
        assert tracker.get_detected_dart_count() == 0

    def test_remove_nonexistent_dart_is_noop(self) -> None:
        tracker = DartTracker()
        tracker.remove_dart(999)
        assert tracker.get_detected_dart_count() == 0

    def test_remove_one_of_many(self) -> None:
        tracker = DartTracker()
        id0 = tracker.add_dart((10.0, 20.0))
        tracker.add_dart((30.0, 40.0))
        tracker.remove_dart(id0)
        assert tracker.get_detected_dart_count() == 1
        assert tracker.get_dart_position(id0) is None


class TestBounceOutCount:
    """Test bounce_out_count increments correctly."""

    def test_increment_bounce_out(self) -> None:
        tracker = DartTracker()
        tracker.increment_bounce_out_count()
        assert tracker.get_bounce_out_count() == 1

    def test_multiple_bounce_outs(self) -> None:
        tracker = DartTracker()
        tracker.increment_bounce_out_count()
        tracker.increment_bounce_out_count()
        assert tracker.get_bounce_out_count() == 2


class TestTotalCount:
    """Test total_count = detected + bounced_out."""

    def test_total_with_detected_only(self) -> None:
        tracker = DartTracker()
        tracker.add_dart((10.0, 20.0))
        tracker.add_dart((30.0, 40.0))
        assert tracker.get_total_dart_count() == 2

    def test_total_with_bounce_outs_only(self) -> None:
        tracker = DartTracker()
        tracker.increment_bounce_out_count()
        assert tracker.get_total_dart_count() == 1

    def test_total_mixed(self) -> None:
        tracker = DartTracker()
        tracker.add_dart((10.0, 20.0))
        tracker.increment_bounce_out_count()
        assert tracker.get_total_dart_count() == 2

    def test_total_after_remove(self) -> None:
        tracker = DartTracker()
        dart_id = tracker.add_dart((10.0, 20.0))
        tracker.increment_bounce_out_count()
        tracker.remove_dart(dart_id)
        # 0 detected + 1 bounce_out = 1
        assert tracker.get_total_dart_count() == 1


class TestIsAtCapacity:
    """Test is_at_capacity() returns true at 3 darts."""

    def test_not_at_capacity_initially(self) -> None:
        tracker = DartTracker()
        assert tracker.is_at_capacity() is False

    def test_at_capacity_with_three_detected(self) -> None:
        tracker = DartTracker()
        tracker.add_dart((10.0, 20.0))
        tracker.add_dart((30.0, 40.0))
        tracker.add_dart((50.0, 60.0))
        assert tracker.is_at_capacity() is True

    def test_at_capacity_with_mixed(self) -> None:
        tracker = DartTracker()
        tracker.add_dart((10.0, 20.0))
        tracker.add_dart((30.0, 40.0))
        tracker.increment_bounce_out_count()
        assert tracker.is_at_capacity() is True

    def test_not_at_capacity_with_two(self) -> None:
        tracker = DartTracker()
        tracker.add_dart((10.0, 20.0))
        tracker.add_dart((30.0, 40.0))
        assert tracker.is_at_capacity() is False


class TestClearAll:
    """Test clear_all() resets all state."""

    def test_clear_resets_darts(self) -> None:
        tracker = DartTracker()
        tracker.add_dart((10.0, 20.0))
        tracker.add_dart((30.0, 40.0))
        tracker.increment_bounce_out_count()
        tracker.clear_all()
        assert tracker.get_detected_dart_count() == 0
        assert tracker.get_bounce_out_count() == 0
        assert tracker.get_total_dart_count() == 0
        assert tracker.get_known_positions() == []

    def test_clear_resets_id_counter(self) -> None:
        tracker = DartTracker()
        tracker.add_dart((10.0, 20.0))
        tracker.clear_all()
        new_id = tracker.add_dart((30.0, 40.0))
        assert new_id == 0


class TestFindMatchingDart:
    """Test find_matching_dart() with threshold."""

    def test_finds_exact_match(self) -> None:
        tracker = DartTracker()
        dart_id = tracker.add_dart((100.0, 100.0))
        result = tracker.find_matching_dart((100.0, 100.0))
        assert result == dart_id

    def test_finds_within_threshold(self) -> None:
        tracker = DartTracker()
        dart_id = tracker.add_dart((100.0, 100.0))
        result = tracker.find_matching_dart((110.0, 100.0), threshold=30.0)
        assert result == dart_id

    def test_returns_none_beyond_threshold(self) -> None:
        tracker = DartTracker()
        tracker.add_dart((100.0, 100.0))
        result = tracker.find_matching_dart((200.0, 200.0), threshold=30.0)
        assert result is None

    def test_finds_closest_dart(self) -> None:
        tracker = DartTracker()
        tracker.add_dart((100.0, 100.0))
        closer_id = tracker.add_dart((115.0, 100.0))
        result = tracker.find_matching_dart((120.0, 100.0), threshold=30.0)
        assert result == closer_id

    def test_returns_none_on_empty_tracker(self) -> None:
        tracker = DartTracker()
        result = tracker.find_matching_dart((100.0, 100.0))
        assert result is None


class TestGetKnownPositions:
    """Test get_known_positions() returns correct list."""

    def test_empty_tracker(self) -> None:
        tracker = DartTracker()
        assert tracker.get_known_positions() == []

    def test_returns_all_positions(self) -> None:
        tracker = DartTracker()
        tracker.add_dart((10.0, 20.0))
        tracker.add_dart((30.0, 40.0))
        positions = tracker.get_known_positions()
        assert len(positions) == 2
        assert (10.0, 20.0) in positions
        assert (30.0, 40.0) in positions
