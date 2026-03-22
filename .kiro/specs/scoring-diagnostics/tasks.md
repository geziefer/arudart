# Implementation Plan: Scoring Diagnostics

## Overview

Implement diagnostic logging and accuracy testing for the ARU-DART scoring pipeline. The work proceeds bottom-up: data models first, then persistence, then known positions, then accuracy test orchestration, then CLI integration. Each step builds on the previous and ends with wiring into main.py.

## Tasks

- [ ] 1. Create diagnostics package with DetectionRecord and CameraDiagnostic data models
  - [ ] 1.1 Create `src/diagnostics/__init__.py` and `src/diagnostics/detection_record.py`
    - Define `CameraDiagnostic` dataclass with fields: camera_id, pixel_x, pixel_y, board_x, board_y, confidence, deviation_mm, deviation_dx, deviation_dy
    - Define `DetectionRecord` dataclass with fields: timestamp, board_x, board_y, radius, angle_deg, ring, sector, score_total, score_base, score_multiplier, fusion_confidence, cameras_used, camera_data (list of CameraDiagnostic), image_paths
    - Implement `to_dict()` and `from_dict()` for JSON round-trip on both dataclasses
    - Implement `from_dart_hit_event(event: DartHitEvent) -> DetectionRecord` factory that computes camera deviations: dx = camera.board_x - event.board_x, dy = camera.board_y - event.board_y, deviation_mm = sqrt(dx^2 + dy^2)
    - Export `DetectionRecord` and `CameraDiagnostic` from `__init__.py`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 7.1, 7.2_

  - [ ]* 1.2 Write property test: DetectionRecord preserves DartHitEvent fields
    - **Property 1: DetectionRecord preserves DartHitEvent fields**
    - Generate random DartHitEvent objects (random coords, scores, 1-3 camera detections), create DetectionRecord via from_dart_hit_event(), verify all fields match source event
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [ ]* 1.3 Write property test: DetectionRecord JSON round-trip
    - **Property 2: DetectionRecord JSON round-trip**
    - Generate random DetectionRecord objects, serialize with to_dict(), deserialize with from_dict(), verify equivalence within float tolerance
    - **Validates: Requirements 1.4, 1.5**

  - [ ]* 1.4 Write property test: Camera deviation vector consistency
    - **Property 3: Camera deviation vector consistency**
    - Generate random fused positions and camera board positions, create DetectionRecord, verify deviation_mm == sqrt(dx^2 + dy^2) and dx/dy match camera.board - fused
    - **Validates: Requirements 7.1, 7.2**

- [ ] 2. Implement DiagnosticLogger for session management and persistence
  - [ ] 2.1 Create `src/diagnostics/diagnostic_logger.py`
    - Implement `DiagnosticLogger.__init__(base_dir="data/diagnostics")`: create session directory `Session_NNN_YYYY-MM-DD_HH-MM-SS`, initialize throw_count=0 and records list
    - Implement `log_detection(event: DartHitEvent) -> DetectionRecord`: create DetectionRecord from event, increment throw_count, write `throw_NNN_HH-MM-SS.json`, copy annotated images into session dir (warn and skip if missing), append to records
    - Implement `write_session_summary()`: compute total_throws, successful_detections (non-zero cameras_used), average_fusion_confidence, per-camera aggregate stats (mean/max deviation, mean deviation vector dx/dy), write `session_summary.json`
    - Expose `session_dir` as read-only property
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 7.3_

  - [ ]* 2.2 Write property test: Session summary aggregation correctness
    - **Property 4: Session summary aggregation correctness**
    - Generate random sequences of DetectionRecord objects, feed to DiagnosticLogger, verify session summary total_throws, successful_detections, average_fusion_confidence, and per-camera mean/max deviation match manual computation
    - **Validates: Requirements 2.4, 7.3**

- [ ] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement KnownPosition catalog and BoardGeometry integration
  - [ ] 4.1 Create `src/diagnostics/known_positions.py`
    - Define `KnownPosition` dataclass with fields: name, expected_x, expected_y, expected_ring, expected_sector (int|None), expected_score
    - Implement `build_known_positions(board_geometry: BoardGeometry) -> list[KnownPosition]` that computes all 14 required positions:
      - DB: (0, 0), ring="bull", sector=None, score=50
      - SB: single bull midpoint radius at 90° via board_geometry.get_sector_angle(20), ring="single_bull", sector=None, score=25
      - T20, T1, T5: use board_geometry.get_board_coords(sector, "triple"), score = sector * 3
      - D20, D1, D5: use board_geometry.get_board_coords(sector, "double"), score = sector * 2
      - BS20, BS1, BS5: use board_geometry.get_board_coords(sector, "single"), score = sector
      - SS20, SS1, SS5: compute radius = (single_bull_radius + triple_inner) / 2 at sector angle from board_geometry.get_sector_angle(sector), score = sector
    - Implement helper `compute_angular_error(a_deg, b_deg) -> float` returning min(|a-b|, 360-|a-b|), always in [0, 180]
    - Implement helper `compute_position_error(x1, y1, x2, y2) -> float` returning Euclidean distance
    - _Requirements: 4.1, 4.2, 4.3, 5.4, 5.5_

  - [ ]* 4.2 Write property test: Known position coordinates match BoardGeometry
    - **Property 5: Known position coordinates match BoardGeometry**
    - For each known position with a sector, verify coordinates match board_geometry.get_board_coords() or the small-single formula
    - **Validates: Requirements 4.2, 4.3**

  - [ ]* 4.3 Write property test: Position error is Euclidean distance
    - **Property 6: Position error is Euclidean distance**
    - Generate random pairs of board coordinates, verify compute_position_error matches sqrt((x1-x2)^2 + (y1-y2)^2)
    - **Validates: Requirements 5.4**

  - [ ]* 4.4 Write property test: Angular error handles wraparound
    - **Property 7: Angular error handles wraparound**
    - Generate random pairs of angles in [0, 360), verify compute_angular_error equals min(|a-b|, 360-|a-b|) and result is in [0, 180]
    - **Validates: Requirements 5.5**

- [ ] 5. Implement TestReport and TestReportGenerator
  - [ ] 5.1 Create `src/diagnostics/test_report.py`
    - Define `TestReport` dataclass with fields: session_dir, overall (total_throws, sector_match_rate, ring_match_rate, score_match_rate, mean_position_error_mm, max_position_error_mm), per_throw (list of dicts with target_name, expected_score, detected_score, position_error_mm, angular_error_deg, ring_match, sector_match), per_camera (dict of camera_id to mean/max deviation)
    - Implement `to_dict()` and `from_dict()` for JSON round-trip
    - Implement `print_summary()` for human-readable console output (ASCII only, no unicode)
    - Implement `TestReportGenerator.generate_report(results, diagnostic_logger) -> TestReport` that aggregates per-throw results into overall metrics: sector/ring/score match rates as percentages, mean/max position error, per-camera mean/max deviation
    - Handle zero-throw edge case (no division by zero, report N/A or 0)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 5.2 Write property test: Report metric aggregation correctness
    - **Property 8: Report metric aggregation correctness**
    - Generate random lists of per-throw accuracy results (random match booleans, position errors), verify report metrics match manual aggregation
    - **Validates: Requirements 6.2, 6.3, 6.4**

  - [ ]* 5.3 Write property test: TestReport JSON round-trip
    - **Property 9: TestReport JSON round-trip**
    - Generate random TestReport objects, round-trip through to_dict()/from_dict(), verify equivalence within float tolerance
    - **Validates: Requirements 6.6**

- [ ] 6. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement AccuracyTestRunner
  - [ ] 7.1 Create `src/diagnostics/accuracy_test_runner.py`
    - Implement `AccuracyTestRunner.__init__(known_positions, diagnostic_logger, score_calculator)`: store positions list, set current_index=0, initialize results list
    - Implement `get_current_target() -> KnownPosition | None`: return current position or None if complete
    - Implement `record_result(event: DartHitEvent)`: log detection via diagnostic_logger, compute position_error (Euclidean), angular_error (wraparound-safe), ring_match, sector_match, score_match against current target, append to results, advance current_index
    - Implement `is_complete() -> bool`
    - Implement `generate_report() -> TestReport` using TestReportGenerator
    - Support optional position filtering (subset selection) via constructor parameter
    - _Requirements: 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1_

  - [ ]* 7.2 Write unit tests for AccuracyTestRunner
    - Test record_result with a known DartHitEvent and known target, verify position_error, angular_error, ring_match, sector_match, score_match
    - Test is_complete transitions correctly
    - Test generate_report produces valid TestReport
    - _Requirements: 5.4, 5.5, 5.6_

- [ ] 8. Integrate CLI flags and wire into main.py
  - [ ] 8.1 Add `--diagnostics` and `--accuracy-test` CLI flags to argparse in main.py
    - `--diagnostics`: add-on flag, store_true
    - `--accuracy-test`: standalone flag, store_true
    - Validate: `--diagnostics` without `--manual-dart-test` or `--single-dart-test` prints error and exits
    - `--accuracy-test` implies diagnostics
    - _Requirements: 3.1, 3.4, 5.1_

  - [ ] 8.2 Wire DiagnosticLogger into existing test modes
    - When `--diagnostics` is active: instantiate DiagnosticLogger, print session_dir at startup
    - After each `score_calculator.process_detections()` that returns a DartHitEvent, call `diagnostic_logger.log_detection(event)`
    - On exit (finally block), call `diagnostic_logger.write_session_summary()`
    - Wire into both `run_manual_dart_test` and `run_single_dart_test` by passing diagnostic_logger as optional parameter
    - _Requirements: 3.1, 3.2, 3.3, 2.1, 2.2, 2.3_

  - [ ] 8.3 Wire AccuracyTestRunner into main.py as `--accuracy-test` mode
    - When `--accuracy-test`: instantiate BoardGeometry, build known positions, create DiagnosticLogger, create AccuracyTestRunner
    - Reuse the manual-dart-test state machine (stabilize -> placing -> detecting -> result -> removing)
    - Display current target name on camera windows during placing state (e.g., "Place dart at: T20")
    - Display comparison results during result state: expected score, detected score, position error, ring/sector match
    - On completion or quit: generate report, write to session dir, print summary to console, write session summary
    - _Requirements: 5.1, 5.2, 5.3, 5.7, 6.1, 6.5_

- [ ] 9. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use the `hypothesis` library with `@settings(max_examples=100)`
- All property tests go in `tests/test_scoring_diagnostics_properties.py`, unit tests in `tests/test_scoring_diagnostics.py`
- Pre-existing test failures in test_feature_detector, test_feature_matcher, test_feature_matcher_properties, test_bull_center_integration, test_feature_detector_real_images are NOT caused by this feature
- OpenCV text rendering: ASCII only, no unicode characters
