# Implementation Plan: Step 8 - Event State Machine

## Overview

Implement a state machine to manage the complete dart throw lifecycle with 3-dart counting, dart/hand motion classification, and comprehensive event emission. The state machine replaces the simple motion state tracking in main.py with a robust, event-driven architecture.

## Tasks

- [x] 1. Create event dataclasses and state enum
  - Create `src/state_machine/events.py` with DartRemovedEvent, DartBounceOutEvent, ThrowMissEvent dataclasses
  - Create State enum (WaitForThrow, ThrowDetected, ThrowFinished, PullOutStarted)
  - Add to_dict() methods for JSON serialization
  - DartHitEvent already exists from Step 7
  - _Requirements: AC-8.7.1, AC-8.7.2, AC-8.7.3, AC-8.7.4, AC-8.7.5_

- [x] 2. Implement DartTracker class
  - [x] 2.1 Create `src/state_machine/dart_tracker.py` with DartTracker class
    - Implement add_dart(), remove_dart(), increment_bounce_out_count()
    - Implement get_total_dart_count(), get_detected_dart_count(), get_bounce_out_count()
    - Implement get_known_positions(), clear_all(), is_at_capacity()
    - Track known_darts dictionary and bounce_out_count
    - _Requirements: AC-8.2.1, AC-8.2.2, AC-8.2.3_
  
  - [x] 2.2 Write property test for dart count invariant
    - **Property 4: Dart Count Invariant**
    - **Validates: Requirements AC-8.2.1, AC-8.2.4**
    - For any sequence of add/remove operations, count should equal length of known positions
    - Test with random sequences of operations
  
  - [x] 2.3 Write unit tests for DartTracker
    - Test add_dart() increments count correctly
    - Test remove_dart() decrements count correctly
    - Test bounce_out_count increments correctly
    - Test total_count = detected + bounced_out
    - Test is_at_capacity() returns true at 3 darts
    - Test clear_all() resets all state
    - _Requirements: AC-8.2.1, AC-8.2.2, AC-8.2.3, AC-8.2.4_

- [x] 3. Implement MotionClassifier class
  - [x] 3.1 Create `src/state_machine/motion_classifier.py` with MotionClassifier class
    - Implement classify_motion() returning MotionType enum (DART or HAND)
    - Implement compute_motion_speed(), compute_motion_size(), compute_motion_duration()
    - Apply classification rules based on speed/size/duration thresholds
    - Handle UNKNOWN motion type (log warning, default to DART)
    - _Requirements: AC-8.3.1, AC-8.3.2, AC-8.3.3_
  
  - [x] 3.2 Write property test for motion classification
    - **Property: Motion Classification Correctness**
    - **Validates: Requirements AC-8.3.1, AC-8.3.2**
    - For any motion with speed >500, size <100, duration <200 → DART
    - For any motion with speed <200, size >500, duration >500 → HAND
    - Test with random motion parameters
  
  - [x] 3.3 Write unit tests for MotionClassifier
    - Test dart motion classification (fast, small, brief)
    - Test hand motion classification (slow, large, sustained)
    - Test boundary cases (exactly at thresholds)
    - Test UNKNOWN motion handling
    - _Requirements: AC-8.3.1, AC-8.3.2, AC-8.3.3_

- [x] 4. Implement ThrowStateMachine class (core logic)
  - [x] 4.1 Create `src/state_machine/throw_state_machine.py` with ThrowStateMachine class
    - Initialize with dart_tracker, motion_classifier, dart_detectors, score_calculator
    - Implement process() method as main entry point
    - Track current_state, state_entry_time, last_periodic_check
    - _Requirements: AC-8.1.1, AC-8.2.2_
  
  - [x] 4.2 Implement handle_wait_for_throw() method
    - Handle dart motion → transition to ThrowDetected
    - Handle hand motion → transition to PullOutStarted
    - Implement periodic bounce-out check (every 1 second)
    - Transition to ThrowFinished if total_count reaches 3
    - _Requirements: AC-8.1.1, AC-8.3.4, AC-8.3.5, AC-8.5.1, AC-8.5.4_
  
  - [x] 4.3 Implement handle_throw_detected() method
    - Wait for motion to settle (0.5s continuous low motion)
    - Run dart detection on all cameras
    - Add detected dart to tracker, emit DartHitEvent
    - Transition to WaitForThrow if count < 3, ThrowFinished if count == 3
    - Handle timeout (2 seconds) → emit ThrowMissEvent
    - _Requirements: AC-8.1.1, AC-8.1.2, AC-8.1.3, AC-8.1.4, AC-8.2.2, AC-8.6.1, AC-8.6.2_
  
  - [x] 4.4 Implement handle_throw_finished() method
    - Handle hand motion → transition to PullOutStarted
    - Implement periodic bounce-out check (same as WaitForThrow)
    - _Requirements: AC-8.2.4, AC-8.2.5, AC-8.3.5, AC-8.5.1_
  
  - [x] 4.5 Implement handle_pull_out_started() method
    - Wait for motion to settle
    - Re-detect darts, compare with known positions
    - Remove missing darts, emit DartRemovedEvent
    - Transition to WaitForThrow if all darts removed
    - Stay in PullOutStarted if darts remain
    - Handle timeout (5 seconds) → log warning, stay in state
    - _Requirements: AC-8.4.1, AC-8.4.2, AC-8.4.3, AC-8.4.4, AC-8.4.5, AC-8.4.6_
  
  - [x] 4.6 Write property test for state transition correctness
    - **Property 1: State Transition Correctness**
    - **Validates: Requirements AC-8.1.1, AC-8.3.1**
    - For any valid sequence of motion/detection events, verify state transitions follow diagram
    - Test all valid paths through state machine
    - Generate random event sequences
  
  - [x] 4.7 Write unit tests for state machine
    - Test TC8.1: Basic throw sequence (WaitForThrow → ThrowDetected → WaitForThrow)
    - Test TC8.2: Three consecutive darts (WaitForThrow → ThrowFinished)
    - Test TC8.4: Full pull-out (ThrowFinished → PullOutStarted → WaitForThrow)
    - Test TC8.5: Bounce-out detection (periodic check finds missing dart)
    - Test TC8.6: Throw miss (timeout, no dart detected)
    - Test TC8.7: Hand motion classification
    - Test TC8.8: Rapid throws
    - _Requirements: All acceptance criteria_

- [x] 5. Add configuration to config.toml
  - Add [state_machine] section with timeouts
  - Add [motion_classification] section with thresholds
  - Add [bounce_out_detection] section with check interval
  - _Requirements: Configuration Parameters_

- [x] 6. Integrate state machine into main.py
  - [x] 6.1 Replace simple motion state tracking with ThrowStateMachine
    - Initialize ThrowStateMachine with required components
    - Call state_machine.process() in main loop
    - Remove old motion_state variable and manual transitions
    - _Requirements: Integration Notes_
  
  - [x] 6.2 Implement event handling
    - Handle DartHitEvent: log score, save event to disk
    - Handle DartRemovedEvent: log removal count
    - Handle DartBounceOutEvent: log bounce-out
    - Handle ThrowMissEvent: log miss
    - _Requirements: AC-8.7.1, AC-8.7.2, AC-8.7.3, AC-8.7.4_
  
  - [x] 6.3 Write integration tests
    - Test complete throw sequence end-to-end
    - Test event emission and handling
    - Test state machine integration with existing components
    - _Requirements: All acceptance criteria_

- [x] 7. Checkpoint - Ensure all tests pass
  - Run all unit tests and property tests
  - Verify state machine behavior with manual testing
  - Test motion classification accuracy
  - Ensure all events are emitted correctly
  - Ask the user if questions arise

## Notes

- Each task references specific requirements for traceability
- Property tests validate universal correctness properties
- Unit tests validate specific scenarios and edge cases
- Integration tests ensure state machine works with existing system
- Motion classification thresholds may need tuning based on real-world testing
