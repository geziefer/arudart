# Step 8: Event State Machine (Throw vs Pull-Out)

## Overview

Implement a state machine to recognize the complete dart throw sequence: wait for throw → throw detected → throw finished (3 darts) → pull-out started → wait for throw. This handles all real-game scenarios including multiple darts, bounce-outs, misses, and early pull-outs.

The system counts total darts (detected + bounce-outs) and transitions to "throw finished" after 3 darts. Motion is classified as either dart throws (fast, small, brief) or hand pull-outs (slow, large, sustained). Once pull-out starts, all darts must be removed before returning to the waiting state.

## User Stories

### US-8.1: Basic Throw Sequence
**As a** system  
**I want to** recognize the complete throw sequence from waiting to dart detected  
**So that** I can emit a DartHitEvent at the correct time

**Acceptance Criteria:**
- AC-8.1.1: State transitions: WaitForThrow → ThrowDetected (dart motion) → WaitForThrow (dart detected, count < 3)
- AC-8.1.2: DartHitEvent emitted when dart is detected and added to tracker
- AC-8.1.3: System waits for motion to settle before detecting dart (0.5s continuous low motion)
- AC-8.1.4: Throw timeout: If no dart detected after 2 seconds, return to WaitForThrow
- AC-8.1.5: System handles camera vibration from dart impact (waits for settling)

### US-8.2: Three Dart Counting
**As a** system  
**I want to** count total darts (detected + bounce-outs) and transition to ThrowFinished at 3  
**So that** I know when the player's turn is complete

**Acceptance Criteria:**
- AC-8.2.1: System tracks total dart count = detected darts + bounce-outs
- AC-8.2.2: After 3rd dart detected: transition from ThrowDetected → ThrowFinished
- AC-8.2.3: After bounce-out brings total to 3: transition from WaitForThrow → ThrowFinished
- AC-8.2.4: ThrowFinished state waits for hand motion to begin pull-out
- AC-8.2.5: No more dart throws allowed in ThrowFinished state

### US-8.3: Motion Classification
**As a** system  
**I want to** distinguish dart throws from hand pull-outs based on motion characteristics  
**So that** I can correctly identify player intent

**Acceptance Criteria:**
- AC-8.3.1: Dart motion: fast (>500 px/s), small (<100 px²), brief (<200 ms)
- AC-8.3.2: Hand motion: slow (<200 px/s), large (>500 px²), sustained (>500 ms)
- AC-8.3.3: Motion classifier computes speed, size, and duration from motion data
- AC-8.3.4: Dart motion in WaitForThrow or ThrowFinished → ThrowDetected
- AC-8.3.5: Hand motion in WaitForThrow or ThrowFinished → PullOutStarted

### US-8.4: Pull-Out Detection
**As a** system  
**I want to** detect when darts are removed from the board  
**So that** I can emit DartRemovedEvent and reset for next turn

**Acceptance Criteria:**
- AC-8.4.1: State transitions: WaitForThrow/ThrowFinished → PullOutStarted (hand motion)
- AC-8.4.2: System waits for motion to settle before re-detecting darts
- AC-8.4.3: All darts removed → transition to WaitForThrow, emit DartRemovedEvent
- AC-8.4.4: Some darts remain → stay in PullOutStarted, emit DartRemovedEvent with count
- AC-8.4.5: No darts removed (false alarm) → stay in PullOutStarted, wait for completion
- AC-8.4.6: Pull-out timeout (5 seconds) → log warning, stay in PullOutStarted

### US-8.5: Bounce-Out Detection
**As a** system  
**I want to** detect when a dart falls off the board without pull-out motion  
**So that** I can update game state correctly

**Acceptance Criteria:**
- AC-8.5.1: Periodic dart presence check every 1 second while in WaitForThrow or ThrowFinished
- AC-8.5.2: Re-detect all darts and compare with known positions
- AC-8.5.3: If dart disappeared: emit DartBounceOutEvent, increment bounce-out count
- AC-8.5.4: If total count reaches 3: transition from WaitForThrow → ThrowFinished
- AC-8.5.5: Bounce-out distinguished from pull-out by lack of hand motion

### US-8.6: Throw Miss Detection
**As a** system  
**I want to** detect when a throw misses the board  
**So that** I can log the miss and continue gameplay

**Acceptance Criteria:**
- AC-8.6.1: Dart motion detected but no dart found after settling → ThrowMissEvent
- AC-8.6.2: Throw timeout (2 seconds): No dart detected → ThrowMissEvent, return to WaitForThrow
- AC-8.6.3: Miss event includes timestamp and motion data
- AC-8.6.4: System ready for next throw immediately after miss
- AC-8.6.5: Miss doesn't affect known dart positions or total count

### US-8.7: Event Model
**As a** developer  
**I want to** structured event models for all state transitions  
**So that** downstream systems can process events consistently

**Acceptance Criteria:**
- AC-8.7.1: DartHitEvent: timestamp, board_coordinates, score, camera_hits, image_paths
- AC-8.7.2: DartRemovedEvent: timestamp, count_removed, count_remaining
- AC-8.7.3: DartBounceOutEvent: timestamp, dart_position, time_on_board
- AC-8.7.4: ThrowMissEvent: timestamp, motion_data
- AC-8.7.5: All events JSON-serializable

## State Machine Diagram

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
```

## Configuration Parameters

```toml
[state_machine]
settled_timeout_ms = 500          # Wait for motion to settle
throw_timeout_ms = 2000           # Max time to detect dart after motion
pull_out_timeout_ms = 5000        # Max time for pull-out (longer for manual removal)

[motion_classification]
dart_speed_threshold_px_per_s = 500    # Minimum speed for dart throw
hand_speed_threshold_px_per_s = 200    # Maximum speed for hand
dart_size_threshold_px2 = 100          # Maximum size for dart (bounding box area)
hand_size_threshold_px2 = 500          # Minimum size for hand
dart_duration_threshold_ms = 200       # Maximum duration for dart motion
hand_duration_threshold_ms = 500       # Minimum duration for hand motion

[bounce_out_detection]
check_interval_ms = 1000          # How often to check for bounce-out
```

## Technical Constraints

- State machine must handle concurrent events (motion + timeout)
- Dart position tracking must account for 20-30px systematic error
- Periodic checks must not impact main loop performance
- State transitions must be logged for debugging
- System must recover gracefully from unexpected states

## Edge Cases

- **Rapid throws**: Second throw before first dart settled → queue in ThrowDetected state
- **Simultaneous pull-out**: All 3 darts removed at once → single DartRemovedEvent
- **Early pull-out**: Hand motion before 3 darts → transition to PullOutStarted from WaitForThrow
- **Camera blind spots**: Dart visible in 1/3 cameras → still detect (≥1 camera sufficient)
- **False motion**: Hand wave without throw → timeout, return to WaitForThrow
- **Bounce-out to 3 darts**: 2 detected + 1 bounce-out = 3 total → ThrowFinished

## Dependencies

- Step 7: Multi-camera fusion (dart detection)
- Step 3: Motion detection (impact and settling)
- Step 5: Background model (pre/post frames)
- Event model (dataclasses for all event types)

## Success Metrics

- State transitions: 100% correct for basic throw sequence
- Three-dart counting: Correctly transitions to ThrowFinished after 3 total darts
- Motion classification: >90% accuracy distinguishing dart throws from hand pull-outs
- Pull-out detection: Correctly detects when all darts removed in >95% of cases
- Bounce-out detection: Detects within 2 seconds of dart falling
- Miss detection: No false positives (motion without throw)
- Event completeness: All events have required fields populated

## Test Scenarios

- **TC8.1**: Basic throw → settle → pull-out
- **TC8.2**: Three consecutive darts → ThrowFinished → pull-out
- **TC8.3**: Early pull-out (remove 1 dart after throwing 1)
- **TC8.4**: Full pull-out (remove all 3 darts)
- **TC8.5**: Bounce-out (dart falls off, total reaches 3)
- **TC8.6**: Throw miss (dart motion but no dart)
- **TC8.7**: Hand motion classification (slow, large, sustained)
- **TC8.8**: Rapid throws (second throw before first settled)
