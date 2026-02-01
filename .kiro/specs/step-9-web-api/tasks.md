# Implementation Plan: Step 9 - Web API (FastAPI + WebSockets)

## Overview

This implementation plan breaks down the Web API feature into discrete coding tasks. The API provides REST endpoints for health/metrics/rounds and WebSocket endpoints for real-time event streaming and round completion notifications. The server runs in a separate thread with thread-safe event queues for communication with the main detection loop.

## Tasks

- [ ] 1. Set up FastAPI project structure and dependencies
  - Create `src/api/` directory structure
  - Add FastAPI, uvicorn, websockets, pydantic to requirements.txt
  - Create `__init__.py` files for all modules
  - _Requirements: AC-9.9.1, AC-9.9.2, AC-9.9.3, AC-9.9.4, AC-9.9.5_

- [ ] 2. Implement event queue for thread-safe communication
  - [ ] 2.1 Create EventQueue class with thread-safe operations
    - Implement put(), get(), size(), clear() methods
    - Use queue.Queue for thread safety
    - Add configurable max queue size
    - _Requirements: AC-9.7.1_
  
  - [ ] 2.2 Write unit tests for EventQueue
    - Test concurrent put/get operations
    - Test queue full behavior
    - Test timeout handling
    - _Requirements: AC-9.7.1_

- [ ] 3. Implement data models for API responses
  - [ ] 3.1 Create Pydantic models for all data structures
    - DartInfo model (score, position, timestamp, confidence)
    - CurrentRound model (round_id, darts, bounce_outs, misses)
    - CompletedRound model (extends CurrentRound with duration, total_score)
    - RoundCompleteEvent model (event_type, timestamp, round)
    - _Requirements: AC-9.8.1, AC-9.8.2, AC-9.8.3, AC-9.8.4_
  
  - [ ] 3.2 Write unit tests for data model serialization
    - Test to_dict() methods for all models
    - Test JSON serialization round trip
    - Test timestamp format (ISO 8601)
    - _Requirements: AC-9.8.5_

- [ ] 4. Implement WebSocketManager for connection handling
  - [ ] 4.1 Create WebSocketManager class
    - Implement connect(), disconnect(), broadcast() methods
    - Use threading.Lock for active_connections list
    - Handle connection errors gracefully
    - Track connection count
    - _Requirements: AC-9.3.1, AC-9.3.4, AC-9.3.5, AC-9.4.1, AC-9.4.5_
  
  - [ ] 4.2 Write unit tests for WebSocketManager
    - Test multiple concurrent connections
    - Test broadcast to all clients
    - Test graceful disconnect handling
    - Test error handling (send failures)
    - _Requirements: AC-9.3.4, AC-9.3.5_

- [ ] 5. Implement RoundAggregator for round state tracking
  - [ ] 5.1 Create RoundAggregator class
    - Implement process_event() method for all event types
    - Track current_round (0-3 darts)
    - Track last_completed_round
    - Use threading.Lock for state protection
    - Implement finalize_round() for completion
    - _Requirements: AC-9.7.1, AC-9.7.2, AC-9.7.3, AC-9.7.4, AC-9.7.5_
  
  - [ ] 5.2 Write unit tests for RoundAggregator
    - Test 3-dart round completion
    - Test early pull-out (< 3 darts)
    - Test bounce-out counting
    - Test miss counting
    - Test round reset on dart removal
    - _Requirements: AC-9.4.2, AC-9.4.3, AC-9.4.4_

- [ ] 6. Implement REST endpoint handlers
  - [ ] 6.1 Create REST handler functions
    - Implement GET /health endpoint
    - Implement GET /metrics endpoint
    - Implement GET /rounds/current endpoint
    - Implement GET /rounds/latest endpoint
    - _Requirements: AC-9.1.1, AC-9.1.2, AC-9.1.3, AC-9.1.4, AC-9.2.1, AC-9.2.2, AC-9.2.3, AC-9.5.1, AC-9.5.2, AC-9.5.3, AC-9.6.1, AC-9.6.2, AC-9.6.3_
  
  - [ ] 6.2 Write unit tests for REST endpoints
    - Test /health response format and status codes
    - Test /metrics response format
    - Test /rounds/current with and without active round
    - Test /rounds/latest with and without completed round
    - Test response time < 100ms
    - _Requirements: AC-9.1.5, AC-9.2.4, AC-9.5.4, AC-9.5.5, AC-9.6.4, AC-9.6.5_

- [ ] 7. Implement MetricsTracker for system metrics
  - [ ] 7.1 Create MetricsTracker class
    - Track detection counts by event type
    - Track detection latencies
    - Track per-camera detection rates
    - Track error counts
    - Use threading.Lock for metrics protection
    - _Requirements: AC-9.2.1, AC-9.2.2, AC-9.2.3, AC-9.2.4_
  
  - [ ] 7.2 Write unit tests for MetricsTracker
    - Test metric recording (events, latencies, errors)
    - Test thread-safe metric updates
    - Test metric reset
    - _Requirements: AC-9.2.5_

- [ ] 8. Implement FastAPI application and server thread
  - [ ] 8.1 Create APIServer class with FastAPI app
    - Initialize FastAPI app with CORS settings
    - Create WebSocketManager instances for both endpoints
    - Create RoundAggregator instance
    - Create MetricsTracker instance
    - Implement start() and stop() methods
    - Implement event processing loop
    - _Requirements: AC-9.9.1, AC-9.9.2, AC-9.9.3, AC-9.9.4_
  
  - [ ] 8.2 Implement WebSocket endpoints
    - Add /ws/events endpoint for real-time events
    - Add /ws/rounds endpoint for round completion
    - Send welcome message on connection
    - Handle connection lifecycle
    - _Requirements: AC-9.3.1, AC-9.3.2, AC-9.3.3, AC-9.4.1, AC-9.4.2_
  
  - [ ] 8.3 Wire REST endpoints to FastAPI app
    - Register all REST endpoint handlers
    - Add error handling middleware
    - Configure CORS
    - _Requirements: AC-9.1.1, AC-9.2.1, AC-9.5.1, AC-9.6.1_

- [ ] 9. Implement event processing and broadcasting
  - [ ] 9.1 Create event processing loop in API thread
    - Pull events from event_queue
    - Broadcast to /ws/events clients
    - Process events in RoundAggregator
    - Broadcast round completion to /ws/rounds clients
    - Update metrics
    - _Requirements: AC-9.3.2, AC-9.3.6, AC-9.4.2_
  
  - [ ] 9.2 Write unit tests for event processing
    - Test event broadcast to real-time clients
    - Test round aggregation and broadcast
    - Test metrics updates
    - Test error handling (queue empty, broadcast failures)
    - _Requirements: AC-9.3.3, AC-9.3.6_

- [ ] 10. Add configuration support
  - [ ] 10.1 Add API configuration to config.toml
    - Add [api] section with host, port, paths
    - Add CORS settings
    - Add debug mode toggle
    - Add event queue size
    - _Requirements: AC-9.9.1, AC-9.9.2, AC-9.9.3, AC-9.9.4, AC-9.9.5_
  
  - [ ] 10.2 Load configuration in APIServer
    - Read config from config.toml
    - Apply settings to FastAPI app
    - Validate configuration values
    - _Requirements: AC-9.9.1, AC-9.9.2, AC-9.9.3_

- [ ] 11. Integrate API server with main detection loop
  - [ ] 11.1 Initialize APIServer in main.py
    - Create APIServer instance with config
    - Start server thread before main loop
    - Stop server thread on shutdown
    - _Requirements: AC-9.7.1_
  
  - [ ] 11.2 Push state machine events to API
    - Call api_server.push_event() for each event
    - Handle event queue full errors
    - _Requirements: AC-9.3.2, AC-9.4.2_

- [ ] 12. Checkpoint - Ensure all tests pass
  - Run all unit tests
  - Verify API server starts without errors
  - Test WebSocket connections manually
  - Test REST endpoints manually
  - Ask the user if questions arise

- [ ] 13. Write integration tests for end-to-end API flow
  - [ ] 13.1 Test complete dart throw flow
    - Push DartHitEvent to queue
    - Verify broadcast to /ws/events clients
    - Verify round aggregation
    - Push 2 more DartHitEvents
    - Verify RoundCompleteEvent broadcast to /ws/rounds clients
    - _Requirements: AC-9.3.2, AC-9.4.2, AC-9.4.3_
  
  - [ ] 13.2 Test REST + WebSocket interaction
    - Connect WebSocket clients
    - Push events via queue
    - Query /rounds/current during round
    - Query /rounds/latest after completion
    - Verify consistency between WebSocket and REST data
    - _Requirements: AC-9.5.1, AC-9.5.2, AC-9.6.1, AC-9.6.2_
  
  - [ ] 13.3 Test multiple concurrent WebSocket clients
    - Connect 10+ clients to each endpoint
    - Push events via queue
    - Verify all clients receive messages
    - Test client disconnect during broadcast
    - _Requirements: AC-9.3.4, AC-9.4.5_

- [ ] 14. Final checkpoint - Ensure all tests pass
  - Run all unit and integration tests
  - Verify no memory leaks (long-running test)
  - Verify WebSocket latency < 50ms
  - Verify REST response time < 100ms
  - Ask the user if questions arise

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Unit tests validate specific functionality
- Integration tests validate end-to-end flows
- API server runs in separate thread to avoid blocking detection loop
- Thread-safe event queue ensures data consistency
- Two WebSocket endpoints serve different consumer types
- All tests are required for comprehensive validation
