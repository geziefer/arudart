# Implementation Plan: Step 9 — Web API (SSE)

## Overview

Add a minimal HTTP API layer to the ARU-DART backend using FastAPI and Server-Sent Events (SSE). Three new modules bridge the existing `ThrowStateMachine` event stream to connected clients: `EventBus` (thread-safe pub/sub), `RoundTracker` (accumulates dart hits, emits round_complete), and `Server` (FastAPI app with SSE + reset endpoints). The server runs in a daemon thread alongside the main camera/detection loop.

## Tasks

- [ ] 1. Add dependencies and create module skeleton
  - Add `fastapi>=0.110.0`, `uvicorn>=0.29.0`, and `httpx>=0.27.0` to `requirements.txt`
  - Create `src/api/__init__.py` (empty)
  - _Requirements: 7.1, 7.2_

- [ ] 2. Implement EventBus (`src/api/event_bus.py`)
  - [ ] 2.1 Create `EventBus` class with `publish()`, `subscribe()`, and `subscriber_count`
    - `publish(event: dict) -> None` — called from main loop thread; uses `loop.call_soon_threadsafe` to put event into each subscriber's `asyncio.Queue`; silently drops if no loop or no subscribers
    - `subscribe() -> AsyncGenerator[dict, None]` — creates a per-client `asyncio.Queue(maxsize=100)` on entry, removes it on exit; drops oldest event and logs warning when queue is full
    - `set_loop(loop: asyncio.AbstractEventLoop) -> None` — called once when FastAPI server starts
    - Use `threading.Lock` to protect `_subscribers` list mutations
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 2.2 Write property test for EventBus fan-out (Property 1)
    - **Property 1: Fan-out delivery** — for any event published with N subscribers, every subscriber receives exactly that event
    - **Validates: Requirements 1.3, 6.2**
    - Use `asyncio.run()` to exercise publish/subscribe cycle with random event counts and subscriber counts (1–5)
    - _File: `tests/test_api_properties.py`_

  - [ ]* 2.3 Write property test for subscriber disconnect isolation (Property 2)
    - **Property 2: Subscriber disconnect isolation** — when one subscriber is removed, remaining subscribers still receive subsequent events without loss
    - **Validates: Requirements 1.4**
    - _File: `tests/test_api_properties.py`_

  - [ ]* 2.4 Write property test for no replay of past events (Property 9)
    - **Property 9: No replay of past events** — events published before a subscriber connects must not be delivered to that subscriber
    - **Validates: Requirements 6.4**
    - _File: `tests/test_api_properties.py`_

  - [ ]* 2.5 Write unit tests for EventBus
    - Test `publish()` with no subscribers is a no-op (non-blocking)
    - Test `publish()` before `set_loop()` is called drops event silently
    - Test `subscriber_count` increments on subscribe and decrements on exit
    - _File: `tests/test_api.py`_

- [ ] 3. Implement RoundTracker (`src/api/round_tracker.py`)
  - [ ] 3.1 Create `RoundTracker` class with `process_hit()`, `reset()`, and `dart_count`
    - `process_hit(dart_hit: DartHitEvent) -> list[dict]` — increments internal counter (1→2→3); always returns `[dart_scored_dict]`; appends `round_complete_dict` when counter reaches 3
    - `reset() -> None` — clears accumulated throws and resets counter to 0
    - `dart_count -> int` — current number of darts in this round (0–3)
    - Score label conversion: `T{sector}`, `D{sector}`, `S{sector}`, `SB`, `DB`, `Miss` (reuse pattern from `score_to_display_string` in `src/feedback/feedback_collector.py` but without the points suffix)
    - `dart_scored` payload: `{"dart_number": int, "label": str, "points": int}`
    - `round_complete` payload: `{"throws": [...], "total": int}`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 3.2 Write property test for dart_scored payload correctness (Property 3)
    - **Property 3: dart_scored payload correctness** — for any valid `DartHitEvent`, `process_hit()` returns a `dart_scored` dict with `dart_number` (int 1–3), `label` (matching `T{sector}|D{sector}|S{sector}|SB|DB|Miss`), and `points` equal to `score.total`
    - **Validates: Requirements 2.1, 2.2, 2.4**
    - Generate random `DartHitEvent` objects with all ring types, sectors 1–20, bulls, misses
    - _File: `tests/test_api_properties.py`_

  - [ ]* 3.3 Write property test for sequential dart numbering (Property 4)
    - **Property 4: Sequential dart numbering** — for any sequence of `DartHitEvent` objects processed by a fresh `RoundTracker`, `dart_number` in successive `dart_scored` outputs is 1, 2, 3 in order; resets to 1 after `reset()`
    - **Validates: Requirements 2.5**
    - _File: `tests/test_api_properties.py`_

  - [ ]* 3.4 Write property test for round completion ordering (Property 5)
    - **Property 5: Round completion ordering and emission** — for exactly 3 `DartHitEvent` objects, the 3rd call returns `[dart_scored, round_complete]` in that order; first two calls return only `[dart_scored]`
    - **Validates: Requirements 2.3, 3.1**
    - _File: `tests/test_api_properties.py`_

  - [ ]* 3.5 Write property test for round_complete payload correctness (Property 6)
    - **Property 6: round_complete payload correctness** — for any 3 `DartHitEvent` objects, `round_complete` contains `throws` array with exactly 3 entries in input order and `total` equal to sum of the 3 `points` values
    - **Validates: Requirements 3.2, 3.3, 3.4**
    - _File: `tests/test_api_properties.py`_

  - [ ]* 3.6 Write unit tests for RoundTracker
    - Test `reset()` clears state after a partial round (1 or 2 darts)
    - Test all 6 ring types produce correct score labels (T20, D16, S5, SB, DB, Miss)
    - Test `dart_count` property reflects current state
    - _File: `tests/test_api.py`_

- [ ] 4. Checkpoint — ensure EventBus and RoundTracker tests pass
  - Run `pytest tests/test_api.py tests/test_api_properties.py -v`
  - Ask the user if questions arise.

- [ ] 5. Implement FastAPI server (`src/api/server.py`)
  - [ ] 5.1 Create `create_app(event_bus, state_machine) -> FastAPI` factory
    - No CORS restrictions (all clients on same LAN) — _Requirements: 7.4_
    - On startup: call `event_bus.set_loop(asyncio.get_event_loop())`
    - _Requirements: 7.1, 7.4_

  - [ ] 5.2 Implement `GET /api/events` SSE endpoint
    - Returns `StreamingResponse` with `media_type="text/event-stream"`
    - Async generator subscribes to `event_bus.subscribe()`; yields each event as `"event: {event_type}\ndata: {json_payload}\n\n"`
    - Sends keepalive comment `": keepalive\n\n"` every 15s when idle (use `asyncio.wait_for` with timeout)
    - Catches `asyncio.CancelledError` on client disconnect; logs disconnect
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ] 5.3 Implement `POST /api/reset` endpoint
    - Calls `state_machine.dart_tracker.clear_all()` and sets `state_machine.current_state = State.WaitForThrow`
    - Returns HTTP 200 `{"status": "ok", "message": "System reset"}` on success
    - Returns HTTP 503 `{"status": "error", "message": "State machine not available"}` when `state_machine is None`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ] 5.4 Implement `start_server(app, host, port) -> None`
    - Runs `uvicorn.run(app, host=host, port=port)` in a `daemon=True` thread
    - _Requirements: 7.1, 7.3, 7.5_

  - [ ]* 5.5 Write property test for darts_removed event generation (Property 7)
    - **Property 7: darts_removed event generation** — for any `DartRemovedEvent` with `count_remaining == 0`, the conversion produces `{"event": "darts_removed", "message": "Ready for next round"}`; for `count_remaining > 0`, no event is produced
    - **Validates: Requirements 4.1, 4.2**
    - Test the helper function that converts `DartRemovedEvent` to SSE dict (extract as a pure function in `server.py` or `round_tracker.py`)
    - _File: `tests/test_api_properties.py`_

  - [ ]* 5.6 Write property test for reset restoring initial state (Property 8)
    - **Property 8: Reset restores initial state** — for any `ThrowStateMachine` in any state with any number of tracked darts, calling the reset logic results in `current_state == State.WaitForThrow` and `dart_tracker.get_total_dart_count() == 0`
    - **Validates: Requirements 5.2**
    - _File: `tests/test_api_properties.py`_

  - [ ]* 5.7 Write unit tests for server endpoints
    - Test `GET /api/events` returns `text/event-stream` content type — _Requirements: 1.1_
    - Test `POST /api/reset` returns HTTP 200 with `{"status": "ok", "message": "System reset"}` — _Requirements: 5.3_
    - Test `POST /api/reset` returns HTTP 503 when state machine is `None` — _Requirements: 5.4_
    - Test keepalive is sent within 15s of no events — _Requirements: 1.5_
    - Use `httpx.AsyncClient` with FastAPI's `TestClient`
    - _File: `tests/test_api.py`_

- [ ] 6. Integrate with `main.py`
  - [ ] 6.1 Add `--api-port` CLI flag (default: 8000) to `main()` argument parser
    - _Requirements: 7.2_

  - [ ] 6.2 Wire EventBus and RoundTracker into `run_state_machine_mode()`
    - Accept optional `event_bus: EventBus | None` and `round_tracker: RoundTracker | None` parameters
    - In the event handling loop: on `DartHitEvent`, call `round_tracker.process_hit(event)` and publish each returned dict to `event_bus`
    - On `DartRemovedEvent` with `count_remaining == 0`: publish `{"event": "darts_removed", "message": "Ready for next round"}` to `event_bus` and call `round_tracker.reset()`
    - _Requirements: 2.1, 4.1, 4.2_

  - [ ] 6.3 Start API server when `--state-machine` flag is active
    - In `main()`, after initializing `state_machine`, create `EventBus`, `RoundTracker`, and call `start_server(create_app(event_bus, state_machine), host="0.0.0.0", port=args.api_port)`
    - Pass `event_bus` and `round_tracker` into `run_state_machine_mode()`
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

- [ ] 7. Final checkpoint — ensure all tests pass
  - Run `pytest tests/test_api.py tests/test_api_properties.py -v`
  - Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Property tests use `@settings(max_examples=100)` and are tagged with `# Feature: step-9-web-api, Property N: ...`
- The `EventBus` bridges sync (main loop) and async (FastAPI) worlds via `loop.call_soon_threadsafe`
- `RoundTracker` is pure Python with no async dependencies — easy to unit test
- The `darts_removed` SSE event is only emitted when `count_remaining == 0` (all darts pulled out)
