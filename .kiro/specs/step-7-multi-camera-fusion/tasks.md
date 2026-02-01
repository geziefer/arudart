# Implementation Plan: Step 7 - Multi-Camera Fusion and Score Derivation

## Overview

Implement the multi-camera fusion and scoring system that combines per-camera dart detections into a single fused position, converts to polar coordinates, determines ring and sector, calculates the final score, and creates a complete DartHitEvent with all information.

This implementation builds on Step 6 (coordinate mapping) which provides board coordinates in mm. The fusion system handles 0-3 camera detections per throw with confidence-weighted averaging, outlier rejection, and complete event data for downstream systems.

## Tasks

- [ ] 1. Create data models and configuration
  - Create DartHitEvent, Score, and CameraDetection dataclasses in `src/fusion/dart_hit_event.py`
  - Implement `to_dict()` and `from_dict()` methods for JSON serialization
  - Add fusion and board configuration sections to `config.toml`
  - _Requirements: AC-7.6.1, AC-7.6.2, AC-7.6.3, AC-7.6.4, AC-7.6.5, AC-7.6.6, AC-7.6.7_

- [ ] 1.1 Write property test for event JSON serialization
  - **Property 7: Event JSON Serialization Round Trip**
  - **Validates: Requirements AC-7.6.7**

- [ ] 2. Implement CoordinateFusion class
  - [ ] 2.1 Create `src/fusion/coordinate_fusion.py` with CoordinateFusion class
    - Implement `fuse_detections()` method with confidence filtering
    - Handle single camera case (return directly)
    - Handle multi-camera case (weighted average)
    - _Requirements: AC-7.1.1, AC-7.1.2, AC-7.1.3_
  
  - [ ] 2.2 Implement outlier rejection algorithm
    - Compute median position from all detections
    - Filter detections by distance from median (>50mm threshold)
    - Handle edge case: ≤2 detections (no outlier rejection)
    - _Requirements: AC-7.1.4_
  
  - [ ] 2.3 Implement confidence-weighted average
    - Compute weighted average: sum(coord × confidence) / sum(confidence)
    - Apply to both X and Y coordinates
    - Compute combined confidence (average of inlier confidences)
    - _Requirements: AC-7.1.3, AC-7.1.5_

- [ ] 2.4 Write property test for weighted average fusion
  - **Property 3: Weighted Average Fusion Correctness**
  - **Validates: Requirements AC-7.1.3, AC-7.1.5**

- [ ] 2.5 Write property test for outlier rejection
  - **Property 5: Outlier Rejection Correctness**
  - **Validates: Requirements AC-7.1.4**

- [ ] 2.6 Write unit tests for CoordinateFusion
  - Test single camera detection (use directly)
  - Test two camera fusion (weighted average)
  - Test three camera fusion with outliers
  - Test all outliers rejected (return None)
  - Test low confidence filtering
  - _Requirements: AC-7.1.2, AC-7.1.3, AC-7.1.4_

- [ ] 3. Implement PolarConverter class
  - [ ] 3.1 Create `src/fusion/polar_converter.py` with PolarConverter class
    - Implement `cartesian_to_polar()` method
    - Compute radius: r = sqrt(x² + y²)
    - Compute angle: θ = atan2(y, x), normalize to [0, 2π)
    - Handle edge case: (0, 0) → (0, 0)
    - _Requirements: AC-7.2.1, AC-7.2.2, AC-7.2.3, AC-7.2.4_
  
  - [ ] 3.2 Implement `polar_to_cartesian()` method
    - Compute x = r × cos(θ)
    - Compute y = r × sin(θ)
    - _Requirements: AC-7.2.5_
  
  - [ ] 3.3 Add helper methods for angle conversion
    - `radians_to_degrees()` and `degrees_to_radians()`
    - _Requirements: AC-7.2.2_

- [ ] 3.4 Write property test for polar coordinate round trip
  - **Property 2: Polar Coordinate Round Trip**
  - **Validates: Requirements AC-7.2.1, AC-7.2.2, AC-7.2.3, AC-7.2.5**

- [ ] 3.5 Write unit tests for PolarConverter
  - Test origin (0, 0) → (0, 0)
  - Test positive X axis (100, 0) → (100, 0°)
  - Test positive Y axis (0, 100) → (100, 90°)
  - Test negative coordinates
  - Test angle normalization [0, 2π)
  - _Requirements: AC-7.2.4, AC-7.2.3_

- [ ] 4. Checkpoint - Ensure fusion and polar conversion tests pass
  - Ensure all tests pass, ask the user if questions arise.


- [ ] 5. Implement RingDetector class
  - [ ] 5.1 Create `src/fusion/ring_detector.py` with RingDetector class
    - Load board dimensions from config (bull, single_bull, triple, double radii)
    - Implement `determine_ring()` method with radius-based classification
    - Return (ring_name, multiplier, base_score) tuple
    - _Requirements: AC-7.3.1, AC-7.3.2, AC-7.3.3, AC-7.3.4, AC-7.3.5, AC-7.3.6_

- [ ] 5.2 Write property test for ring determination
  - **Property 1: Ring Determination Correctness**
  - **Validates: Requirements AC-7.3.1, AC-7.3.2, AC-7.3.3, AC-7.3.4, AC-7.3.5, AC-7.3.6**

- [ ] 5.3 Write unit tests for RingDetector
  - Test bull (r=3mm) → ("bull", 0, 50)
  - Test single bull (r=10mm) → ("single_bull", 0, 25)
  - Test triple (r=103mm) → ("triple", 3, 0)
  - Test double (r=166mm) → ("double", 2, 0)
  - Test single (r=50mm) → ("single", 1, 0)
  - Test out of bounds (r=180mm) → ("out_of_bounds", 0, 0)
  - Test boundary cases (exactly at thresholds)
  - _Requirements: AC-7.3.1, AC-7.3.2, AC-7.3.3, AC-7.3.4, AC-7.3.5, AC-7.3.6_

- [ ] 6. Implement SectorDetector class
  - [ ] 6.1 Create `src/fusion/sector_detector.py` with SectorDetector class
    - Load sector configuration from config (sector_order, widths, offset)
    - Implement `determine_sector()` method
    - Convert angle to degrees and apply offset
    - Rotate coordinate system (sector 20 at top)
    - Determine wedge index and check for wire
    - Map wedge to sector number using sector_order
    - _Requirements: AC-7.4.1, AC-7.4.2, AC-7.4.3, AC-7.4.4, AC-7.4.5_

- [ ] 6.2 Write property test for sector determination
  - **Property 4: Sector Determination Correctness**
  - **Validates: Requirements AC-7.4.1, AC-7.4.2, AC-7.4.3, AC-7.4.4**

- [ ] 6.3 Write unit tests for SectorDetector
  - Test sector 20 at top (θ=90°)
  - Test all 20 sectors at their center angles
  - Test sector boundaries
  - Test wire detection (last 2° of wedge)
  - Test angle wraparound (359° → 0°)
  - Test sector offset application
  - _Requirements: AC-7.4.1, AC-7.4.2, AC-7.4.3, AC-7.4.4, AC-7.4.5_

- [ ] 7. Implement ScoreCalculator class
  - [ ] 7.1 Create `src/fusion/score_calculator.py` with ScoreCalculator class
    - Initialize all sub-components (fusion, converter, detectors)
    - Implement `process_detections()` orchestration method
    - Pipeline: fusion → polar → ring → sector → score → event
    - _Requirements: AC-7.5.1, AC-7.5.2, AC-7.5.3, AC-7.5.4, AC-7.5.5_
  
  - [ ] 7.2 Implement score calculation logic
    - Handle bull: score = 50 (no sector)
    - Handle single bull: score = 25 (no sector)
    - Handle out of bounds: score = 0 (no sector)
    - Handle regular rings: score = sector × multiplier
    - Create Score object with all fields
    - _Requirements: AC-7.5.1, AC-7.5.2, AC-7.5.3, AC-7.5.4_
  
  - [ ] 7.3 Implement event creation
    - Generate ISO 8601 timestamp
    - Convert detections to CameraDetection objects
    - Populate all DartHitEvent fields
    - Include image paths if provided
    - _Requirements: AC-7.6.1, AC-7.6.2, AC-7.6.3, AC-7.6.4, AC-7.6.5, AC-7.6.6_

- [ ] 7.4 Write property test for score calculation
  - **Property 6: Score Calculation Correctness**
  - **Validates: Requirements AC-7.5.1, AC-7.5.2, AC-7.5.3**

- [ ] 7.5 Write property test for event structure completeness
  - **Property 8: Event Structure Completeness**
  - **Validates: Requirements AC-7.5.4, AC-7.5.5, AC-7.6.1, AC-7.6.2, AC-7.6.3, AC-7.6.4, AC-7.6.5, AC-7.6.6**

- [ ] 7.6 Write unit tests for ScoreCalculator
  - Test T20 (triple 20) → 60
  - Test D20 (double 20) → 40
  - Test S20 (single 20) → 20
  - Test Bull → 50
  - Test Single bull → 25
  - Test out of bounds → 0
  - Test complete event creation with all fields
  - _Requirements: AC-7.5.1, AC-7.5.2, AC-7.5.3, AC-7.5.4, AC-7.5.5_

- [ ] 8. Checkpoint - Ensure all scoring tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Integration with main loop
  - [ ] 9.1 Update main.py to initialize ScoreCalculator
    - Import ScoreCalculator from src.fusion
    - Initialize with config after coordinate mapper
    - _Requirements: AC-7.1.1_
  
  - [ ] 9.2 Integrate fusion into dart detection workflow
    - After coordinate mapping, collect detections with board coordinates
    - Call `score_calculator.process_detections()` with detections and image paths
    - Handle null result (no valid detections after fusion)
    - _Requirements: AC-7.1.1, AC-7.1.2, AC-7.1.3_
  
  - [ ] 9.3 Add logging for fusion results
    - Log score (total, base, multiplier)
    - Log ring and sector
    - Log position (board coordinates, polar coordinates)
    - Log cameras used and confidence
    - _Requirements: AC-7.1.6, AC-7.5.4, AC-7.5.5_
  
  - [ ] 9.4 Save DartHitEvent to JSON
    - Generate timestamp-based filename
    - Save event using `to_dict()` method
    - Save to `data/throws/event_{timestamp}.json`
    - _Requirements: AC-7.6.7_

- [ ] 9.5 Write integration tests
  - Test full pipeline (detections → event)
  - Test multi-camera fusion with realistic data
  - Test known control points (T20, D20, bull) with expected scores
  - Test error handling (no detections, all outliers)
  - _Requirements: AC-7.1.1, AC-7.1.2, AC-7.1.3, AC-7.5.1, AC-7.5.2, AC-7.5.3_

- [ ] 10. Add configuration to config.toml
  - Add `[fusion]` section with outlier_threshold_mm and min_confidence
  - Add `[board]` section with all ring dimensions
  - Add `[board.sectors]` section with sector_order, widths, and offset
  - _Requirements: AC-7.1.4, AC-7.3.1, AC-7.3.2, AC-7.3.3, AC-7.3.4, AC-7.3.5, AC-7.3.6, AC-7.4.1, AC-7.4.2, AC-7.4.3, AC-7.4.4_

- [ ] 11. Create test data and fixtures
  - Create `tests/data/fusion/` directory
  - Add single_camera.json with example single-camera detections
  - Add multi_camera.json with example multi-camera detections
  - Add outliers.json with outlier rejection examples
  - Add control_points.json with known scores (T20, D20, bull, etc.)
  - _Requirements: AC-7.1.2, AC-7.1.3, AC-7.1.4_

- [ ] 12. Final checkpoint - End-to-end testing
  - Run full system with real camera detections
  - Verify fusion works with Step 6 coordinate mapping
  - Verify events are saved correctly to JSON
  - Verify scores are calculated correctly for known throws
  - Test with single camera, two cameras, and three cameras
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (minimum 100 iterations each)
- Unit tests validate specific examples and edge cases
- Integration tests validate end-to-end workflow
- All tests are required for comprehensive validation

