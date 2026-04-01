"""Thread-safe event bus bridging sync main loop and async FastAPI handlers.

Provides publish() for the sync main loop thread and subscribe() as an
async generator for SSE handlers. Each subscriber gets its own asyncio.Queue.

Requirements: 6.1, 6.2, 6.3, 6.4
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


class EventBus:
    """Thread-safe pub/sub bridge between sync and async worlds."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict]] = []
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the asyncio event loop (called once when FastAPI starts)."""
        self._loop = loop

    def publish(self, event: dict) -> None:
        """Publish an event to all subscribers. Non-blocking, thread-safe.

        Silently drops if no loop is set or no subscribers exist.
        """
        loop = self._loop
        if loop is None:
            return

        with self._lock:
            subscribers = list(self._subscribers)

        if not subscribers:
            return

        for queue in subscribers:
            try:
                loop.call_soon_threadsafe(self._enqueue, queue, event)
            except RuntimeError:
                # Loop is closed or shutting down
                pass

    @staticmethod
    def _enqueue(queue: asyncio.Queue[dict], event: dict) -> None:
        """Put event into a subscriber queue, dropping oldest if full."""
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
            logger.warning("Subscriber queue full, dropped oldest event")

    async def subscribe(self) -> AsyncGenerator[dict, None]:
        """Async generator yielding events for a single SSE client.

        Creates a per-client Queue on entry, removes it on exit.
        """
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        with self._lock:
            self._subscribers.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        except asyncio.CancelledError:
            logger.info("SSE subscriber disconnected")
        finally:
            with self._lock:
                try:
                    self._subscribers.remove(queue)
                except ValueError:
                    pass

    @property
    def subscriber_count(self) -> int:
        """Number of currently connected subscribers."""
        with self._lock:
            return len(self._subscribers)
