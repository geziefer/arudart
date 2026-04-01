"""FastAPI server with SSE streaming and reset endpoints.

Runs in a daemon thread alongside the main camera/detection loop.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 5.1, 5.2, 5.3, 5.4, 7.1, 7.3, 7.4, 7.5
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse

from src.api.event_bus import EventBus
from src.state_machine.events import State

logger = logging.getLogger(__name__)


def create_app(event_bus: EventBus, state_machine=None) -> FastAPI:
    """Create a FastAPI app with SSE and reset endpoints.

    Args:
        event_bus: EventBus instance for pub/sub.
        state_machine: ThrowStateMachine instance (or None).

    Returns:
        Configured FastAPI application.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_event_loop()
        event_bus.set_loop(loop)
        logger.info("API server started, event loop set")
        yield

    app = FastAPI(title="ARU-DART API", lifespan=lifespan)

    @app.get("/api/events")
    async def sse_events() -> StreamingResponse:
        """SSE endpoint streaming dart scoring events."""
        return StreamingResponse(
            _event_generator(event_bus),
            media_type="text/event-stream",
        )

    @app.post("/api/reset")
    async def reset() -> JSONResponse:
        """Reset the state machine to WaitForThrow."""
        if state_machine is None:
            return JSONResponse(
                status_code=503,
                content={"status": "error", "message": "State machine not available"},
            )
        state_machine.dart_tracker.clear_all()
        state_machine.current_state = State.WaitForThrow
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "message": "System reset"},
        )

    return app


async def _event_generator(event_bus: EventBus):
    """Async generator yielding SSE frames from the event bus.

    Sends keepalive comments every 15 seconds when idle.
    """
    KEEPALIVE_TIMEOUT = 15.0

    async def _subscribe_and_yield():
        async for event in event_bus.subscribe():
            event_type = event.get("event", "message")
            # Build payload without the "event" key
            payload = {k: v for k, v in event.items() if k != "event"}
            yield f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

    gen = _subscribe_and_yield()
    try:
        while True:
            try:
                frame = await asyncio.wait_for(gen.__anext__(), timeout=KEEPALIVE_TIMEOUT)
                yield frame
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
            except StopAsyncIteration:
                break
    except asyncio.CancelledError:
        logger.info("SSE client disconnected")
    finally:
        await gen.aclose()


def start_server(app: FastAPI, host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start uvicorn in a daemon thread.

    Args:
        app: FastAPI application instance.
        host: Host to bind (default 0.0.0.0).
        port: Port to listen on (default 8000).
    """
    import uvicorn

    def _run():
        uvicorn.run(app, host=host, port=port, log_level="warning")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info(f"API server started on {host}:{port}")
