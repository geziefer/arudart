"""Unit tests for the Web API layer (EventBus, RoundTracker, Server).

Tests cover:
- RoundTracker: score labels, dart counting, round completion, reset
- EventBus: basic publish/subscribe, no-op when no subscribers
- Server: endpoint content types, reset responses
"""

import asyncio

import pytest
import pytest_asyncio

from src.api.event_bus import EventBus
from src.api.round_tracker import RoundTracker, score_to_label
from src.api.server import create_app
from src.fusion.dart_hit_event import DartHitEvent, Score
from src.state_machine.events import State


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hit(ring: str, sector: int | None, total: int, multiplier: int = 1, base: int = 0) -> DartHitEvent:
    """Create a minimal DartHitEvent for testing."""
    return DartHitEvent(
        timestamp="2025-01-01T00:00:00Z",
        board_x=0.0,
        board_y=0.0,
        radius=50.0,
        angle_rad=0.0,
        angle_deg=0.0,
        score=Score(base=base or total, multiplier=multiplier, total=total, ring=ring, sector=sector),
        fusion_confidence=0.9,
        cameras_used=[0],
        num_cameras=1,
        detections=[],
    )


# ---------------------------------------------------------------------------
# RoundTracker unit tests
# ---------------------------------------------------------------------------

class TestRoundTrackerLabels:
    """Test all 6 ring types produce correct score labels."""

    def test_triple_label(self):
        hit = _make_hit("triple", 20, 60, multiplier=3, base=20)
        result = RoundTracker().process_hit(hit)
        assert result[0]["label"] == "T20"

    def test_double_label(self):
        hit = _make_hit("double", 16, 32, multiplier=2, base=16)
        result = RoundTracker().process_hit(hit)
        assert result[0]["label"] == "D16"

    def test_single_label(self):
        hit = _make_hit("single", 5, 5)
        result = RoundTracker().process_hit(hit)
        assert result[0]["label"] == "S5"

    def test_single_bull_label(self):
        hit = _make_hit("single_bull", None, 25)
        result = RoundTracker().process_hit(hit)
        assert result[0]["label"] == "SB"

    def test_double_bull_label(self):
        hit = _make_hit("bull", None, 50)
        result = RoundTracker().process_hit(hit)
        assert result[0]["label"] == "DB"

    def test_miss_label(self):
        hit = _make_hit("miss", None, 0)
        result = RoundTracker().process_hit(hit)
        assert result[0]["label"] == "Miss"


class TestRoundTrackerDartCount:
    """Test dart_count property reflects current state."""

    def test_initial_count_is_zero(self):
        tracker = RoundTracker()
        assert tracker.dart_count == 0

    def test_count_increments(self):
        tracker = RoundTracker()
        tracker.process_hit(_make_hit("single", 1, 1))
        assert tracker.dart_count == 1
        tracker.process_hit(_make_hit("single", 2, 2))
        assert tracker.dart_count == 2

    def test_count_after_three_darts(self):
        tracker = RoundTracker()
        for i in range(3):
            tracker.process_hit(_make_hit("single", i + 1, i + 1))
        assert tracker.dart_count == 3


class TestRoundTrackerReset:
    """Test reset() clears state after partial round."""

    def test_reset_after_one_dart(self):
        tracker = RoundTracker()
        tracker.process_hit(_make_hit("single", 1, 1))
        tracker.reset()
        assert tracker.dart_count == 0

    def test_reset_after_two_darts(self):
        tracker = RoundTracker()
        tracker.process_hit(_make_hit("single", 1, 1))
        tracker.process_hit(_make_hit("single", 2, 2))
        tracker.reset()
        assert tracker.dart_count == 0

    def test_dart_number_restarts_after_reset(self):
        tracker = RoundTracker()
        tracker.process_hit(_make_hit("single", 1, 1))
        tracker.process_hit(_make_hit("single", 2, 2))
        tracker.reset()
        result = tracker.process_hit(_make_hit("single", 3, 3))
        assert result[0]["dart_number"] == 1


class TestRoundTrackerRoundComplete:
    """Test round completion logic."""

    def test_first_two_darts_no_round_complete(self):
        tracker = RoundTracker()
        r1 = tracker.process_hit(_make_hit("single", 1, 1))
        r2 = tracker.process_hit(_make_hit("single", 2, 2))
        assert len(r1) == 1
        assert len(r2) == 1
        assert r1[0]["event"] == "dart_scored"
        assert r2[0]["event"] == "dart_scored"

    def test_third_dart_emits_round_complete(self):
        tracker = RoundTracker()
        tracker.process_hit(_make_hit("single", 1, 10))
        tracker.process_hit(_make_hit("single", 2, 20))
        result = tracker.process_hit(_make_hit("triple", 20, 60, multiplier=3, base=20))
        assert len(result) == 2
        assert result[0]["event"] == "dart_scored"
        assert result[1]["event"] == "round_complete"

    def test_round_complete_total(self):
        tracker = RoundTracker()
        tracker.process_hit(_make_hit("single", 1, 10))
        tracker.process_hit(_make_hit("single", 2, 20))
        result = tracker.process_hit(_make_hit("triple", 20, 60, multiplier=3, base=20))
        assert result[1]["total"] == 90

    def test_round_complete_throws_order(self):
        tracker = RoundTracker()
        tracker.process_hit(_make_hit("single", 1, 10))
        tracker.process_hit(_make_hit("double", 5, 10, multiplier=2, base=5))
        result = tracker.process_hit(_make_hit("triple", 20, 60, multiplier=3, base=20))
        throws = result[1]["throws"]
        assert len(throws) == 3
        assert throws[0]["dart_number"] == 1
        assert throws[1]["dart_number"] == 2
        assert throws[2]["dart_number"] == 3


# ---------------------------------------------------------------------------
# EventBus unit tests
# ---------------------------------------------------------------------------

class TestEventBus:
    """Test EventBus basic behavior."""

    def test_publish_no_subscribers_is_noop(self):
        """publish() with no subscribers should not raise."""
        bus = EventBus()
        loop = asyncio.new_event_loop()
        bus.set_loop(loop)
        bus.publish({"event": "test"})  # Should not raise
        loop.close()

    def test_publish_before_set_loop_drops_silently(self):
        """publish() before set_loop() should drop event silently."""
        bus = EventBus()
        bus.publish({"event": "test"})  # Should not raise

    def test_subscriber_count_increments_and_decrements(self):
        """subscriber_count should track active subscribers."""
        bus = EventBus()
        loop = asyncio.new_event_loop()
        bus.set_loop(loop)

        assert bus.subscriber_count == 0

        async def _run():
            count_during = None
            async def _consume():
                nonlocal count_during
                async for _ in bus.subscribe():
                    count_during = bus.subscriber_count
                    break

            task = loop.create_task(_consume())
            # Give the coroutine a chance to register
            await asyncio.sleep(0.01)
            assert bus.subscriber_count == 1
            bus.publish({"event": "ping"})
            await asyncio.sleep(0.01)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        loop.run_until_complete(_run())
        assert bus.subscriber_count == 0
        loop.close()

    def test_publish_delivers_to_subscriber(self):
        """publish() should deliver event to a subscribed client."""
        bus = EventBus()
        loop = asyncio.new_event_loop()
        bus.set_loop(loop)
        received = []

        async def _run():
            async def _consume():
                async for event in bus.subscribe():
                    received.append(event)
                    break

            task = loop.create_task(_consume())
            await asyncio.sleep(0.01)
            bus.publish({"event": "dart_scored", "dart_number": 1})
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        loop.run_until_complete(_run())
        assert len(received) == 1
        assert received[0]["event"] == "dart_scored"
        loop.close()


# ---------------------------------------------------------------------------
# Server endpoint unit tests
# ---------------------------------------------------------------------------

class TestServerEndpoints:
    """Test FastAPI server endpoints."""

    def _make_state_machine(self):
        """Create a minimal mock state machine for testing."""
        class MockDartTracker:
            def clear_all(self):
                pass

        class MockStateMachine:
            def __init__(self):
                self.dart_tracker = MockDartTracker()
                self.current_state = State.WaitForThrow

        return MockStateMachine()

    def test_sse_endpoint_content_type(self):
        """GET /api/events should return text/event-stream."""
        from starlette.testclient import TestClient

        bus = EventBus()
        app = create_app(bus, None)

        with TestClient(app, raise_server_exceptions=False) as client:
            with client.stream("GET", "/api/events") as response:
                assert "text/event-stream" in response.headers["content-type"]

    def test_reset_returns_200_with_state_machine(self):
        """POST /api/reset should return 200 with correct JSON."""
        from starlette.testclient import TestClient

        bus = EventBus()
        sm = self._make_state_machine()
        app = create_app(bus, sm)

        with TestClient(app) as client:
            response = client.post("/api/reset")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["message"] == "System reset"

    def test_reset_returns_503_without_state_machine(self):
        """POST /api/reset should return 503 when state machine is None."""
        from starlette.testclient import TestClient

        bus = EventBus()
        app = create_app(bus, None)

        with TestClient(app) as client:
            response = client.post("/api/reset")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "error"

    def test_reset_clears_state_machine(self):
        """POST /api/reset should set state to WaitForThrow."""
        from starlette.testclient import TestClient

        bus = EventBus()
        sm = self._make_state_machine()
        sm.current_state = State.ThrowFinished
        app = create_app(bus, sm)

        with TestClient(app) as client:
            client.post("/api/reset")
            assert sm.current_state == State.WaitForThrow
