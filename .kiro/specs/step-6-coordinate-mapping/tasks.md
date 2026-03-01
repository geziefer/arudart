# Implementation Plan: Step 6 - Coordinate Mapping (Spiderweb-Based)

## Overview

This implementation plan breaks down the color-based coordinate mapping system into discrete coding tasks. The system uses the dartboard's natural color patterns (black/white singles, red/green rings) as calibration reference points, which is more reliable than detecting thin wires. Each camera gets its own homography computed from features visible in its perspective.

## Tasks

- [x] 1. Set up calibration module structure and configuration
  - Create `src/calibration/__init__.py` with module exports
  - Add calibration configuration section to `config.toml` (feature detection params, thresholds)
  - Create `calibration/` directory for calibration JSON files
  - _Requirements: 3.5, 7.4_

- [ ] 2. Implement FeatureDetector class
  - [x] 2.1 Create `src/calibration/feature_detector.py` with basic structure
    - Implement `__init__()` with config loading (including HSV color ranges)
    - Implement `detect()` returning FeatureDetectionResult dataclass
    - Define SectorBoundary and BoundaryIntersection dataclasses
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  
  - [x] 2.2 Implement bull center detection
    - Convert to HSV color space
    - Create masks for bull colors (red for double bull, green for single bull)
    - Apply morphological operations to clean mask
    - Find contours and fit ellipse (handles perspective distortion)
    - Select best ellipse by circularity and position
    - _Requirements: 1.1, 1.7_
  
  - [x] 2.3 Implement ring edge detection
    - Apply Canny edge detection
    - Create annular masks around expected ring radii
    - Fit ellipses to edge points using cv2.fitEllipse
    - Sample points along fitted ellipses
    - _Requirements: 1.2, 1.3_
  
  - [x] 2.4 Implement sector boundary detection using color segmentation
    - Convert to HSV color space
    - Create masks for black/white singles (low/high value, low saturation)
    - Create masks for red/green rings (hue-based)
    - Find color transition points (black→white, red→green)
    - Cluster transition points by angle from bull center (18° sectors)
    - Fit lines through clusters to get sector boundaries
    - Assign sector numbers based on alternating color pattern
    - _Requirements: 1.4, 1.5, 1.9_
  
  - [x] 2.5 Implement boundary-ring intersection finding
    - Compute intersections between sector boundaries (angles) and ring ellipses
    - Associate intersections with sector number and ring type
    - Store confidence scores from color detection
    - _Requirements: 1.6, 1.8_
  
  - [x] 2.6 Write unit tests for FeatureDetector
    - Test bull detection with synthetic dartboard images (colored bull)
    - Test ring detection with known ellipse geometry
    - Test color segmentation with synthetic black/white/red/green patterns
    - Test sector boundary detection with known color transitions
    - Test error handling for missing features
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

- [x] 3. Checkpoint - Verify feature detection works
  - Test FeatureDetector on real camera images
  - Verify bull center detection accuracy (ellipse-based)
  - Verify ring edge detection coverage
  - Verify sector boundary detection count (≥8 in good view region)
  - Verify color segmentation works across all cameras (including angled cam2)
  - Ask user if questions arise

- [ ] 4. Implement FeatureMatcher class
  - [x] 4.1 Create `src/calibration/feature_matcher.py`
    - Implement `__init__()` with board geometry constants
    - Implement `match()` returning list of (pixel, board, confidence) tuples
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.8_
  
  - [x] 4.2 Implement sector 20 identification
    - Find sector boundary closest to vertical (pointing up from bull)
    - Use color pattern to confirm sector 20 (boundary between sectors 5 and 20)
    - Weight by confidence from color detection
    - _Requirements: 2.4_
  
  - [x] 4.3 Implement sector boundary assignment
    - Sector numbers already assigned during color detection (alternating pattern)
    - Verify sector assignments relative to sector 20 boundary
    - Use known sector order: 20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5
    - _Requirements: 2.4, 2.5, 2.8_
  
  - [x] 4.4 Implement board coordinate computation
    - Map bull center to (0, 0)
    - Map ring edge points to known radii (170mm, 107mm)
    - Map boundary intersections using radius and sector angle
    - Include confidence weights from color detection
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.8_
  
  - [x] 4.5 Write property test for bull center mapping
    - **Property 1: Bull Center Maps to Origin**
    - For any detected bull center, matched board coordinate should be (0, 0)
    - **Validates: Requirements 2.1**
  
  - [x] 4.6 Write property test for ring radius mapping
    - **Property 2: Ring Points Map to Correct Radius**
    - For any double ring point, radius should be 170mm (±1mm)
    - For any triple ring point, radius should be 107mm (±1mm)
    - **Validates: Requirements 2.2, 2.3**

- [ ] 5. Implement HomographyCalculator class
  - [ ] 5.1 Create `src/calibration/homography_calculator.py`
    - Implement `__init__()` with RANSAC configuration
    - Implement `compute()` using cv2.findHomography with RANSAC
    - Implement `verify()` to compute reprojection error
    - Implement `save()` and `load()` for JSON persistence
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  
  - [ ] 5.2 Write property test for serialization round-trip
    - **Property 4: Calibration Serialization Round-Trip**
    - Save homography to JSON, load back, verify numerical equivalence
    - **Validates: Requirements 3.5, 7.4**
  
  - [ ] 5.3 Write property test for reprojection error threshold
    - **Property 9: Reprojection Error Thresholds Met**
    - Verify computed homography has reprojection error < 5mm
    - **Validates: Requirements 3.3**

- [ ] 6. Checkpoint - Verify homography computation works
  - Run full pipeline: detect → match → compute homography
  - Verify homography is non-degenerate
  - Verify reprojection error < 5mm
  - Save homography to JSON and verify file format
  - Ask user if questions arise

- [ ] 7. Implement CoordinateMapper class
  - [ ] 7.1 Create `src/calibration/coordinate_mapper.py`
    - Implement `__init__()` to load intrinsic and homography from JSON
    - Implement `map_to_board()` with undistortion and homography
    - Implement `map_to_image()` for inverse transformation
    - Implement `is_calibrated()` and `reload_calibration()`
    - Add threading.Lock for thread safety
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_
  
  - [ ] 7.2 Write property test for homography round-trip
    - **Property 3: Homography Round-Trip Consistency**
    - For any board coordinate, map_to_image then map_to_board should return original (±1mm)
    - **Validates: Requirements 4.4, 4.7**
  
  - [ ] 7.3 Write property test for bounds checking
    - **Property 5: Bounds Checking Returns None for Out-of-Bounds**
    - For pixels mapping to radius > 200mm, map_to_board should return None
    - **Validates: Requirements 4.6**
  
  - [ ] 7.4 Write property test for thread safety
    - **Property 8: Thread Safety Under Concurrent Access**
    - Concurrent calls from multiple threads should complete without corruption
    - **Validates: Requirements 4.8**
  
  - [ ] 7.5 Write unit tests for CoordinateMapper
    - Test loading valid calibration files
    - Test handling missing calibration files gracefully
    - Test coordinate system convention (origin, axes)
    - Test reload_calibration() functionality
    - _Requirements: 4.1, 4.5_

- [ ] 8. Implement CalibrationManager class
  - [ ] 8.1 Create `src/calibration/calibration_manager.py`
    - Implement `__init__()` with component dependencies
    - Implement state machine: ready, calibrating, error
    - Implement `get_status()` returning CalibrationStatus
    - _Requirements: 5.5, 6.1, 6.5_
  
  - [ ] 8.2 Implement full calibration workflow
    - Implement `run_full_calibration()` orchestrating detect → match → compute → save
    - Handle calibration failures with retry logic
    - _Requirements: 5.1, 6.6_
  
  - [ ] 8.3 Implement lightweight validation
    - Implement `run_lightweight_validation()` checking bull center only
    - Compute drift as distance from expected (0, 0)
    - _Requirements: 5.2, 5.3_
  
  - [ ] 8.4 Implement drift detection and recalibration
    - Implement `check_and_recalibrate()` triggering recalibration on drift > 3mm
    - Track consecutive failures, enter error state after 3
    - _Requirements: 5.3, 5.4, 6.6_
  
  - [ ] 8.5 Write property test for drift detection
    - **Property 6: Drift Detection Triggers Recalibration**
    - For drift > 3mm, state should transition to "calibrating"
    - **Validates: Requirements 5.3**
  
  - [ ] 8.6 Write property test for state machine transitions
    - **Property 7: State Machine Transitions Are Valid**
    - Verify only valid state transitions occur
    - After 3 failures, state should be "error"
    - **Validates: Requirements 6.1, 6.6**

- [ ] 9. Checkpoint - Verify calibration manager works
  - Test full calibration workflow on real camera
  - Test lightweight validation detects drift
  - Test state transitions: ready → calibrating → ready
  - Test failure handling: 3 failures → error state
  - Ask user if questions arise

- [ ] 10. Implement intrinsic calibration script (preserved from original)
  - [ ] 10.1 Create `src/calibration/intrinsic_calibrator.py`
    - Implement chessboard image capture with interactive UI
    - Implement calibration using cv2.calibrateCamera
    - Implement save to JSON format
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  
  - [ ] 10.2 Create `calibration/calibrate_intrinsic.py` script
    - Interactive camera capture with live preview
    - Chessboard detection overlay
    - Capture 20-30 images at different angles
    - Display reprojection error and save results
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 11. Implement color-based calibration script
  - [ ] 11.1 Create `calibration/calibrate_color_boundaries.py` script
    - Initialize cameras and capture frames
    - Run FeatureDetector on each camera (color-based detection)
    - Run FeatureMatcher to get point pairs with confidence weights
    - Run HomographyCalculator to compute and save homography
    - Display summary with feature counts and reprojection errors
    - Add visualization option to show detected features and color masks
    - _Requirements: 1.1-1.9, 2.1-2.8, 3.1-3.5_

- [ ] 12. Implement calibration verification script
  - [ ] 12.1 Create `calibration/verify_calibration.py` script
    - Interactive UI for clicking control points (T20, D20, bull)
    - Transform clicked pixels to board coordinates
    - Compute error vs known ground truth
    - Display error statistics and save verification report
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  
  - [ ] 12.2 Write property test for error computation
    - **Property 9 (continued): Verification error computation**
    - Verify average error calculation is correct
    - **Validates: Requirements 8.3, 8.4**

- [ ] 13. Integrate coordinate mapper into main.py
  - [ ] 13.1 Add CoordinateMapper initialization
    - Import CoordinateMapper and CalibrationManager
    - Initialize after camera manager setup
    - Check which cameras are calibrated
    - Log warning if no cameras calibrated
    - _Requirements: 4.1, 5.1_
  
  - [ ] 13.2 Add coordinate transformation to dart detection loop
    - After dart detection, transform pixel to board coordinates
    - Store both pixel and board coordinates in detection results
    - Log board coordinates for each detection
    - Handle cameras without calibration gracefully
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6_
  
  - [ ] 13.3 Add calibration state checking
    - Check CalibrationManager status before processing throws
    - Skip scoring when state is "calibrating"
    - Log when calibration state changes
    - _Requirements: 6.2, 6.3_
  
  - [ ] 13.4 Add command-line flags for calibration
    - Add `--calibrate` flag to run color-based calibration at startup
    - Add `--calibrate-intrinsic` flag to run intrinsic calibration
    - Add `--verify-calibration` flag to run verification script
    - _Requirements: 5.1, 7.1, 8.1_
  
  - [ ] 13.5 Add keyboard shortcut for runtime calibration
    - Add 'c' key handler to trigger color-based calibration in dev mode
    - Run calibration for all cameras
    - Reload coordinate mapper after calibration
    - _Requirements: 5.4_

- [ ] 14. Add calibration visualization for debugging
  - [ ] 14.1 Implement calibration visualization overlay
    - Draw detected bull center (green ellipse)
    - Draw detected ring edges (blue ellipses)
    - Draw detected sector boundaries (yellow lines from bull center)
    - Draw boundary intersections (red dots)
    - Draw color masks (overlay showing detected black/white/red/green regions)
    - Add toggle with 'v' key in dev mode
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.9_

- [ ] 15. Final checkpoint - End-to-end testing
  - Run full calibration workflow (intrinsic + color-based)
  - Verify coordinate transformation in main.py
  - Test with actual dart throws
  - Verify multi-camera detections produce consistent board coordinates
  - Run verification script to measure accuracy (< 5mm average error)
  - Test continuous calibration: drift detection and recalibration
  - Verify color-based detection works from all camera angles (especially cam2)
  - Ensure all tests pass
  - Ask user if questions arise

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- Integration happens incrementally to catch errors early
- Intrinsic calibration (chessboard) is preserved from original design - it handles lens distortion which is camera-specific
- Color-based calibration replaces wire detection for extrinsic calibration - more robust for thin modern dartboard wires
- HSV color space used for better color segmentation under LED lighting
- Ellipse fitting used for bull detection to handle perspective distortion from angled cameras
