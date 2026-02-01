# Step 8: Event State Machine (Throw vs Pull-Out)

## Overview

Implement a state machine to recognize the complete dart throw sequence: idle → throw in progress → dart present → pull-out → idle. This handles all real-game scenarios including multiple darts, bounce-outs, misses, and partial pull-outs.

## User Stories

### US-8.1: Basic Throw Sequence
**As a** system  
**I want to** recognize the complete throw sequence from idle to dart present  
**So that** I can emit a DartHitEvent at the correct time

**Acceptance Criteria:**
- AC-8.1.1: State transitions: Idle → ThrowInProgress (motion detected) → DartPresent (dart detected)
- AC-8.1.2: DartHitEvent emitted when transitioning to DartPresent
- AC-8.1.3: System waits for motion to settle before detecting dart (0.5s continuous low motion)
- AC-8.1.4: Throw timeout: If no dart detected after 2 seconds, return to Idle
- AC-8.1.5: System handles camera vibration from dart impact (waits for settling)

### US-8.2: Multiple Darts Tracking
**As a** system  
**I want to** track multiple darts on the board (up to 3)  
**So that** I can distinguish new darts from existing darts

**Acceptance Criteria:**
- AC-8.2.1: System maintains list of known dart positions after each detection
- AC-8.2.2: New dart detected if position >30px from all known darts
- AC-8.2.3: Moved dart ignored if position <30px from known dart (e.g., 3rd dart pushes 1st/2nd)
- AC-8.2.4: System tracks dart count (0-3 darts on board)
- AC-8.2.5: Known positions cleared on full pull-out (transition to Idle)

### US-8.3: Pull-Out Detection
**As a** system  
**I want to** detect when darts are removed from the board  
**So that** I can emit DartRemovedEvent and reset for next throw

**Acceptance Criteria:**
- AC-8.3.1: State transitions: DartPresent → PullOutInProgress (motion near darts) → Idle or DartPresent
- AC-8.3.2: Motion near darts: motion detected within 100px of any known dart position
- AC-8.3.3: Full pull-out: All darts removed → transition to Idle, emit DartRemovedEvent
- AC-8.3.4: Partial pull-out: Some darts remain → stay in DartPresent, emit DartRemovedEvent with count
- AC-8.3.5: False alarm: Motion stops but darts unchanged → return to DartPresent

### US-8.4: Bounce-Out Detection
**As a** system  
**I want to** detect when a dart falls off the board without pull-out motion  
**So that** I can update game state correctly

**Acceptance Criteria:**
- AC-8.4.1: Periodic dart presence check every 1 second while in DartPresent state
- AC-8.4.2: Re-detect all darts and compare with known positions
- AC-8.4.3: If dart disappeared: emit DartBounceOutEvent, update known positions
- AC-8.4.4: If all darts gone: transition to Idle
- AC-8.4.5: Bounce-out distinguished from pull-out by lack of motion

### US-8.5: Throw Miss Detection
**As a** system  
**I want to** detect when a throw misses the board  
**So that** I can log the miss and continue gameplay

**Acceptance Criteria:**
- AC-8.5.1: Motion detected but no dart found after settling → ThrowMissEvent
- AC-8.5.2: Throw timeout (2 seconds): No dart detected → ThrowMissEvent, return to previous state
- AC-8.5.3: Miss event includes timestamp and motion data
- AC-8.5.4: System ready for next throw immediately after miss
- AC-8.5.5: Miss doesn't affect known dart positions

### US-8.6: Event Model
**As a** developer  
**I want to** structured event models for all state transitions  
**So that** downstream systems can process events consistently

**Acceptance Criteria:**
- AC-8.6.1: DartHitEvent: timestamp, board_coordinates, score, camera_hits, image_paths
- AC-8.6.2: DartRemovedEvent: timestamp, count_removed, count_remaining
- AC-8.6.3: DartBounceOutEvent: timestamp, dart_position, time_on_board
- AC-8.6.4: ThrowMissEvent: timestamp, motion_data
- AC-8.6.5: All events JSON-serializable

## State Machine Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ┌──────┐  motion   ┌──────────────────┐  dart detected   │
│  │ Idle │─────────→ │ ThrowInProgress  │─────────────────┐ │
│  └──────┘           └──────────────────┘                 │ │
│     ↑                      │                             │ │
│     │ all darts removed    │ timeout / no dart          │ │
│     │                      ↓                             ↓ │
│  ┌──────────────────┐   ┌──────┐                  ┌────────────┐
│  │ PullOutInProgress│←──│ Idle │                  │DartPresent │
│  └──────────────────┘   └──────┘                  └────────────┘
│           ↑                                              │
│           │ motion near darts                            │
│           └──────────────────────────────────────────────┘
│                                                             │
│  Periodic check (1s): dart disappeared → DartBounceOutEvent│
└─────────────────────────────────────────────────────────────┘
```

## Configuration Parameters

```toml
[state_machine]
settled_timeout_ms = 500          # Wait for motion to settle
pull_out_motion_threshold = 15    # Motion threshold for pull-out
pull_out_timeout_ms = 2000        # Max time for pull-out
dart_movement_threshold_px = 30   # Distance to consider dart "moved" vs "new"
throw_timeout_ms = 2000           # Max time to detect dart after motion
dart_presence_check_interval_ms = 1000  # How often to check for bounce-out
motion_near_dart_radius_px = 100  # Distance to consider motion "near" dart
```

## Technical Constraints

- State machine must handle concurrent events (motion + timeout)
- Dart position tracking must account for 20-30px systematic error
- Periodic checks must not impact main loop performance
- State transitions must be logged for debugging
- System must recover gracefully from unexpected states

## Edge Cases

- **Rapid throws**: Second throw before first dart detected → queue throws
- **Simultaneous pull-out**: All 3 darts removed at once → single DartRemovedEvent
- **Dart pushed by impact**: 3rd dart pushes 1st/2nd → ignore moved darts, detect only new
- **Camera blind spots**: Dart visible in 1/3 cameras → still detect (≥1 camera sufficient)
- **False motion**: Hand wave without throw → timeout, return to previous state

## Dependencies

- Step 7: Multi-camera fusion (dart detection)
- Step 3: Motion detection (impact and settling)
- Step 5: Background model (pre/post frames)
- Event model (dataclasses for all event types)

## Success Metrics

- State transitions: 100% correct for basic throw sequence
- Multiple darts: Correctly distinguishes new vs moved darts in >95% of cases
- Pull-out detection: Correctly detects full vs partial pull-out in >90% of cases
- Bounce-out detection: Detects within 2 seconds of dart falling
- Miss detection: No false positives (motion without throw)
- Event completeness: All events have required fields populated

## Test Scenarios

- **TC8.1**: Basic throw → settle → pull-out
- **TC8.2**: Three consecutive darts (no pull-out between)
- **TC8.3**: Partial pull-out (remove 1 of 3 darts)
- **TC8.4**: Full pull-out (remove all 3 darts)
- **TC8.5**: Bounce-out (dart falls off during game)
- **TC8.6**: Throw miss (motion but no dart)
- **TC8.7**: "180 scenario" (3 darts in T20, 3rd pushes 1st/2nd)
- **TC8.8**: Rapid throws (second throw before first settled)
