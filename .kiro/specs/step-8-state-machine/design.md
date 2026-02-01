# Step 8: Event State Machine (Throw vs Pull-Out) - Design Document

## Overview

This design document specifies the architecture for a state machine that recognizes the complete dart throw lifecycle: idle → throw in progress → dart present → pull-out → idle. The state machine handles all real-game scenarios including multiple darts on the board (up to 3), bounce-outs, misses, and partial pull-outs.

The state machine integrates with existing motion detection (Step 3), dart detection (Step 5), and scoring systems (Step 7) to provide a complete event-driven interface for game logic. It emits structured events (DartHitEvent, DartRemovedEvent, DartBounceOutEvent, ThrowMissEvent) at appropriate state transitions, enabling downstream systems (game logic, API, UI) to react to gameplay events.

**Key Design Principles**:
- Clear state transitions with explicit conditions
- Dart position tracking to distinguish new vs moved darts
- Motion-based pull-out detection (motion near known darts)
- Periodic bounce-out detection (dart falls without motion)
- Timeout handling for all transient states
- Comprehensive event model with complete context
- Non-blocking periodic checks (no impact on main loop)

## Architecture

### Key State Machine Behaviors

**1. Three Darts Required**
The system waits for 3 total darts before transitioning to ThrowFinished:
- Total count = detected darts + bounce-outs
- After 3 total darts → ThrowFinished state (no more throws allowed)
- Player must pull out all darts to reset

**2. Motion Type Classification**
The system distinguishes between dart throws and hand pull-outs:
- **Dart motion**: Fast (high speed), small object, brief duration
- **Hand motion**: Slow (low speed), large object, sustained duration
- Motion analysis uses speed, size, and duration to classify

**3. Pull-Out Can Start Early**
Pull-out can be detected before 3 darts are thrown:
- If hand motion detected in WaitForThrow (0-2 darts) → PullOutStarted
- Once in PullOutStarted, no more throws allowed
- Must remove all darts to return to WaitForThrow

**4. Bounce-Out Counting**
Bounce-outs count toward the 3-dart total:
- Example: 2 darts detected + 1 bounce-out = 3 total → ThrowFinished
- This prevents infinite waiting if darts fall off

**5. Partial Pull-Out Not Allowed**
Once pull-out starts, must remove ALL darts:
- System stays in PullOutStarted until all darts removed
- No returning to WaitForThrow with darts still on board
- Ensures clean state transitions

### Module Structure

```
src/state_machine/
├── __init__.py
├── throw_state_machine.py      # ThrowStateMachine class (main)
├── dart_tracker.py              # DartTracker class
├── motion_analyzer.py           # MotionAnalyzer class
└── events.py                    # Event dataclasses

config.toml additions:
[state_machine]
settled_timeout_ms = 500
throw_timeout_ms = 2000
pull_out_timeout_ms = 2000
dart_movement_threshold_px = 30
motion_near_dart_radius_px = 100
dart_presence_check_interval_ms = 1000
pull_out_motion_threshold = 15
```

### State Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ┌──────────────┐  dart motion   ┌──────────────────┐          │
│  │ WaitForThrow │───────────────→│ ThrowDetected    │          │
│  │ (0-2 darts)  │                └──────────────────┘          │
│  └──────────────┘                         │                    │
│         ↑                                 │ dart detected      │
│         │                                 ↓                    │
│         │                        ┌──────────────┐              │
│         │                        │ WaitForThrow │              │
│         │                        │ (1-2 darts)  │              │
│         │                        └──────────────┘              │
│         │                                 │                    │
│         │                                 │ 3rd dart detected  │
│         │                                 │ or bounce-out      │
│         │                                 ↓                    │
│         │                        ┌──────────────────┐          │
│         │                        │ ThrowFinished    │          │
│         │                        │ (3 darts total)  │          │
│         │                        └──────────────────┘          │
│         │                                 │                    │
│         │                                 │ hand motion        │
│         │                                 ↓                    │
│         │                        ┌──────────────────┐          │
│         │                        │ PullOutStarted   │          │
│         │                        └──────────────────┘          │
│         │                                 │                    │
│         │ all darts removed               │ darts removed      │
│         └─────────────────────────────────┘                    │
│                                                                 │
│  Special case: Hand motion detected in WaitForThrow (0-2 darts)│
│  → Transition directly to PullOutStarted                       │
│                                                                 │
│  Dart count includes: detected darts + bounce-outs             │
└─────────────────────────────────────────────────────────────────┘

States:
- WaitForThrow: Waiting for dart throws (0-2 darts on board)
- ThrowDetected: Fast motion detected, waiting for settling and detection
- ThrowFinished: 3 darts total (detected + bounced out), waiting for pull-out
- PullOutStarted: Hand motion detected, waiting for all darts to be removed
- (Returns to WaitForThrow when all darts removed)

Key Behaviors:
- System counts total darts: detected + bounce-outs
- After 3 total darts → ThrowFinished (no more throws allowed)
- Hand motion distinguished from dart motion by speed and size
- Pull-out can start early (before 3 darts) if hand detected
- Once in PullOutStarted, must remove all darts before returning to WaitForThrow
```

### Class Hierarchy

```
ThrowStateMachine (main state machine)
├── Uses DartTracker for position tracking and counting
├── Uses MotionClassifier for dart vs hand motion
├── Uses MotionDetector (from Step 3)
├── Uses DartDetector (from Step 5)
└── Uses ScoreCalculator (from Step 7)

DartTracker
├── add_dart(position) → dart_id
├── remove_dart(dart_id)
├── increment_bounce_out_count()
├── get_total_dart_count() → integer (detected + bounced out)
├── get_detected_dart_count() → integer
├── get_bounce_out_count() → integer
├── get_known_positions() → list of positions
├── clear_all()
└── is_at_capacity() → boolean (total >= 3)

MotionClassifier
├── classify_motion(motion_data) → MotionType (DART or HAND)
├── compute_motion_speed(motion_data) → float
├── compute_motion_size(motion_data) → float
└── compute_motion_duration(motion_data) → float

Event Dataclasses:
├── DartHitEvent (from Step 7)
├── DartRemovedEvent
├── DartBounceOutEvent
└── ThrowMissEvent
```

### Data Flow

```
Main Loop (motion detection)
    ↓
Motion Detected
    ↓
[MotionClassifier.classify_motion()] → DART or HAND
    ↓
If DART motion:
    [ThrowStateMachine.process_dart_motion()]
    ↓
    State: WaitForThrow → ThrowDetected
    ↓
    Wait for Settling (0.5s continuous low motion)
    ↓
    Run Dart Detection (all cameras)
    ↓
    If dart detected:
        [DartTracker.add_dart()]
        [DartTracker.get_total_dart_count()]
        Emit DartHitEvent
        ↓
        If total_count < 3:
            State: ThrowDetected → WaitForThrow
        Else:
            State: ThrowDetected → ThrowFinished
    ↓
    If no dart detected:
        State: ThrowDetected → WaitForThrow
        Emit ThrowMissEvent
    ↓
If HAND motion:
    [ThrowStateMachine.process_hand_motion()]
    ↓
    State: WaitForThrow or ThrowFinished → PullOutStarted
    ↓
    Wait for Settling
    ↓
    Re-detect darts
    Compare with known positions
    ↓
    For each missing dart:
        [DartTracker.remove_dart()]
        Emit DartRemovedEvent
    ↓
    If all darts removed:
        [DartTracker.clear_all()]
        State: PullOutStarted → WaitForThrow
    Else:
        State: PullOutStarted → PullOutStarted (stay until all removed)
    ↓
Periodic Check (every 1s in WaitForThrow or ThrowFinished):
    Re-detect darts
    Compare with known positions
    ↓
    If dart disappeared:
        [DartTracker.remove_dart()]
        [DartTracker.increment_bounce_out_count()]
        Emit DartBounceOutEvent
        ↓
        If total_count >= 3:
            State: WaitForThrow → ThrowFinished
```

### Integration with Existing System

The state machine replaces the simple motion state tracking in main.py:

```
main():
    # Initialize components
    state_machine = ThrowStateMachine(config, dart_detectors, score_calculator)
    
    # Main loop
    while true:
        # Get frames from all cameras
        frames = get_all_frames()
        
        # Process motion detection
        motion_detected, motion_data = motion_detector.detect(frames)
        
        # NEW: Process state machine
        events = state_machine.process(motion_detected, motion_data, frames)
        
        # Handle emitted events
        for event in events:
            if isinstance(event, DartHitEvent):
                log_info("Dart hit: " + event.score.total + " points")
                save_event(event)
                # Update game state
            
            elif isinstance(event, DartRemovedEvent):
                log_info("Darts removed: " + event.count_removed)
                # Update game state
            
            elif isinstance(event, DartBounceOutEvent):
                log_warning("Dart bounced out")
                # Update game state
            
            elif isinstance(event, ThrowMissEvent):
                log_info("Throw missed")
                # Update game state
        
        # Display frames in dev mode
        # Handle keypresses
```

## Components and Interfaces

### 1. ThrowStateMachine Class

**Purpose**: Main state machine orchestrating throw lifecycle with 3-dart counting and dart/hand motion distinction.

**Interface**:
```
ThrowStateMachine:
    State:
        current_state: enum (WaitForThrow, ThrowDetected, ThrowFinished, PullOutStarted)
        state_entry_time: timestamp (when current state was entered)
    
    Components:
        dart_tracker: DartTracker instance
        motion_classifier: MotionClassifier instance
        dart_detectors: dictionary of DartDetector instances (per camera)
        score_calculator: ScoreCalculator instance
        config: configuration object
    
    Timers:
        last_periodic_check: timestamp (for bounce-out detection)
    
    Methods:
        process(motion_detected, motion_data, frames) → list of events
            Input: Motion detection result, motion data, current frames
            Output: List of events emitted during this cycle
            
            Algorithm:
                1. Check for timeouts in current state
                2. If timeout: handle timeout, emit events if needed
                3. If motion detected:
                   a. Classify motion type (DART or HAND)
                   b. Process based on motion type and current state
                4. Run periodic checks (bounce-out detection)
                5. Return list of emitted events
        
        handle_wait_for_throw(motion_type, motion_data, frames) → events
            If motion_type == DART:
                transition to ThrowDetected
                return []
            
            If motion_type == HAND:
                transition to PullOutStarted
                return []
            
            # Periodic bounce-out check
            if time_since_last_check >= 1 second:
                re-detect darts
                for each missing dart:
                    remove from tracker
                    increment bounce-out count
                    events.append(DartBounceOutEvent)
                
                if total_dart_count >= 3:
                    transition to ThrowFinished
                
                return events
            
            return []
        
        handle_throw_detected(motion_data, frames) → events
            Check if motion settled (0.5s continuous low motion):
                If settled:
                    run dart detection
                    if dart detected:
                        add to tracker
                        total_count = get_total_dart_count()
                        
                        if total_count < 3:
                            transition to WaitForThrow
                        else:
                            transition to ThrowFinished
                        
                        return [DartHitEvent]
                    else:
                        transition to WaitForThrow
                        return [ThrowMissEvent]
            
            Check timeout (2 seconds):
                If timeout:
                    transition to WaitForThrow
                    return [ThrowMissEvent(reason="timeout")]
            
            return []
        
        handle_throw_finished(motion_type, motion_data, frames) → events
            If motion_type == HAND:
                transition to PullOutStarted
                return []
            
            # Periodic bounce-out check (same as WaitForThrow)
            if time_since_last_check >= 1 second:
                re-detect darts
                for each missing dart:
                    remove from tracker
                    events.append(DartBounceOutEvent)
                
                return events
            
            return []
        
        handle_pull_out_started(motion_data, frames) → events
            Check if motion settled:
                If settled:
                    re-detect darts
                    compare with known positions
                    removed_count = 0
                    for each missing dart:
                        remove from tracker
                        removed_count++
                    
                    if removed_count > 0:
                        events = [DartRemovedEvent(removed_count, remaining_count)]
                        
                        if all darts removed:
                            clear tracker
                            transition to WaitForThrow
                        else:
                            # Stay in PullOutStarted until all removed
                            remain in PullOutStarted
                        
                        return events
                    else:
                        # No darts removed yet, keep waiting
                        remain in PullOutStarted
                        return []
            
            Check timeout (5 seconds):
                If timeout:
                    # Player may have paused mid-pull-out
                    # Stay in PullOutStarted, log warning
                    log_warning("Pull-out timeout, waiting for completion")
                    return []
            
            return []
        
        detect_darts(frames) → list of detections
            Run dart detection on all cameras
            Fuse detections using score_calculator
            Return list of detected dart positions (board coordinates)
        
        is_motion_settled(motion_data) → boolean
            Check if motion below threshold for settled_timeout_ms
            Return true if settled, false otherwise
```

### 2. DartTracker Class

**Purpose**: Track known dart positions, count total darts (detected + bounced out), and manage dart lifecycle.

**Interface**:
```
DartTracker:
    State:
        known_darts: dictionary mapping dart_id → (x, y, timestamp)
        bounce_out_count: integer (number of darts that bounced out)
        next_dart_id: integer (auto-incrementing)
    
    Methods:
        add_dart(position) → dart_id
            Input: Board coordinates (x, y) in mm
            Output: Unique dart ID
            
            Algorithm:
                1. Generate unique dart_id
                2. Store position with timestamp
                3. Return dart_id
        
        remove_dart(dart_id)
            Remove dart from known_darts dictionary
        
        increment_bounce_out_count()
            Increment bounce_out_count by 1
        
        get_total_dart_count() → integer
            Return detected_count + bounce_out_count
        
        get_detected_dart_count() → integer
            Return count of darts in known_darts
        
        get_bounce_out_count() → integer
            Return bounce_out_count
        
        get_known_positions() → list of (x, y)
            Return list of all known dart positions
        
        clear_all()
            Remove all darts from tracker
            Reset bounce_out_count to 0
            Reset next_dart_id to 0
        
        is_at_capacity() → boolean
            Return true if total_dart_count >= 3
        
        get_dart_position(dart_id) → (x, y) or null
            Return position of specific dart, or null if not found
```

### 3. MotionClassifier Class

**Purpose**: Classify motion as dart throw (fast, small) or hand pull-out (slow, large) based on motion characteristics.

**Interface**:
```
MotionClassifier:
    Configuration:
        dart_speed_threshold: 500 px/s (minimum speed for dart)
        hand_speed_threshold: 200 px/s (maximum speed for hand)
        dart_size_threshold: 100 px² (maximum size for dart)
        hand_size_threshold: 500 px² (minimum size for hand)
        dart_duration_threshold: 200 ms (maximum duration for dart)
        hand_duration_threshold: 500 ms (minimum duration for hand)
    
    Methods:
        classify_motion(motion_data) → MotionType (DART or HAND)
            Input: Motion data from motion detector
            Output: MotionType enum (DART or HAND)
            
            Algorithm:
                1. Compute motion speed (pixels per second)
                2. Compute motion size (bounding box area)
                3. Compute motion duration (milliseconds)
                4. Apply classification rules:
                   
                   If speed > dart_speed_threshold AND
                      size < dart_size_threshold AND
                      duration < dart_duration_threshold:
                       → DART
                   
                   Else if speed < hand_speed_threshold AND
                           size > hand_size_threshold AND
                           duration > hand_duration_threshold:
                       → HAND
                   
                   Else:
                       → UNKNOWN (log warning, default to DART for safety)
        
        compute_motion_speed(motion_data) → float
            Input: Motion data with position history
            Output: Speed in pixels per second
            
            Algorithm:
                1. Get first and last motion positions
                2. Compute distance traveled
                3. Compute time elapsed
                4. Return distance / time
        
        compute_motion_size(motion_data) → float
            Input: Motion data with bounding box
            Output: Area in pixels²
            
            Algorithm:
                1. Get bounding box (x, y, width, height)
                2. Return width × height
        
        compute_motion_duration(motion_data) → float
            Input: Motion data with timestamps
            Output: Duration in milliseconds
            
            Algorithm:
                1. Get first and last motion timestamps
                2. Return time_last - time_first
```

### 4. Event Dataclasses

**Purpose**: Structured event models for all state transitions, providing complete context for downstream systems.

**Data Structures**:
```
DartHitEvent (from Step 7):
    timestamp: string (ISO 8601)
    board_x, board_y: float (fused board coordinates in mm)
    radius: float (distance from center in mm)
    angle_deg: float (angle in degrees)
    score: Score object (base, multiplier, total, ring, sector)
    fusion_confidence: float
    cameras_used: list of integers
    detections: list of CameraDetection objects
    image_paths: dictionary mapping camera_id → image path
    
    Methods:
        to_dict() → dictionary (JSON-serializable)

DartRemovedEvent:
    timestamp: string (ISO 8601)
    count_removed: integer (number of darts removed)
    count_remaining: integer (number of darts still on board)
    removed_dart_ids: list of integers (IDs of removed darts)
    
    Methods:
        to_dict() → dictionary (JSON-serializable)

DartBounceOutEvent:
    timestamp: string (ISO 8601)
    dart_id: integer (ID of dart that bounced out)
    dart_position: (x, y) in mm (last known position)
    time_on_board_ms: integer (time from hit to bounce-out)
    
    Methods:
        to_dict() → dictionary (JSON-serializable)

ThrowMissEvent:
    timestamp: string (ISO 8601)
    motion_data: dictionary (motion detection data)
    reason: string ("timeout" or "no_dart_detected")
    
    Methods:
        to_dict() → dictionary (JSON-serializable)
```

## Data Models

### Configuration Schema (config.toml additions)

```toml
# State machine configuration
[state_machine]
settled_timeout_ms = 500          # Wait for motion to settle
throw_timeout_ms = 2000           # Max time to detect dart after motion
pull_out_timeout_ms = 5000        # Max time for pull-out (longer for manual removal)

# Motion classification (dart vs hand)
[motion_classification]
dart_speed_threshold_px_per_s = 500    # Minimum speed for dart throw
hand_speed_threshold_px_per_s = 200    # Maximum speed for hand
dart_size_threshold_px2 = 100          # Maximum size for dart (bounding box area)
hand_size_threshold_px2 = 500          # Minimum size for hand
dart_duration_threshold_ms = 200       # Maximum duration for dart motion
hand_duration_threshold_ms = 500       # Minimum duration for hand motion

# Bounce-out detection
[bounce_out_detection]
check_interval_ms = 1000          # How often to check for bounce-out
```

### Event JSON Formats

**DartHitEvent** (from Step 7, included for completeness):
```json
{
  "event_type": "dart_hit",
  "timestamp": "2024-01-15T14:32:18.123456Z",
  "board_coordinates": {"x_mm": 2.3, "y_mm": 98.7},
  "polar_coordinates": {"radius_mm": 98.7, "angle_deg": 88.6},
  "score": {"base": 20, "multiplier": 3, "total": 60, "ring": "triple", "sector": 20},
  "fusion": {"confidence": 0.82, "cameras_used": [0, 1, 2], "num_cameras": 3},
  "detections": [...],
  "image_paths": {...}
}
```

**DartRemovedEvent**:
```json
{
  "event_type": "dart_removed",
  "timestamp": "2024-01-15T14:32:25.456789Z",
  "count_removed": 1,
  "count_remaining": 2,
  "removed_dart_ids": [0]
}
```

**DartBounceOutEvent**:
```json
{
  "event_type": "dart_bounce_out",
  "timestamp": "2024-01-15T14:32:30.789012Z",
  "dart_id": 1,
  "dart_position": {"x_mm": 5.2, "y_mm": 102.3},
  "time_on_board_ms": 3500
}
```

**ThrowMissEvent**:
```json
{
  "event_type": "throw_miss",
  "timestamp": "2024-01-15T14:32:35.123456Z",
  "motion_data": {
    "max_motion": 45.2,
    "motion_duration_ms": 150
  },
  "reason": "no_dart_detected"
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property Reflection

After analyzing all acceptance criteria, I identified the following testable properties and eliminated redundancy:

**Redundancy Analysis**:
- AC-8.1.5 is redundant with AC-8.1.3 (both test settling timeout)
- AC-8.2.3 is redundant with AC-8.2.2 (inverse of same distance threshold)
- AC-8.5.2 is redundant with AC-8.1.4 (same timeout behavior)
- AC-8.6.1, AC-8.6.2, AC-8.6.3, AC-8.6.4 (event structure) → Combined into Property 8 (event completeness)

**Properties to Test**:
1. State transition correctness (valid sequences)
2. Dart position classification (new vs moved)
3. Motion near darts detection
4. Dart count invariant
5. Periodic check timing
6. Miss event preservation of dart positions
7. State readiness after miss
8. Event structure completeness
9. Event JSON serialization round trip

### Property 1: State Transition Correctness

*For any* valid sequence of motion and detection events, the state machine should follow the correct transition path: Idle → ThrowInProgress (on motion) → DartPresent (on dart detected) or Idle (on timeout/miss), and DartPresent → PullOutInProgress (on motion near darts) → Idle or DartPresent (on settling).

**Validates: Requirements AC-8.1.1, AC-8.3.1**

**Test Strategy**: Generate random sequences of motion/detection events and verify state transitions follow the state diagram. Test all valid paths and verify invalid transitions are rejected.

### Property 2: Dart Position Classification

*For any* detected dart position and set of known dart positions, the classification should be "new dart" if distance > 30px from all known darts, and "moved dart" if distance ≤ 30px from any known dart.

**Validates: Requirements AC-8.2.2, AC-8.2.3**

**Test Strategy**: Generate random dart positions and known position sets. Compute distances manually and verify classification matches expected result. Test boundary cases (exactly 30px, 29px, 31px).

### Property 3: Motion Near Darts Detection

*For any* motion centroid position and set of known dart positions, motion should be classified as "near darts" if distance < 100px from any dart, and "not near darts" otherwise.

**Validates: Requirements AC-8.3.2**

**Test Strategy**: Generate random motion positions and dart position sets. Verify classification based on minimum distance to any dart. Test boundary cases (exactly 100px, 99px, 101px).

### Property 4: Dart Count Invariant

*For any* state of the dart tracker, the dart count should always equal the number of known dart positions, and should never exceed 3 or go below 0.

**Validates: Requirements AC-8.2.1, AC-8.2.4**

**Test Strategy**: Perform random sequences of add_dart() and remove_dart() operations. After each operation, verify count equals length of known positions list, and verify 0 ≤ count ≤ 3.

### Property 5: Periodic Check Timing

*For any* time spent in DartPresent state, periodic bounce-out checks should occur at intervals of approximately 1 second (±100ms tolerance for processing delays).

**Validates: Requirements AC-8.4.1**

**Test Strategy**: Simulate time progression in DartPresent state. Record timestamps of periodic checks. Verify intervals are within 1000ms ± 100ms tolerance.

### Property 6: Miss Event Preservation of Dart Positions

*For any* throw miss event (motion without dart detection), the known dart positions should remain unchanged before and after the miss.

**Validates: Requirements AC-8.5.5**

**Test Strategy**: Set up known dart positions, trigger a miss event, verify known positions are identical before and after. Test with 0, 1, 2, and 3 darts on board.

### Property 7: State Readiness After Miss

*For any* throw miss event, the state machine should return to a ready state (Idle if no darts on board, DartPresent if darts remain) immediately after the miss, allowing the next throw to be processed.

**Validates: Requirements AC-8.5.4**

**Test Strategy**: Trigger miss events from various states. Verify state transitions to correct ready state. Verify next motion event is processed correctly.

### Property 8: Event Structure Completeness

*For any* emitted event (DartHitEvent, DartRemovedEvent, DartBounceOutEvent, ThrowMissEvent), the event should contain all required fields with valid values: timestamp (ISO 8601 format), event-specific data fields, and all fields should be non-null.

**Validates: Requirements AC-8.6.1, AC-8.6.2, AC-8.6.3, AC-8.6.4**

**Test Strategy**: Generate random events of each type. Verify all required fields present and non-null. Verify timestamp format. Verify field types and value ranges.

### Property 9: Event JSON Serialization Round Trip

*For any* valid event object, serializing to JSON then deserializing should produce an equivalent event with all fields matching within floating-point tolerance.

**Validates: Requirements AC-8.6.5**

**Test Strategy**: Generate random events, serialize with to_dict(), deserialize, verify all fields match. Test all event types.

## Error Handling

### Motion Detection Failure

**Scenario**: Motion detector fails or returns invalid data

**Handling**:
```
process(motion_detected, motion_data, frames):
    if motion_data is null or invalid:
        log_warning("Invalid motion data, skipping cycle")
        return []  # No events emitted
    
    # Continue processing...
```

**Behavior**:
- Skip processing for this cycle
- Log warning
- No state transitions
- No events emitted
- System recovers on next valid cycle

### Dart Detection Failure

**Scenario**: All cameras fail to detect dart after motion settles

**Handling**:
```
handle_throw_in_progress(motion_data, frames):
    if motion_settled:
        detections = detect_darts(frames)
        
        if detections is empty or null:
            log_info("No dart detected after settling")
            transition to previous_state (or Idle)
            return [ThrowMissEvent(reason="no_dart_detected")]
```

**Behavior**:
- Emit ThrowMissEvent
- Return to previous state (Idle if no darts, DartPresent if darts remain)
- Log as miss
- System ready for next throw

### Timeout in ThrowInProgress

**Scenario**: Motion detected but dart not detected within 2 seconds

**Handling**:
```
handle_throw_in_progress(motion_data, frames):
    time_in_state = current_time - state_entry_time
    
    if time_in_state > throw_timeout_ms:
        log_warning("Throw timeout: no dart detected after 2 seconds")
        transition to previous_state (or Idle)
        return [ThrowMissEvent(reason="timeout")]
```

**Behavior**:
- Emit ThrowMissEvent with reason="timeout"
- Return to previous state
- Log timeout warning
- Prevents indefinite waiting

### Timeout in PullOutInProgress

**Scenario**: Motion near darts but no change detected within 2 seconds

**Handling**:
```
handle_pull_out_in_progress(motion_data, frames):
    time_in_state = current_time - state_entry_time
    
    if time_in_state > pull_out_timeout_ms:
        log_warning("Pull-out timeout: assuming false alarm")
        transition to DartPresent
        return []  # No events, false alarm
```

**Behavior**:
- Return to DartPresent state
- No events emitted (false alarm)
- Log timeout warning
- Known dart positions unchanged

### Dart Count Exceeds Maximum

**Scenario**: Detection finds 4th dart (should be impossible in real game)

**Handling**:
```
handle_throw_in_progress(motion_data, frames):
    if dart_tracker.get_dart_count() >= 3:
        log_warning("Maximum darts (3) already on board, ignoring detection")
        transition to DartPresent
        return []  # No event, ignore detection
```

**Behavior**:
- Ignore 4th dart detection
- Log warning
- No event emitted
- Remain in DartPresent state
- Suggests user should remove darts

### Periodic Check Detects All Darts Gone

**Scenario**: All darts bounce out between periodic checks

**Handling**:
```
handle_dart_present(motion_detected, motion_data, frames):
    if time_since_last_check >= 1 second:
        current_detections = detect_darts(frames)
        
        if current_detections is empty:
            # All darts gone
            events = []
            for each dart_id in known_darts:
                events.append(DartBounceOutEvent(dart_id, ...))
            
            dart_tracker.clear_all()
            transition to Idle
            return events
```

**Behavior**:
- Emit DartBounceOutEvent for each missing dart
- Clear all known positions
- Transition to Idle
- Log bounce-out events

### Invalid Dart Position

**Scenario**: Detected dart position is out of bounds or invalid

**Handling**:
```
detect_darts(frames):
    detections = score_calculator.process_detections(...)
    
    if detections is null or detections.board_x is null:
        log_warning("Invalid dart position detected")
        return []  # Treat as no detection
    
    # Validate position is within reasonable bounds
    if abs(detections.board_x) > 200 or abs(detections.board_y) > 200:
        log_warning("Dart position out of bounds: " + detections.board_x + ", " + detections.board_y)
        return []  # Treat as no detection
    
    return [detections]
```

**Behavior**:
- Treat as no detection
- Log warning with position
- No event emitted
- Prevents invalid positions from entering tracker

### Concurrent State Transitions

**Scenario**: Multiple events occur simultaneously (e.g., timeout and motion)

**Design Approach**:
- Process events in priority order:
  1. Timeouts (highest priority)
  2. Periodic checks
  3. Motion events
  4. User input (future)
- Only one state transition per cycle
- Events queued for next cycle if needed

**Behavior**:
- Deterministic state transitions
- No race conditions
- Clear priority ordering
- Predictable behavior

## Testing Strategy

### Dual Testing Approach

The state machine requires both unit tests and property-based tests for comprehensive validation:

**Unit Tests**: Verify specific scenarios and edge cases
- Basic throw sequence (TC8.1)
- Three consecutive darts (TC8.2)
- Partial pull-out (TC8.3)
- Full pull-out (TC8.4)
- Bounce-out (TC8.5)
- Throw miss (TC8.6)
- "180 scenario" - 3rd dart pushes others (TC8.7)
- Rapid throws (TC8.8)
- Timeout scenarios
- Error handling (invalid data, detection failures)

**Property Tests**: Verify universal properties across all inputs
- State transition correctness for all valid sequences
- Dart position classification for all distance combinations
- Motion near darts detection for all position combinations
- Dart count invariant after all operations
- Periodic check timing across various durations
- Event structure completeness for all event types
- JSON serialization round trip for all events

Both approaches are complementary and necessary for ensuring correctness.

### Property-Based Testing Configuration

**Library**: Use `hypothesis` for Python property-based testing

**Installation**:
```bash
pip install hypothesis
```

**Configuration**:
- Minimum 100 iterations per property test (due to randomization)
- Each property test references its design document property
- Tag format: `# Feature: step-8-state-machine, Property N: [property text]`

**Example Property Test**:
```python
from hypothesis import given, strategies as st
import math

@given(
    dart_x=st.floats(min_value=-200, max_value=200, allow_nan=False),
    dart_y=st.floats(min_value=-200, max_value=200, allow_nan=False),
    known_positions=st.lists(
        st.tuples(
            st.floats(min_value=-200, max_value=200, allow_nan=False),
            st.floats(min_value=-200, max_value=200, allow_nan=False)
        ),
        max_size=3
    )
)
def test_dart_position_classification(dart_x, dart_y, known_positions):
    """
    Feature: step-8-state-machine, Property 2: Dart Position Classification
    
    For any detected dart position and set of known positions, classification
    should be "new" if distance > 30px from all known darts, "moved" otherwise.
    """
    dart_tracker = DartTracker(config)
    
    # Add known positions
    for pos in known_positions:
        dart_tracker.add_dart(pos)
    
    # Check classification
    matching_dart = dart_tracker.find_matching_dart((dart_x, dart_y))
    
    # Compute expected result
    min_distance = float('inf')
    for known_x, known_y in known_positions:
        distance = math.sqrt((dart_x - known_x)**2 + (dart_y - known_y)**2)
        min_distance = min(min_distance, distance)
    
    if len(known_positions) == 0:
        # No known darts, should be new
        assert matching_dart is None
    elif min_distance > 30:
        # Far from all known darts, should be new
        assert matching_dart is None
    else:
        # Close to a known dart, should match
        assert matching_dart is not None
```

### Unit Test Examples

**Test TC8.1: Basic Throw Sequence**
```python
def test_basic_throw_sequence():
    """Test: Idle → motion → ThrowInProgress → settled → dart detected → DartPresent"""
    state_machine = ThrowStateMachine(config, dart_detectors, score_calculator)
    
    # Initial state: Idle
    assert state_machine.current_state == State.Idle
    
    # Motion detected
    events = state_machine.process(motion_detected=True, motion_data={...}, frames={...})
    assert state_machine.current_state == State.ThrowInProgress
    assert len(events) == 0
    
    # Wait for settling (simulate 0.5s)
    time.sleep(0.5)
    
    # Motion settled, dart detected
    events = state_machine.process(motion_detected=False, motion_data={...}, frames={...})
    assert state_machine.current_state == State.DartPresent
    assert len(events) == 1
    assert isinstance(events[0], DartHitEvent)
```

**Test TC8.6: Throw Miss**
```python
def test_throw_miss():
    """Test: Motion detected but no dart found → ThrowMissEvent"""
    state_machine = ThrowStateMachine(config, dart_detectors, score_calculator)
    
    # Motion detected
    events = state_machine.process(motion_detected=True, motion_data={...}, frames={...})
    assert state_machine.current_state == State.ThrowInProgress
    
    # Wait for settling, no dart detected
    time.sleep(0.5)
    events = state_machine.process(motion_detected=False, motion_data={...}, frames={...})
    
    assert state_machine.current_state == State.Idle
    assert len(events) == 1
    assert isinstance(events[0], ThrowMissEvent)
    assert events[0].reason == "no_dart_detected"
```

## Performance Considerations

### Periodic Check Overhead

**Challenge**: Periodic bounce-out checks (every 1 second) could impact main loop performance

**Solution**:
- Only run periodic checks in DartPresent state
- Use lightweight detection (single-camera or reduced resolution)
- Cache last check timestamp to avoid redundant checks
- Run checks asynchronously if needed (future optimization)

**Expected Impact**: < 10ms per periodic check (negligible)

### State Transition Logging

**Challenge**: Excessive logging could slow down main loop

**Solution**:
- Use structured logging with appropriate levels
- State transitions: INFO level
- Dart tracking operations: DEBUG level
- Error conditions: WARNING/ERROR level
- Configurable log verbosity

**Expected Impact**: < 1ms per log statement

### Dart Position Comparison

**Challenge**: Comparing detected position with all known darts (up to 3) on every detection

**Solution**:
- Simple Euclidean distance calculation (fast)
- Maximum 3 comparisons per detection
- Early exit on first match found

**Expected Impact**: < 0.1ms for 3 comparisons

### Event Serialization

**Challenge**: JSON serialization of events could be slow

**Solution**:
- Serialize events asynchronously (future optimization)
- Use efficient JSON library (orjson if needed)
- Only serialize when saving to disk (not for in-memory events)

**Expected Impact**: < 5ms per event serialization (acceptable)

## Future Enhancements

### Multi-Player Support

**Enhancement**: Track darts per player, emit player-specific events

**Changes Needed**:
- Add player_id to DartTracker
- Separate known_darts per player
- Player-specific DartHitEvent and DartRemovedEvent
- Game state management (whose turn, score tracking)

### Confidence-Based Dart Tracking

**Enhancement**: Weight dart positions by detection confidence

**Changes Needed**:
- Store confidence with each known dart position
- Use confidence-weighted distance for matching
- Prefer high-confidence detections over low-confidence

### Adaptive Thresholds

**Enhancement**: Adjust movement_threshold and motion_near_dart_radius based on observed data

**Changes Needed**:
- Collect statistics on dart position variance
- Adjust thresholds dynamically
- Provide configuration override

### State Machine Visualization

**Enhancement**: Real-time visualization of state transitions for debugging

**Changes Needed**:
- Add state transition logging with timestamps
- Create visualization tool (web UI or terminal)
- Display current state, known darts, recent events

### Event Replay

**Enhancement**: Record and replay event sequences for testing and debugging

**Changes Needed**:
- Serialize all events to log file
- Create replay tool that feeds events to state machine
- Verify state transitions match original sequence

## Integration Notes

### Main Loop Integration

The state machine replaces the simple motion state tracking in main.py. Key changes:

1. **Remove old state tracking**:
   - Remove `motion_state` variable
   - Remove manual state transitions

2. **Add state machine**:
   - Initialize `ThrowStateMachine` with config and components
   - Call `state_machine.process()` in main loop
   - Handle returned events

3. **Event handling**:
   - Add event handlers for each event type
   - Update game state based on events
   - Save events to disk
   - Send events to API (future)

### Configuration Migration

Add new state machine configuration to config.toml:

```toml
[state_machine]
settled_timeout_ms = 500
throw_timeout_ms = 2000
pull_out_timeout_ms = 2000
dart_movement_threshold_px = 30
motion_near_dart_radius_px = 100
dart_presence_check_interval_ms = 1000
pull_out_motion_threshold = 15
```

### Backward Compatibility

The state machine is a new component and does not break existing functionality:
- Dart detection (Step 5) unchanged
- Coordinate mapping (Step 6) unchanged
- Scoring (Step 7) unchanged
- Motion detection (Step 3) unchanged

All existing components are used as-is by the state machine.

## Summary

The state machine provides a robust, event-driven interface for dart throw lifecycle management. It handles all real-game scenarios (multiple darts, bounce-outs, misses, partial pull-outs) with clear state transitions and comprehensive event emission. The design emphasizes correctness through property-based testing, performance through efficient algorithms, and maintainability through clear separation of concerns.

Key benefits:
- **Correctness**: Property-based tests ensure all state transitions are valid
- **Completeness**: Handles all edge cases (timeouts, errors, concurrent events)
- **Performance**: Minimal overhead (< 10ms per cycle)
- **Maintainability**: Clear state diagram, well-defined interfaces
- **Extensibility**: Easy to add new states, events, or behaviors
