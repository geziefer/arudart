# Step 9: Web API (FastAPI + WebSockets)

## Overview

Expose dart detection events and system metrics over a network API using FastAPI with REST endpoints and WebSocket support. The API serves two types of consumers: real-time event consumers (every event) and round-based consumers (aggregated 3-dart rounds).

## Consumer Types

### Real-Time Consumer
Receives every individual event as it happens (dart hits, removals, bounce-outs, misses, state changes). Use case: live scoreboards, real-time UI updates, spectator displays, sound/visual effects.

### Round-Based Consumer
Receives aggregated round data after 3 darts are thrown. Use case: game logic, score tracking, statistics, tournament systems that only care about complete rounds.

## User Stories

### US-9.1: REST Health Endpoint
**As a** system administrator  
**I want to** check system health and status via REST API  
**So that** I can monitor the system remotely

**Acceptance Criteria:**
- AC-9.1.1: `GET /health` returns service status (running/stopped)
- AC-9.1.2: Response includes per-camera FPS
- AC-9.1.3: Response includes uptime
- AC-9.1.4: Response includes last detection timestamp
- AC-9.1.5: Response time <100ms

### US-9.2: REST Metrics Endpoint
**As a** developer  
**I want to** retrieve system metrics via REST API  
**So that** I can analyze performance and debug issues

**Acceptance Criteria:**
- AC-9.2.1: `GET /metrics` returns detection counts
- AC-9.2.2: Response includes average detection latency
- AC-9.2.3: Response includes per-camera detection rates
- AC-9.2.4: Response includes error counts
- AC-9.2.5: Metrics reset on server restart

### US-9.3: WebSocket Real-Time Event Streaming
**As a** real-time consumer  
**I want to** receive all dart events in real-time via WebSocket  
**So that** I can update UI immediately when any event occurs

**Acceptance Criteria:**
- AC-9.3.1: `GET /ws/events` establishes WebSocket connection for all events
- AC-9.3.2: All events broadcast to connected clients (DartHitEvent, DartRemovedEvent, DartBounceOutEvent, ThrowMissEvent, StateChangeEvent)
- AC-9.3.3: Events sent as JSON messages with event_type field
- AC-9.3.4: Connection handles multiple concurrent clients (10+)
- AC-9.3.5: Graceful disconnect handling
- AC-9.3.6: No event filtering (consumers receive all events)

### US-9.4: WebSocket Round Completion Streaming
**As a** round-based consumer  
**I want to** receive round completion notifications via WebSocket  
**So that** I can process complete 3-dart rounds without tracking individual events

**Acceptance Criteria:**
- AC-9.4.1: `GET /ws/rounds` establishes WebSocket connection for round events
- AC-9.4.2: RoundCompleteEvent sent when round finishes (3 darts thrown or pull-out)
- AC-9.4.3: Event includes all dart scores, total score, and round metadata
- AC-9.4.4: Event includes bounce-outs and misses count
- AC-9.4.5: Connection handles multiple concurrent clients

### US-9.5: REST Current Round Endpoint
**As a** round-based consumer  
**I want to** query the current round state via REST API  
**So that** I can poll for round progress without WebSocket

**Acceptance Criteria:**
- AC-9.5.1: `GET /rounds/current` returns current round in progress
- AC-9.5.2: Response includes darts thrown so far (0-3)
- AC-9.5.3: Response includes current total score
- AC-9.5.4: Response includes round state (in_progress/completed)
- AC-9.5.5: Returns empty/null if no round in progress

### US-9.6: REST Latest Round Endpoint
**As a** round-based consumer  
**I want to** retrieve the most recently completed round via REST API  
**So that** I can get final round results

**Acceptance Criteria:**
- AC-9.6.1: `GET /rounds/latest` returns most recently completed round
- AC-9.6.2: Response includes all 3 dart scores (or fewer if bounce-outs/misses)
- AC-9.6.3: Response includes total score for the round
- AC-9.6.4: Response includes round duration and timestamp
- AC-9.6.5: Returns null if no completed round exists yet

### US-9.7: Round State Tracking
**As a** system  
**I want to** track current and last completed round  
**So that** I can serve round data to consumers

**Acceptance Criteria:**
- AC-9.7.1: System maintains current round object (0-3 darts)
- AC-9.7.2: System maintains last completed round object
- AC-9.7.3: Round resets when all darts removed (transition to WaitForThrow)
- AC-9.7.4: Round marked complete when 3 darts thrown (transition to ThrowFinished)
- AC-9.7.5: No historical round storage (only current + last)

### US-9.8: Event JSON Format
**As a** client developer  
**I want to** receive events in a well-defined JSON format  
**So that** I can parse and process them reliably

**Acceptance Criteria:**
- AC-9.8.1: All events include event_type field
- AC-9.8.2: Timestamps in ISO 8601 format
- AC-9.8.3: DartHitEvent includes score, position, confidence
- AC-9.8.4: RoundCompleteEvent includes all darts, total score, metadata
- AC-9.8.5: JSON schema documented for all event types

### US-9.9: Server Configuration
**As a** system operator  
**I want to** configure server settings via config file  
**So that** I can customize host, port, and endpoints

**Acceptance Criteria:**
- AC-9.9.1: Host configurable (default: 0.0.0.0)
- AC-9.9.2: Port configurable (default: 8000)
- AC-9.9.3: WebSocket paths configurable (default: /ws/events, /ws/rounds)
- AC-9.9.4: CORS settings configurable
- AC-9.9.5: Debug mode toggle

## Technical Constraints

- FastAPI with uvicorn server
- WebSocket pub/sub for event broadcasting
- Thread-safe event queue for both event types
- Server runs in separate thread from main loop
- No blocking operations in API handlers
- Round state tracking (current + last completed only)
- No historical round storage beyond last completed

## API Endpoints Summary

**WebSocket Endpoints:**
- `/ws/events` - All events (real-time consumer)
- `/ws/rounds` - Round completion only (round-based consumer)

**REST Endpoints:**
- `GET /health` - System health and status
- `GET /metrics` - Performance metrics
- `GET /rounds/current` - Current round in progress
- `GET /rounds/latest` - Most recently completed round

## Event Types

**Real-Time Events** (sent to `/ws/events`):
- DartHitEvent - Individual dart scored
- DartRemovedEvent - Darts pulled out
- DartBounceOutEvent - Dart fell off board
- ThrowMissEvent - Throw missed
- StateChangeEvent - State machine transitions

**Round Events** (sent to `/ws/rounds`):
- RoundCompleteEvent - Round finished (3 darts or pull-out)

## Dependencies

- Step 8: State machine (event generation)
- FastAPI, uvicorn, websockets libraries
- Event model (JSON serialization)
- Round aggregation logic

## Success Metrics

- API response time <100ms
- WebSocket latency <50ms for event delivery
- Supports 10+ concurrent WebSocket clients per endpoint
- No event loss during transmission
- Round state always consistent with state machine
