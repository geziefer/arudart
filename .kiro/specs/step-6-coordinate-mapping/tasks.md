# Implementation Plan: Step 6 - Coordinate Mapping (Manual Control Points)

## Overview

This implementation plan implements manual control point calibration for coordinate mapping. The user clicks 8-12 known points on the dartboard (bull, T20, D20, etc.), and the system computes a homography matrix that transforms camera pixels to board coordinates. This approach is simple, accurate, and proven in commercial systems like Autodarts.

The system projects a complete spiderweb overlay through the computed homography for visual validation, allowing iterative refinement until the overlay perfectly matches the board.

## Tasks

- [x] 1. Set up calibration module structure and configuration
  - Create `src/calibration/__init__.py` with module exports
  - Add calibration configuration section to `config.toml` (control points, thresholds)
  - Create `calibration/` directory for calibration JSON files
  - _Requirements: 3.5, 7.4_

- [x] 2. Implement FeatureDetector class (OPTIONAL - preserved for future automatic detection)
  - [x] 2.1-2.6 Complete (bull detection, ring detection, sector boundaries)
  - _Note: Not required for manual calibration, kept as optional enhancement_

- [x] 3. Checkpoint - Feature detection works (OPTIONAL)
  - Feature detection validated but not used for primary calibration
  - Manual control points are the primary calibration method

- [x] 4. Implement BoardGeometry class (NEW - PRIORITY)
  - [x] 4.1 Create `src/calibration/board_geometry.py`
    - Define Winmau Blade 6 dimensions as constants
    - Implement `get_control_point_coords()` returning standard control points
    - Implement `get_sector_angle()` for sector number → angle conversion
    - Implement `get_board_coords()` for any sector/ring combination
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  
  - [x] 4.2 Implement spiderweb projection
    - Implement `project_point()` to project board coords through homography
    - Implement `generate_spiderweb()` returning all wire/ring pixel coordinates
    - Generate 20 sector boundaries (radial lines from bull)
    - Generate 5 ring circles (bull, triple, single, double, outer)
    - _Requirements: 2.5, 2.6_
  
  - [x] 4.3 Write unit tests for BoardGeometry
    - Test control point coordinate accuracy
    - Test sector angle calculations
    - Test board coordinate computations
    - Test spiderweb generation completeness
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 5. Implement ManualCalibrator class (NEW - PRIORITY)
  - [x] 5.1 Create `src/calibration/manual_calibrator.py`
    - Implement `__init__()` with board geometry
    - Implement `calibrate()` returning list of (pixel, board) point pairs
    - Define standard control points (bull, T20, T5, T1, D20, D5, D1, etc.)
    - _Requirements: 1.1, 1.2, 1.3_
  
  - [x] 5.2 Implement interactive UI
    - Display camera image with control point labels
    - Capture mouse clicks for each control point
    - Show clicked points with labels
    - Allow point deletion/re-clicking
    - Require minimum 4 points (bull + 3 others)
    - _Requirements: 1.4, 1.5, 1.6_
  
  - [x] 5.3 Implement validation and refinement
    - Compute preliminary homography after 4+ points
    - Project spiderweb overlay for visual validation
    - Allow adding more points for refinement
    - Show reprojection error for each point
    - Highlight outlier points (error > 10px)
    - _Requirements: 1.7, 1.8, 1.9_
  
  - [x] 5.4 Write unit tests for ManualCalibrator
    - Test control point definition
    - Test point pair creation
    - Test minimum point validation
    - Test UI state management
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [ ] 6. Checkpoint - Manual calibration UI works
  - Test interactive point clicking
  - Verify spiderweb overlay projection
  - Validate point refinement workflow
  - Measure calibration time (should be < 5 minutes per camera)
  - Ask user if questions arise

- [-] 7. Implement HomographyCalculator class
  - [x] 7.1 Create `src/calibration/homography_calculator.py`
    - Implement `__init__()` with RANSAC configuration
    - Implement `compute()` using cv2.findHomography with RANSAC
    - Implement `verify()` to compute reprojection error
    - Implement `save()` and `load()` for JSON persistence
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  
  - [ ] 7.2 Write property test for serialization round-trip
    - **Property 4: Calibration Serialization Round-Trip**
    - Save homography to JSON, load back, verify numerical equivalence
    - **Validates: Requirements 3.5, 7.4**
  
  - [ ] 7.3 Write property test for reprojection error threshold
    - **Property 9: Reprojection Error Thresholds Met**
    - Verify computed homography has reprojection error < 5mm
    - **Validates: Requirements 3.3**

- [ ] 8. Checkpoint - Verify homography computation works
  - Run full pipeline: click points → compute homography → project spiderweb
  - Verify homography is non-degenerate
  - Verify reprojection error < 5mm
  - Save homography to JSON and verify file format
  - Test with all 3 cameras
  - Ask user if questions arise

- [-] 9. Implement CoordinateMapper class
  - [x] 9.1 Create `src/calibration/coordinate_mapper.py`
    - Implement `__init__()` to load intrinsic and homography from JSON
    - Implement `map_to_board()` with undistortion and homography
    - Implement `map_to_image()` for inverse transformation
    - Implement `is_calibrated()` and `reload_calibration()`
    - Add threading.Lock for thread safety
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_
  
  - [ ] 9.2 Write property test for homography round-trip
    - **Property 3: Homography Round-Trip Consistency**
    - For any board coordinate, map_to_image then map_to_board should return original (±1mm)
    - **Validates: Requirements 4.4, 4.7**
  
  - [ ] 9.3 Write property test for bounds checking
    - **Property 5: Bounds Checking Returns None for Out-of-Bounds**
    - For pixels mapping to radius > 200mm, map_to_board should return None
    - **Validates: Requirements 4.6**
  
  - [ ] 9.4 Write property test for thread safety
    - **Property 8: Thread Safety Under Concurrent Access**
    - Concurrent calls from multiple threads should complete without corruption
    - **Validates: Requirements 4.8**
  
  - [x] 9.5 Write unit tests for CoordinateMapper
    - Test loading valid calibration files
    - Test handling missing calibration files gracefully
    - Test coordinate system convention (origin, axes)
    - Test reload_calibration() functionality
    - _Requirements: 4.1, 4.5_

- [ ] 10. Implement CalibrationManager class
  - [ ] 10.1 Create `src/calibration/calibration_manager.py`
    - Implement `__init__()` with component dependencies
    - Implement state machine: ready, calibrating, error
    - Implement `get_status()` returning CalibrationStatus
    - _Requirements: 5.5, 6.1, 6.5_
  
  - [ ] 10.2 Implement full calibration workflow
    - Implement `run_full_calibration()` orchestrating manual calibration
    - Handle calibration failures with retry logic
    - _Requirements: 5.1, 6.6_
  
  - [ ] 10.3 Implement lightweight validation
    - Implement `run_lightweight_validation()` checking bull center only
    - Compute drift as distance from expected (0, 0)
    - _Requirements: 5.2, 5.3_
  
  - [ ] 10.4 Implement drift detection and recalibration
    - Implement `check_and_recalibrate()` triggering recalibration on drift > 3mm
    - Track consecutive failures, enter error state after 3
    - _Requirements: 5.3, 5.4, 6.6_
  
  - [ ] 10.5 Write property test for drift detection
    - **Property 6: Drift Detection Triggers Recalibration**
    - For drift > 3mm, state should transition to "calibrating"
    - **Validates: Requirements 5.3**
  
  - [ ] 10.6 Write property test for state machine transitions
    - **Property 7: State Machine Transitions Are Valid**
    - Verify only valid state transitions occur
    - After 3 failures, state should be "error"
    - **Validates: Requirements 6.1, 6.6**

- [ ] 11. Checkpoint - Verify calibration manager works
  - Test full calibration workflow on real camera
  - Test lightweight validation detects drift
  - Test state transitions: ready → calibrating → ready
  - Test failure handling: 3 failures → error state
  - Ask user if questions arise

- [ ] 12. Implement intrinsic calibration script (preserved from original)
  - [ ] 12.1 Create `src/calibration/intrinsic_calibrator.py`
    - Implement chessboard image capture with interactive UI
    - Implement calibration using cv2.calibrateCamera
    - Implement save to JSON format
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  
  - [ ] 12.2 Create `calibration/calibrate_intrinsic.py` script
    - Interactive camera capture with live preview
    - Chessboard detection overlay
    - Capture 20-30 images at different angles
    - Display reprojection error and save results
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 13. Implement manual calibration script (PRIMARY)
  - [x] 13.1 Create `calibration/calibrate_manual.py` script
    - Initialize cameras and capture frames
    - Run ManualCalibrator for each camera
    - Display control point labels and capture clicks
    - Compute homography and show spiderweb overlay
    - Allow refinement and re-calibration
    - Save homography to JSON
    - Display summary with reprojection errors
    - _Requirements: 1.1-1.9, 2.1-2.8, 3.1-3.5_

- [ ] 14. Implement calibration verification script
  - [ ] 14.1 Create `calibration/verify_calibration.py` script
    - Interactive UI for clicking test points (T20, D20, bull, etc.)
    - Transform clicked pixels to board coordinates
    - Compute error vs known ground truth
    - Display error statistics and save verification report
    - Show spiderweb overlay for visual validation
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  
  - [ ] 14.2 Write property test for error computation
    - **Property 9 (continued): Verification error computation**
    - Verify average error calculation is correct
    - **Validates: Requirements 8.3, 8.4**

- [ ] 15. Integrate coordinate mapper into main.py
  - [ ] 15.1 Add CoordinateMapper initialization
    - Import CoordinateMapper and CalibrationManager
    - Initialize after camera manager setup
    - Check which cameras are calibrated
    - Log warning if no cameras calibrated
    - _Requirements: 4.1, 5.1_
  
  - [ ] 15.2 Add coordinate transformation to dart detection loop
    - After dart detection, transform pixel to board coordinates
    - Store both pixel and board coordinates in detection results
    - Log board coordinates for each detection
    - Handle cameras without calibration gracefully
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6_
  
  - [ ] 15.3 Add calibration state checking
    - Check CalibrationManager status before processing throws
    - Skip scoring when state is "calibrating"
    - Log when calibration state changes
    - _Requirements: 6.2, 6.3_
  
  - [ ] 15.4 Add command-line flags for calibration
    - Add `--calibrate` flag to run manual calibration at startup
    - Add `--calibrate-intrinsic` flag to run intrinsic calibration
    - Add `--verify-calibration` flag to run verification script
    - _Requirements: 5.1, 7.1, 8.1_
  
  - [ ] 15.5 Add keyboard shortcut for runtime calibration
    - Add 'c' key handler to trigger manual calibration in dev mode
    - Run calibration for all cameras
    - Reload coordinate mapper after calibration
    - _Requirements: 5.4_

- [ ] 16. Add calibration visualization for debugging
  - [ ] 16.1 Implement calibration visualization overlay
    - Draw spiderweb overlay (all sector boundaries and rings)
    - Draw control points with labels
    - Draw reprojection error vectors
    - Show calibration status and metrics
    - Add toggle with 'v' key in dev mode
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.9_

- [ ] 17. Final checkpoint - End-to-end testing
  - Run full calibration workflow (intrinsic + manual)
  - Verify coordinate transformation in main.py
  - Test with actual dart throws
  - Verify multi-camera detections produce consistent board coordinates
  - Run verification script to measure accuracy (< 5mm average error)
  - Test continuous calibration: drift detection and recalibration
  - Verify manual calibration works from all camera angles
  - Ensure all tests pass
  - Ask user if questions arise

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- Integration happens incrementally to catch errors early
- **Manual control point calibration is the PRIMARY method** - simple, accurate, proven
- Automatic feature detection (FeatureDetector, FeatureMatcher) preserved as OPTIONAL enhancement
- Intrinsic calibration (chessboard) handles lens distortion - camera-specific, one-time setup
- Manual calibration should take < 5 minutes per camera
- Spiderweb overlay provides immediate visual feedback for calibration quality
