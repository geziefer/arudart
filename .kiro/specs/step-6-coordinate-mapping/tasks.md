# Implementation Plan: Step 6 - Coordinate Mapping

## Overview

This implementation plan breaks down the coordinate mapping system into discrete coding tasks. Each task builds on previous steps and includes references to specific requirements. The system transforms camera pixel coordinates to board-plane coordinates using intrinsic and extrinsic calibration.

## Tasks

- [x] 1. Set up calibration module structure and configuration
  - Create `src/calibration/` directory with `__init__.py`
  - Create `calibration/` directory for calibration files and scripts
  - Add calibration configuration section to `config.toml`
  - Update `requirements.txt` with `opencv-contrib-python` (for ARUCO)
  - _Requirements: AC-6.1.4, AC-6.2.4, AC-6.3.3_

- [ ] 2. Implement ARUCO marker generation script
  - [x] 2.1 Create `calibration/generate_aruco_markers.py`
    - Implement marker generation using DICT_4X4_50 dictionary
    - Generate individual marker images (40mm at 300 DPI)
    - Generate combined marker sheet for easy printing
    - Add printing instructions and verification guidance
    - _Requirements: AC-6.2.1, AC-6.2.6_

- [ ] 3. Implement ArucoDetector class
  - [x] 3.1 Create `src/calibration/aruco_detector.py`
    - Implement `__init__()` with dictionary initialization
    - Implement `detect_markers()` using cv2.aruco.detectMarkers()
    - Implement `validate_markers()` to check for minimum 4 markers
    - Implement `draw_markers()` for visualization
    - Add error handling for detection failures
    - _Requirements: AC-6.2.5, AC-6.3.1_
  
  - [x] 3.2 Write property test for marker detection
    - **Property 1: Marker Detection Reliability**
    - Generate synthetic images with ARUCO markers at various positions
    - Verify detection succeeds and corner accuracy within 1 pixel
    - **Validates: Requirements AC-6.2.5, AC-6.3.1**

- [ ] 4. Implement IntrinsicCalibrator class
  - [x] 4.1 Create `src/calibration/intrinsic_calibrator.py`
    - Implement `__init__()` with chessboard configuration
    - Implement `capture_calibration_images()` with interactive UI
    - Implement `calibrate()` using cv2.calibrateCamera()
    - Implement `save_calibration()` to JSON format
    - Add validation for reprojection error < 0.5 pixels
    - _Requirements: AC-6.1.1, AC-6.1.2, AC-6.1.3, AC-6.1.4_
  
  - [x] 4.2 Write unit tests for intrinsic calibration
    - Test chessboard detection with synthetic images
    - Test calibration computation with known geometry
    - Test JSON serialization/deserialization
    - Test error handling for insufficient images
    - _Requirements: AC-6.1.2, AC-6.1.3, AC-6.1.4_
  
  - [x] 4.3 Write property test for calibration serialization
    - **Property 5: Calibration Serialization Round Trip**
    - Generate random valid calibration matrices
    - Save to JSON, load back, verify numerical equivalence
    - **Validates: Requirements AC-6.1.4**

- [ ] 5. Implement intrinsic calibration script
  - [x] 5.1 Create `calibration/calibrate_intrinsic.py`
    - Implement interactive camera capture with live preview
    - Show chessboard detection overlay
    - Capture 20-30 images at different angles
    - Run calibration and display reprojection error
    - Save results to `calibration/intrinsic_cam{N}.json`
    - _Requirements: AC-6.1.1, AC-6.1.2, AC-6.1.3, AC-6.1.4_

- [x] 6. Checkpoint - Verify intrinsic calibration works
  - Run intrinsic calibration script for one camera
  - Verify reprojection error < 0.5 pixels
  - Verify JSON file created with correct format
  - Ask user if questions arise


- [ ] 7. Implement ExtrinsicCalibrator class
  - [~] 7.1 Create `src/calibration/extrinsic_calibrator.py`
    - Implement `__init__()` with ArucoDetector and marker positions from config
    - Implement `calibrate()` to compute homography using cv2.findHomography()
    - Implement `save_calibration()` to JSON format
    - Implement `verify_homography()` to compute reprojection error
    - Add error handling for insufficient markers and degenerate homography
    - _Requirements: AC-6.3.1, AC-6.3.2, AC-6.3.3, AC-6.3.6_
  
  - [~] 7.2 Write unit tests for extrinsic calibration
    - Test marker detection with synthetic images
    - Test homography computation with known point correspondences
    - Test JSON serialization/deserialization
    - Test error handling for missing markers
    - _Requirements: AC-6.3.2, AC-6.3.3, AC-6.3.6_
  
  - [~] 7.3 Write property test for homography collinearity
    - **Property 3: Homography Preserves Collinearity**
    - Generate random sets of 3 collinear board points
    - Transform to image coordinates
    - Verify collinearity using cross product (near zero)
    - **Validates: Requirements AC-6.3.2**

- [ ] 8. Implement extrinsic calibration script
  - [~] 8.1 Create `calibration/calibrate_extrinsic.py`
    - Initialize all cameras
    - For each camera: detect markers, compute homography, save results
    - Display summary with marker counts and reprojection errors
    - Add visualization option to show detected markers
    - _Requirements: AC-6.3.1, AC-6.3.2, AC-6.3.3, AC-6.3.4_

- [ ] 9. Implement CoordinateMapper class
  - [~] 9.1 Create `src/calibration/coordinate_mapper.py`
    - Implement `__init__()` to load calibration data from JSON files
    - Implement `map_to_board()` with undistortion and homography
    - Implement `map_to_image()` for inverse transformation
    - Implement `is_calibrated()` to check calibration status
    - Implement `reload_calibration()` for runtime recalibration
    - Add thread safety with threading.Lock
    - Add error handling for missing calibration files
    - Add bounds checking for out-of-bounds coordinates
    - _Requirements: AC-6.4.1, AC-6.4.2, AC-6.4.3, AC-6.4.4, AC-6.4.5, AC-6.3.7_
  
  - [~] 9.2 Write property test for homography inverse
    - **Property 2: Homography Inverse Property (Round Trip)**
    - Generate random board coordinates within bounds (-200 to +200mm)
    - Transform to image then back to board
    - Verify round trip error < 1mm
    - **Validates: Requirements AC-6.4.2, AC-6.5.2**
  
  - [~] 9.3 Write property test for undistortion invertibility
    - **Property 6: Undistortion is Invertible**
    - Generate random pixel coordinates within image bounds
    - Undistort then redistort
    - Verify round trip error < 0.1 pixels
    - **Validates: Requirements AC-6.4.3**
  
  - [~] 9.4 Write property test for coordinate bounds checking
    - **Property 7: Coordinate Bounds Checking**
    - Generate pixel coordinates that map outside board bounds
    - Verify system returns None or flags out-of-bounds
    - **Validates: Requirements AC-6.4.5**
  
  - [~] 9.5 Write property test for multi-camera consistency
    - **Property 8: Transformation Consistency Across Cameras**
    - Generate random board coordinates
    - Transform to image for all 3 cameras, then back to board
    - Verify all cameras agree within 5mm
    - **Validates: Requirements AC-6.4.2, AC-6.5.4**
  
  - [~] 9.6 Write unit tests for CoordinateMapper
    - Test loading valid calibration files
    - Test handling missing calibration files gracefully
    - Test coordinate system convention (origin, axes)
    - Test thread-safe concurrent access
    - Test reload_calibration() functionality
    - _Requirements: AC-6.4.1, AC-6.4.4, AC-6.3.7_

- [~] 10. Checkpoint - Verify coordinate transformation works
  - Create test calibration files with known homography
  - Test map_to_board() with known pixel coordinates
  - Verify board coordinates match expected values
  - Test map_to_image() inverse transformation
  - Ask user if questions arise

- [ ] 11. Implement calibration verification script
  - [~] 11.1 Create `calibration/verify_calibration.py`
    - Implement interactive UI for clicking control points
    - Load coordinate mapper and display camera view
    - Transform clicked pixels to board coordinates
    - Compute error vs known ground truth (T20, D20, bull, etc.)
    - Display error statistics and save verification report
    - _Requirements: AC-6.5.1, AC-6.5.2, AC-6.5.3, AC-6.5.4, AC-6.5.5_
  
  - [~] 11.2 Write property test for calibration quality metrics
    - **Property 4: Calibration Quality Metrics**
    - Use real calibration data with known control points
    - Verify reprojection error < 0.5 pixels (intrinsic)
    - Verify mapping error < 5mm (extrinsic with control points)
    - **Validates: Requirements AC-6.1.3, AC-6.5.4**

- [ ] 12. Integrate coordinate mapper into main.py
  - [~] 12.1 Add CoordinateMapper initialization in main.py
    - Import CoordinateMapper class
    - Initialize after camera manager setup
    - Check which cameras are calibrated
    - Log warning if no cameras calibrated
    - _Requirements: AC-6.4.1_
  
  - [~] 12.2 Add coordinate transformation to dart detection loop
    - After dart detection, transform pixel coordinates to board coordinates
    - Store both pixel and board coordinates in detection results
    - Log board coordinates for each detection
    - Handle cameras without calibration gracefully
    - _Requirements: AC-6.4.2, AC-6.4.5_
  
  - [~] 12.3 Add command-line flags for calibration
    - Add `--calibrate` flag to run extrinsic calibration at startup
    - Add `--verify-calibration` flag to run verification script
    - Implement calibration trigger logic
    - _Requirements: AC-6.3.5, AC-6.3.7_
  
  - [~] 12.4 Add keyboard shortcut for runtime calibration
    - Add 'c' key handler to trigger extrinsic calibration in dev mode
    - Run calibration for all cameras
    - Reload coordinate mapper after calibration
    - _Requirements: AC-6.3.7_

- [ ] 13. Add calibration visualization for debugging
  - [~] 13.1 Implement calibration visualization overlay
    - Draw board coordinate grid on camera view
    - Draw coordinate axes (X=red, Y=green)
    - Show marker detection with IDs and corners
    - Add toggle with 'v' key in dev mode
    - _Requirements: AC-6.4.4_

- [~] 14. Final checkpoint - End-to-end testing
  - Run full calibration workflow (intrinsic + extrinsic)
  - Verify coordinate transformation in main.py
  - Test with actual dart throws
  - Verify multi-camera detections produce consistent board coordinates
  - Run verification script to measure accuracy
  - Ensure all tests pass
  - Ask user if questions arise

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- Integration happens incrementally to catch errors early
- All tests are required for comprehensive validation

