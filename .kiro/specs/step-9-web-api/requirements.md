# Step 9: Web API (FastAPI + WebSockets)

## Overview

Expose dart detection events and system metrics over a network API using FastAPI with REST endpoints and WebSocket support for real-time event streaming.

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

### US-9.3: WebSocket Event Streaming
**As a** client application  
**I want to** receive dart events in real-time via WebSocket  
**So that** I can update UI immediately when darts are thrown

**Acceptance Criteria:**
- AC-9.3.1: `GET /ws` establishes WebSocket connection
- AC-9.3.2: All dart events broadcast to connected clients
- AC-9.3.3: Events sent as JSON messages
- AC-9.3.4: Connection handles multiple concurrent clients
- AC-9.3.5: Graceful disconnect handling

### US-9.4: Event JSON Format
**As a** client developer  
**I want to** receive events in a well-defined JSON format  
**So that** I can parse and process them reliably

**Acceptance Criteria:**
- AC-9.4.1: DartHitEvent format includes all required fields
- AC-9.4.2: DartRemovedEvent format includes count information
- AC-9.4.3: All events include event_type field
- AC-9.4.4: Timestamps in ISO 8601 format
- AC-9.4.5: JSON schema documented

### US-9.5: Server Configuration
**As a** system operator  
**I want to** configure server settings via config file  
**So that** I can customize host, port, and endpoints

**Acceptance Criteria:**
- AC-9.5.1: Host configurable (default: 0.0.0.0)
- AC-9.5.2: Port configurable (default: 8000)
- AC-9.5.3: WebSocket path configurable (default: /ws)
- AC-9.5.4: CORS settings configurable
- AC-9.5.5: Debug mode toggle

## Technical Constraints

- FastAPI with uvicorn server
- WebSocket pub/sub for event broadcasting
- Thread-safe event queue
- Server runs in separate thread from main loop
- No blocking operations in API handlers

## Dependencies

- Step 8: State machine (event generation)
- FastAPI, uvicorn, websockets libraries
- Event model (JSON serialization)

## Success Metrics

- API response time <100ms
- WebSocket latency <50ms
- Supports 10+ concurrent WebSocket clients
- No event loss during transmission
