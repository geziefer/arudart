# Step 9: Web API (FastAPI + WebSockets) - Design Document

## Overview

This design document specifies the architecture for a FastAPI-based web API that exposes dart detection events and system metrics over HTTP and WebSocket protocols. The API serves two distinct consumer types: real-time consumers (receiving every event) and round-based consumers (receiving aggregated 3-dart rounds).

The API runs in a separate thread from the main detection loop, using thread-safe event queues for communication. It provides REST endpoints for health checks, metrics, and round queries, plus WebSocket endpoints for real-time event streaming and round completion notifications.

**Key Design Principles**:
- Non-blocking API server (separate thread)
- Thread-safe event broadcasting to multiple clients
- Two WebSocket endpoints for different consumer needs
- Minimal state tracking (current round + last completed only)
- No historical storage or database
- JSON serialization for all events
- Graceful connection handling and error recovery

## Architecture

### High-Level Architecture

```
Main Detection Loop (Thread 1)
    ↓
State Machine Events
    ↓
Event Queue (thread-safe)
    ↓
API Server (Thread 2)
    ├─→ WebSocket Manager (/ws/events)
    │   └─→ Broadcast to all real-time clients
    │
    ├─→ Round Aggregator
    │   ├─→ Track current round (0-3 darts)
    │   └─→ Store last completed round
    │
    ├─→ WebSocket Manager (/ws/rounds)
    │   └─→ Broadcast round completion to round-based clients
    │
    └─→ REST Handlers
        ├─→ GET /health
        ├─→ GET /metrics
        ├─→ GET /rounds/current
        └─→ GET /rounds/latest
```

### Module Structure

```
src/api/
├── __init__.py
├── server.py                    # FastAPI app and server thread
├── websocket_manager.py         # WebSocket connection management
├── round_aggregator.py          # Round state tracking and aggregation
├── event_queue.py               # Thread-safe event queue
├── rest_handlers.py             # REST endpoint handlers
└── models.py                    # Pydantic models for API responses

config.toml additions:
[api]
host = "0.0.0.0"
port = 8000
ws_events_path = "/ws/events"
ws_rounds_path = "/ws/rounds"
enable_cors = true
cors_origins = ["*"]
debug = false
```

### Thread Architecture

```
Main Thread:
    - Run detection loop
    - Process state machine
    - Emit events
    - Push events to event_queue
    
API Thread:
    - Run FastAPI server (uvicorn)
    - Process event_queue
    - Broadcast to WebSocket clients
    - Handle REST requests
    - Update round state
    
Communication:
    - event_queue: thread-safe queue (queue.Queue)
    - round_state: protected by threading.Lock
    - metrics: protected by threading.Lock
```

### Data Flow

```
State Machine Event
    ↓
event_queue.put(event)
    ↓
API Thread: event_queue.get()
    ↓
┌─────────────────────────────────────┐
│ Event Processing                    │
│                                     │
│ 1. Broadcast to /ws/events clients  │
│    (all events)                     │
│                                     │
│ 2. Update round aggregator          │
│    (DartHitEvent, DartRemovedEvent) │
│                                     │
│ 3. If round complete:               │
│    - Create RoundCompleteEvent      │
│    - Broadcast to /ws/rounds clients│
│    - Store as last_completed_round  │
│                                     │
│ 4. Update metrics                   │
│    (detection counts, latency)      │
└─────────────────────────────────────┘
```

## Components and Interfaces

### 1. APIServer Class

**Purpose**: Main FastAPI application and server thread management.

**Interface**:
```
APIServer:
    State:
        app: FastAPI instance
        event_queue: thread-safe queue
        ws_manager_events: WebSocketManager for /ws/events
        ws_manager_rounds: WebSocketManager for /ws/rounds
        round_aggregator: RoundAggregator instance
        metrics: MetricsTracker instance
        server_thread: threading.Thread
        running: boolean flag
    
    Methods:
        start():
            Create server thread
            Start uvicorn server in thread
            Start event processing loop
        
        stop():
            Set running = false
            Wait for thread to finish
            Close all WebSocket connections
        
        push_event(event):
            Add event to event_queue (thread-safe)
        
        process_events():
            Loop while running:
                event = event_queue.get(timeout=0.1)
                
                # Broadcast to real-time consumers
                ws_manager_events.broadcast(event)
                
                # Update round aggregator
                round_event = round_aggregator.process_event(event)
                
                # If round complete, broadcast to round consumers
                if round_event is not None:
                    ws_manager_rounds.broadcast(round_event)
                
                # Update metrics
                metrics.record_event(event)
```

### 2. WebSocketManager Class

**Purpose**: Manage WebSocket connections and broadcast events to multiple clients.

**Interface**:
```
WebSocketManager:
    State:
        active_connections: list of WebSocket connections
        connection_lock: threading.Lock
    
    Methods:
        connect(websocket):
            Accept WebSocket connection
            Add to active_connections (thread-safe)
            Send welcome message
        
        disconnect(websocket):
            Remove from active_connections (thread-safe)
            Close connection gracefully
        
        broadcast(event):
            Serialize event to JSON
            
            For each connection in active_connections:
                Try:
                    Send JSON message
                Except:
                    Log error
                    Remove connection from list
        
        get_connection_count() → integer:
            Return length of active_connections (thread-safe)
```

### 3. RoundAggregator Class

**Purpose**: Track current round state (0-3 darts) and aggregate into round completion events.

**Interface**:
```
RoundAggregator:
    State:
        current_round: CurrentRound object or None
        last_completed_round: CompletedRound object or None
        state_lock: threading.Lock
    
    Methods:
        process_event(event) → RoundCompleteEvent or None:
            Input: Any state machine event
            Output: RoundCompleteEvent if round completed, else None
            
            Algorithm:
                If event is DartHitEvent:
                    If current_round is None:
                        Create new CurrentRound
                    
                    Add dart to current_round
                    
                    If current_round.dart_count >= 3:
                        complete_round = finalize_round()
                        last_completed_round = complete_round
                        current_round = None
                        return RoundCompleteEvent(complete_round)
                
                If event is DartRemovedEvent:
                    If current_round is not None:
                        # Round interrupted by pull-out
                        complete_round = finalize_round()
                        last_completed_round = complete_round
                        current_round = None
                        return RoundCompleteEvent(complete_round)
                
                If event is DartBounceOutEvent:
                    If current_round is not None:
                        Add bounce-out to current_round
                        
                        If current_round.total_count >= 3:
                            complete_round = finalize_round()
                            last_completed_round = complete_round
                            current_round = None
                            return RoundCompleteEvent(complete_round)
                
                If event is ThrowMissEvent:
                    If current_round is not None:
                        Add miss to current_round
                        
                        If current_round.total_count >= 3:
                            complete_round = finalize_round()
                            last_completed_round = complete_round
                            current_round = None
                            return RoundCompleteEvent(complete_round)
                
                Return None
        
        finalize_round() → CompletedRound:
            Compute total score
            Compute round duration
            Create CompletedRound object
            Return completed round
        
        get_current_round() → CurrentRound or None:
            Return current_round (thread-safe)
        
        get_last_completed_round() → CompletedRound or None:
            Return last_completed_round (thread-safe)
        
        reset():
            Clear current_round
            Clear last_completed_round
```

### 4. EventQueue Class

**Purpose**: Thread-safe queue for passing events from main thread to API thread.

**Interface**:
```
EventQueue:
    State:
        queue: queue.Queue instance
    
    Methods:
        put(event):
            Add event to queue (blocking if full)
        
        get(timeout=None) → event or None:
            Remove and return event from queue
            If timeout specified, return None if empty
        
        size() → integer:
            Return number of events in queue
        
        clear():
            Remove all events from queue
```

### 5. REST Handlers

**Purpose**: Handle REST endpoint requests for health, metrics, and round queries.

**Endpoints**:
```
GET /health:
    Response:
        {
            "status": "running",
            "uptime_seconds": 12345,
            "camera_fps": {"cam0": 25.3, "cam1": 24.8, "cam2": 25.1},
            "last_detection_timestamp": "2024-01-15T14:32:18.123Z"
        }
    
    Algorithm:
        Compute uptime from server start time
        Get camera FPS from metrics
        Get last detection timestamp from metrics
        Return JSON response

GET /metrics:
    Response:
        {
            "detection_counts": {
                "dart_hits": 150,
                "dart_removals": 50,
                "bounce_outs": 5,
                "misses": 10
            },
            "average_detection_latency_ms": 75.3,
            "per_camera_detection_rates": {
                "cam0": 0.95,
                "cam1": 0.92,
                "cam2": 0.88
            },
            "error_counts": {
                "detection_failures": 3,
                "websocket_errors": 1
            }
        }
    
    Algorithm:
        Get metrics from MetricsTracker
        Return JSON response

GET /rounds/current:
    Response:
        {
            "round_state": "in_progress",
            "darts_thrown": 2,
            "darts": [
                {"score": 60, "position": {"x": 2.3, "y": 98.7}},
                {"score": 20, "position": {"x": 5.1, "y": 102.3}}
            ],
            "current_total": 80,
            "bounce_outs": 0,
            "misses": 0
        }
    
    Algorithm:
        Get current_round from RoundAggregator
        If None: return {"round_state": "no_round"}
        Else: serialize current_round to JSON

GET /rounds/latest:
    Response:
        {
            "darts": [
                {"score": 60, "position": {"x": 2.3, "y": 98.7}},
                {"score": 20, "position": {"x": 5.1, "y": 102.3}},
                {"score": 5, "position": {"x": 10.2, "y": 50.3}}
            ],
            "total_score": 85,
            "bounce_outs": 0,
            "misses": 0,
            "round_duration_ms": 15000,
            "completed_at": "2024-01-15T14:32:30.123Z"
        }
    
    Algorithm:
        Get last_completed_round from RoundAggregator
        If None: return null
        Else: serialize completed_round to JSON
```

## Data Models

### Configuration Schema (config.toml additions)

```toml
[api]
host = "0.0.0.0"              # Listen on all interfaces
port = 8000                   # Default HTTP port
ws_events_path = "/ws/events" # WebSocket path for all events
ws_rounds_path = "/ws/rounds" # WebSocket path for round events
enable_cors = true            # Enable CORS for web clients
cors_origins = ["*"]          # Allowed CORS origins
debug = false                 # Debug mode (verbose logging)
event_queue_size = 1000       # Max events in queue
```

### CurrentRound Data Model

```
CurrentRound:
    Fields:
        round_id: string (UUID)
        started_at: timestamp (ISO 8601)
        darts: list of DartInfo
        bounce_outs: integer
        misses: integer
    
    Properties:
        dart_count: integer (length of darts list)
        total_count: integer (dart_count + bounce_outs + misses)
        current_total_score: integer (sum of dart scores)
    
    Methods:
        add_dart(dart_hit_event):
            Create DartInfo from event
            Append to darts list
        
        add_bounce_out():
            Increment bounce_outs counter
        
        add_miss():
            Increment misses counter
        
        to_dict() → dictionary:
            Serialize to JSON-compatible dict
```

### CompletedRound Data Model

```
CompletedRound:
    Fields:
        round_id: string (UUID)
        started_at: timestamp (ISO 8601)
        completed_at: timestamp (ISO 8601)
        darts: list of DartInfo
        bounce_outs: integer
        misses: integer
        total_score: integer
        round_duration_ms: integer
    
    Methods:
        to_dict() → dictionary:
            Serialize to JSON-compatible dict
```

### DartInfo Data Model

```
DartInfo:
    Fields:
        score: integer (total score)
        position: (x, y) in mm
        timestamp: timestamp (ISO 8601)
        confidence: float
    
    Methods:
        to_dict() → dictionary:
            Serialize to JSON-compatible dict
```

### RoundCompleteEvent Data Model

```
RoundCompleteEvent:
    Fields:
        event_type: "round_complete"
        timestamp: timestamp (ISO 8601)
        round: CompletedRound object
    
    Methods:
        to_dict() → dictionary:
            Serialize to JSON-compatible dict
```

### MetricsTracker Data Model

```
MetricsTracker:
    State:
        start_time: timestamp
        detection_counts: dictionary (event_type → count)
        detection_latencies: list of floats
        per_camera_detections: dictionary (camera_id → count)
        error_counts: dictionary (error_type → count)
        last_detection_timestamp: timestamp
        metrics_lock: threading.Lock
    
    Methods:
        record_event(event):
            Increment detection_counts[event.event_type]
            Update last_detection_timestamp
            If DartHitEvent: record per-camera detections
        
        record_latency(latency_ms):
            Append to detection_latencies list
        
        record_error(error_type):
            Increment error_counts[error_type]
        
        get_metrics() → dictionary:
            Return all metrics (thread-safe)
        
        reset():
            Clear all metrics
```

## WebSocket Protocol

### Connection Establishment

**Real-Time Events Endpoint** (`/ws/events`):
```
Client → Server: WebSocket upgrade request to /ws/events
Server → Client: Accept connection
Server → Client: Welcome message
    {
        "event_type": "connection_established",
        "endpoint": "/ws/events",
        "message": "Connected to real-time event stream"
    }

# From this point, all state machine events are broadcast
```

**Round Events Endpoint** (`/ws/rounds`):
```
Client → Server: WebSocket upgrade request to /ws/rounds
Server → Client: Accept connection
Server → Client: Welcome message
    {
        "event_type": "connection_established",
        "endpoint": "/ws/rounds",
        "message": "Connected to round completion stream"
    }

# From this point, only RoundCompleteEvent messages are sent
```

### Message Format

All WebSocket messages are JSON with an `event_type` field:

**Real-Time Events** (sent to `/ws/events`):
```json
{
  "event_type": "dart_hit",
  "timestamp": "2024-01-15T14:32:18.123Z",
  "board_coordinates": {"x_mm": 2.3, "y_mm": 98.7},
  "score": {"base": 20, "multiplier": 3, "total": 60},
  ...
}

{
  "event_type": "dart_removed",
  "timestamp": "2024-01-15T14:32:25.456Z",
  "count_removed": 1,
  "count_remaining": 2
}

{
  "event_type": "dart_bounce_out",
  "timestamp": "2024-01-15T14:32:30.789Z",
  "dart_id": 1,
  "dart_position": {"x_mm": 5.2, "y_mm": 102.3}
}

{
  "event_type": "throw_miss",
  "timestamp": "2024-01-15T14:32:35.123Z",
  "reason": "no_dart_detected"
}
```

**Round Events** (sent to `/ws/rounds`):
```json
{
  "event_type": "round_complete",
  "timestamp": "2024-01-15T14:32:40.123Z",
  "round": {
    "round_id": "550e8400-e29b-41d4-a716-446655440000",
    "started_at": "2024-01-15T14:32:10.000Z",
    "completed_at": "2024-01-15T14:32:40.123Z",
    "darts": [
      {"score": 60, "position": {"x_mm": 2.3, "y_mm": 98.7}, "timestamp": "..."},
      {"score": 20, "position": {"x_mm": 5.1, "y_mm": 102.3}, "timestamp": "..."},
      {"score": 5, "position": {"x_mm": 10.2, "y_mm": 50.3}, "timestamp": "..."}
    ],
    "total_score": 85,
    "bounce_outs": 0,
    "misses": 0,
    "round_duration_ms": 30123
  }
}
```

### Connection Handling

**Graceful Disconnect**:
```
Client closes connection
    ↓
Server detects disconnect
    ↓
Remove from active_connections
    ↓
Log disconnect event
```

**Error Handling**:
```
Broadcast fails for specific connection
    ↓
Log error with connection details
    ↓
Remove connection from active_connections
    ↓
Continue broadcasting to other connections
```

**Multiple Clients**:
- Each endpoint supports 10+ concurrent connections
- Connections are independent (one failure doesn't affect others)
- Broadcast is sequential (not parallel) for simplicity
- Future optimization: parallel broadcast with asyncio

## Error Handling

### Event Queue Full

**Scenario**: Main thread produces events faster than API thread consumes

**Handling**:
```
event_queue.put(event):
    If queue is full:
        Log warning "Event queue full, dropping event"
        Drop oldest event
        Add new event
```

**Behavior**:
- Drop oldest events to prevent blocking main thread
- Log warning for monitoring
- API continues processing newer events

### WebSocket Send Failure

**Scenario**: Client connection broken during broadcast

**Handling**:
```
broadcast(event):
    For each connection:
        Try:
            Send JSON message
        Except WebSocketDisconnect:
            Log info "Client disconnected"
            Remove from active_connections
        Except Exception as e:
            Log error "WebSocket send failed: " + str(e)
            Remove from active_connections
```

**Behavior**:
- Remove failed connection
- Continue broadcasting to other clients
- No impact on other connections

### JSON Serialization Failure

**Scenario**: Event contains non-serializable data

**Handling**:
```
broadcast(event):
    Try:
        json_data = event.to_dict()
        json_string = json.dumps(json_data)
    Except Exception as e:
        Log error "JSON serialization failed: " + str(e)
        Return  # Skip this event
```

**Behavior**:
- Log error with event details
- Skip this event
- Continue processing next events

### Round Aggregation Error

**Scenario**: Invalid event data during round aggregation

**Handling**:
```
process_event(event):
    Try:
        # Process event logic
    Except Exception as e:
        Log error "Round aggregation failed: " + str(e)
        # Reset current round to prevent corruption
        current_round = None
        Return None
```

**Behavior**:
- Log error with event details
- Reset current round to clean state
- Continue processing next events

### Server Thread Crash

**Scenario**: API server thread crashes unexpectedly

**Handling**:
```
start():
    Try:
        Run server loop
    Except Exception as e:
        Log critical "API server crashed: " + str(e)
        # Attempt restart
        If restart_count < 3:
            Log info "Attempting server restart"
            restart_count++
            start()
        Else:
            Log critical "Max restarts exceeded, giving up"
```

**Behavior**:
- Log critical error
- Attempt automatic restart (up to 3 times)
- If restart fails, log and exit gracefully

### REST Endpoint Errors

**Scenario**: REST handler raises exception

**Handling**:
```
@app.get("/health")
def get_health():
    Try:
        # Compute health data
        Return health_response
    Except Exception as e:
        Log error "Health endpoint failed: " + str(e)
        Return {"status": "error", "message": str(e)}, 500
```

**Behavior**:
- Return HTTP 500 with error message
- Log error for debugging
- Don't crash server

## Testing Strategy

### Unit Testing Approach

The API layer uses traditional unit tests (no property-based testing needed):

**Unit Tests**:
- REST endpoint responses (health, metrics, rounds)
- WebSocket connection handling (connect, disconnect, broadcast)
- Round aggregation logic (dart counting, score totals)
- Event queue operations (put, get, thread safety)
- JSON serialization (all event types)
- Error handling (queue full, connection failures)

**Integration Tests**:
- End-to-end API flow (event → queue → broadcast)
- Multiple WebSocket clients (concurrent connections)
- Round completion flow (3 darts → round event)
- REST + WebSocket interaction

**Test Configuration**:
- Use pytest for all tests
- Mock state machine events for testing
- Use FastAPI TestClient for REST endpoints
- Use WebSocket test client for WebSocket endpoints

### Unit Test Examples

**Test: REST Health Endpoint**
```python
def test_health_endpoint():
    """Test GET /health returns correct status"""
    client = TestClient(app)
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "uptime_seconds" in data
    assert "camera_fps" in data
```

**Test: WebSocket Broadcast**
```python
def test_websocket_broadcast():
    """Test event broadcast to multiple clients"""
    ws_manager = WebSocketManager()
    
    # Connect 3 clients
    client1 = MockWebSocket()
    client2 = MockWebSocket()
    client3 = MockWebSocket()
    
    ws_manager.connect(client1)
    ws_manager.connect(client2)
    ws_manager.connect(client3)
    
    # Broadcast event
    event = DartHitEvent(...)
    ws_manager.broadcast(event)
    
    # Verify all clients received message
    assert client1.received_count == 1
    assert client2.received_count == 1
    assert client3.received_count == 1
```

**Test: Round Aggregation**
```python
def test_round_aggregation_three_darts():
    """Test round completes after 3 darts"""
    aggregator = RoundAggregator()
    
    # Add 3 darts
    event1 = DartHitEvent(score=60, ...)
    event2 = DartHitEvent(score=20, ...)
    event3 = DartHitEvent(score=5, ...)
    
    result1 = aggregator.process_event(event1)
    assert result1 is None  # Round not complete
    
    result2 = aggregator.process_event(event2)
    assert result2 is None  # Round not complete
    
    result3 = aggregator.process_event(event3)
    assert result3 is not None  # Round complete
    assert isinstance(result3, RoundCompleteEvent)
    assert result3.round.total_score == 85
```

**Test: Event Queue Thread Safety**
```python
def test_event_queue_thread_safety():
    """Test event queue with concurrent producers/consumers"""
    event_queue = EventQueue()
    
    # Producer thread
    def producer():
        for i in range(100):
            event_queue.put(DartHitEvent(...))
    
    # Consumer thread
    def consumer():
        received = []
        for i in range(100):
            event = event_queue.get(timeout=1.0)
            received.append(event)
        return received
    
    # Run concurrently
    producer_thread = threading.Thread(target=producer)
    consumer_thread = threading.Thread(target=consumer)
    
    producer_thread.start()
    consumer_thread.start()
    
    producer_thread.join()
    consumer_thread.join()
    
    # Verify all events received
    assert event_queue.size() == 0
```

## Performance Considerations

### Event Queue Size

**Challenge**: Large event queue could consume memory

**Solution**:
- Configure max queue size (default: 1000 events)
- Drop oldest events if queue full
- Monitor queue size in metrics

**Expected Impact**: < 10MB memory for 1000 events

### WebSocket Broadcast Latency

**Challenge**: Broadcasting to many clients could delay event delivery

**Solution**:
- Sequential broadcast (simple, predictable)
- Future optimization: asyncio for parallel broadcast
- Monitor broadcast latency in metrics

**Expected Impact**: < 5ms per client (< 50ms for 10 clients)

### JSON Serialization Overhead

**Challenge**: JSON serialization on every broadcast

**Solution**:
- Serialize once, send to all clients
- Use efficient JSON library (orjson if needed)
- Cache serialized events (future optimization)

**Expected Impact**: < 1ms per event serialization

### Thread Synchronization

**Challenge**: Lock contention between main thread and API thread

**Solution**:
- Use queue.Queue (lock-free for most operations)
- Minimize lock duration in round aggregator
- Use separate locks for different resources

**Expected Impact**: < 0.1ms lock overhead per event

## Integration Notes

### Main Loop Integration

Add API server initialization and event pushing to main.py:

```
main():
    # Initialize API server
    api_server = APIServer(config)
    api_server.start()
    
    # Initialize state machine
    state_machine = ThrowStateMachine(...)
    
    # Main loop
    while running:
        # Process state machine
        events = state_machine.process(...)
        
        # Push events to API
        for event in events:
            api_server.push_event(event)
        
        # Display frames, handle keypresses
    
    # Cleanup
    api_server.stop()
```

### Configuration

Add API configuration to config.toml:

```toml
[api]
host = "0.0.0.0"
port = 8000
ws_events_path = "/ws/events"
ws_rounds_path = "/ws/rounds"
enable_cors = true
cors_origins = ["*"]
debug = false
event_queue_size = 1000
```

### Dependencies

Add to requirements.txt:
```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
websockets>=12.0
pydantic>=2.5.0
```

## Future Enhancements

### Event Filtering

**Enhancement**: Allow clients to filter events by type

**Changes Needed**:
- Add query parameters to WebSocket endpoints
- Filter events before broadcasting
- Example: `/ws/events?types=dart_hit,dart_removed`

### Historical Round Storage

**Enhancement**: Store round history in database

**Changes Needed**:
- Add database connection (SQLite or PostgreSQL)
- Store completed rounds in database
- Add REST endpoint: `GET /rounds/history`

### Authentication

**Enhancement**: Require authentication for API access

**Changes Needed**:
- Add API key or JWT authentication
- Protect all endpoints
- Add user management

### Rate Limiting

**Enhancement**: Prevent API abuse with rate limiting

**Changes Needed**:
- Add rate limiting middleware
- Configure limits per endpoint
- Return HTTP 429 when exceeded

### Metrics Dashboard

**Enhancement**: Web UI for metrics visualization

**Changes Needed**:
- Add static file serving
- Create HTML/JS dashboard
- Real-time metrics updates via WebSocket

## Summary

The Web API provides a robust, thread-safe interface for exposing dart detection events and system metrics over HTTP and WebSocket protocols. It serves two distinct consumer types (real-time and round-based) with dedicated WebSocket endpoints, while providing REST endpoints for health checks, metrics, and round queries.

Key benefits:
- **Non-blocking**: Separate thread prevents API from impacting detection loop
- **Thread-safe**: Event queue and locks ensure data consistency
- **Scalable**: Supports 10+ concurrent WebSocket clients per endpoint
- **Flexible**: Two consumer types for different use cases
- **Simple**: Minimal state tracking (current + last round only)
- **Maintainable**: Clear separation of concerns, well-defined interfaces
