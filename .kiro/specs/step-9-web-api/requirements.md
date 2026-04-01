# Requirements Document

## Introduction

A minimal HTTP API layer for the ARU-DART backend that pushes dart scoring events to a Flutter dart training app running on a tablet on the same local network. The backend runs on a Raspberry Pi 4 with cameras; the app runs on a tablet — both on the same WLAN. The API bridges the existing `ThrowStateMachine` event stream to connected HTTP clients using Server-Sent Events (SSE), and exposes a reset endpoint for game management.

## Glossary

- **API_Server**: The FastAPI HTTP server running in a background thread within the ARU-DART process.
- **Event_Bus**: A thread-safe queue that bridges events from the main camera/detection loop thread to the API_Server thread.
- **SSE_Stream**: The Server-Sent Events endpoint at `GET /api/events` that pushes scoring events to connected clients.
- **SSE_Client**: A connected HTTP client (typically the Flutter app) consuming the SSE_Stream.
- **dart_scored**: An SSE event emitted immediately after a single dart is detected and scored.
- **round_complete**: An SSE event emitted when all 3 darts in a round have been scored (ThrowFinished state).
- **darts_removed**: An SSE event emitted when pull-out is complete and the system is ready for the next round.
- **Score_Label**: A short string representing a dart score in the format T20, D16, S5, SB, DB, or Miss.
- **ThrowStateMachine**: The existing state machine in `src/state_machine/throw_state_machine.py` that manages the dart throw lifecycle.
- **DartHitEvent**: The event emitted by the ThrowStateMachine when a dart is detected and scored.
- **DartRemovedEvent**: The event emitted by the ThrowStateMachine when darts are pulled out.

## Requirements

### Requirement 1: SSE Event Stream Endpoint

**User Story:** As a Flutter app, I want to connect to a persistent SSE stream, so that I can receive dart scoring events in real time without polling.

#### Acceptance Criteria

1. THE API_Server SHALL expose a `GET /api/events` endpoint that returns a `text/event-stream` response.
2. WHEN an SSE_Client connects to `GET /api/events`, THE API_Server SHALL keep the connection open and push events as they occur.
3. THE SSE_Stream SHALL support multiple simultaneous SSE_Clients receiving the same events.
4. WHEN an SSE_Client disconnects, THE API_Server SHALL release that client's resources without affecting other connected SSE_Clients.
5. WHILE no events are pending, THE API_Server SHALL send a keepalive comment (`: keepalive`) to each SSE_Client at an interval not exceeding 15 seconds to prevent connection timeouts.

### Requirement 2: dart_scored Event

**User Story:** As a Flutter app, I want to receive a `dart_scored` event immediately after each dart lands, so that I can display the score for each individual dart as it happens.

#### Acceptance Criteria

1. WHEN the ThrowStateMachine emits a `DartHitEvent`, THE Event_Bus SHALL publish a `dart_scored` SSE event to all connected SSE_Clients.
2. THE `dart_scored` event payload SHALL contain `dart_number` (1, 2, or 3), `label` (Score_Label string), and `points` (integer total score).
3. THE `dart_scored` event SHALL be emitted before the `round_complete` event for the same round.
4. THE Score_Label in the `dart_scored` payload SHALL use the format: `T{sector}` for triples, `D{sector}` for doubles, `S{sector}` for singles, `SB` for single bull, `DB` for double bull, and `Miss` for misses.
5. THE `dart_number` field SHALL reflect the sequential position of the dart within the current round (1, 2, or 3).

### Requirement 3: round_complete Event

**User Story:** As a Flutter app, I want to receive a `round_complete` event when all 3 darts are scored, so that I can submit the round total and update the game state.

#### Acceptance Criteria

1. WHEN the ThrowStateMachine transitions to the `ThrowFinished` state, THE Event_Bus SHALL publish a `round_complete` SSE event to all connected SSE_Clients.
2. THE `round_complete` event payload SHALL contain a `throws` array with one entry per dart, each containing `dart_number`, `label`, and `points`.
3. THE `round_complete` event payload SHALL contain a `total` field with the integer sum of all dart scores in the round.
4. THE `throws` array in the `round_complete` payload SHALL contain exactly the darts scored in the current round, in the order they were thrown.
5. IF fewer than 3 darts were scored due to bounce-outs or misses, THEN THE `round_complete` payload SHALL still reflect only the darts that registered scores.

### Requirement 4: darts_removed Event

**User Story:** As a Flutter app, I want to receive a `darts_removed` event when the darts are pulled out, so that I know the system is ready for the next round.

#### Acceptance Criteria

1. WHEN the ThrowStateMachine emits a `DartRemovedEvent` with `count_remaining` equal to 0, THE Event_Bus SHALL publish a `darts_removed` SSE event to all connected SSE_Clients.
2. THE `darts_removed` event payload SHALL contain a `message` field with the value `"Ready for next round"`.

### Requirement 5: Reset Endpoint

**User Story:** As a Flutter app operator, I want to call a reset endpoint, so that I can recover from errors or start a new game without restarting the backend process.

#### Acceptance Criteria

1. THE API_Server SHALL expose a `POST /api/reset` endpoint.
2. WHEN `POST /api/reset` is called, THE API_Server SHALL call `state_machine.dart_tracker.clear_all()` and transition the ThrowStateMachine back to the `WaitForThrow` state.
3. WHEN `POST /api/reset` completes successfully, THE API_Server SHALL return HTTP 200 with JSON body `{"status": "ok", "message": "System reset"}`.
4. IF the ThrowStateMachine is not available when `POST /api/reset` is called, THEN THE API_Server SHALL return HTTP 503 with a descriptive error message.

### Requirement 6: Thread-Safe Event Bus

**User Story:** As a developer, I want a thread-safe event bus, so that the main camera loop and the FastAPI server can exchange events without race conditions.

#### Acceptance Criteria

1. THE Event_Bus SHALL use a thread-safe queue to pass events from the main loop thread to the API_Server thread.
2. WHEN the main loop publishes an event to the Event_Bus, THE Event_Bus SHALL deliver that event to all currently connected SSE_Clients.
3. THE Event_Bus SHALL not block the main camera/detection loop when no SSE_Clients are connected.
4. WHEN a new SSE_Client connects, THE Event_Bus SHALL register that client to receive subsequent events only (no replay of past events).

### Requirement 7: FastAPI Server Lifecycle

**User Story:** As a developer, I want the FastAPI server to run alongside the existing main loop, so that the API does not require a separate process or disrupt camera operation.

#### Acceptance Criteria

1. THE API_Server SHALL run in a separate daemon thread within the same Python process as the camera/detection main loop.
2. WHEN the `--state-machine` CLI flag is active, THE API_Server SHALL start automatically on a configurable port (default: 8000).
3. WHEN the main process exits, THE API_Server thread SHALL terminate without requiring an explicit shutdown call.
4. THE API_Server SHALL not apply CORS restrictions, as all clients are on the same local network.
5. THE API_Server SHALL listen on `0.0.0.0` to accept connections from any device on the local network.
