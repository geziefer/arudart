# Requirements Document

## Introduction

This document specifies requirements for Step 6 - Coordinate Mapping using manual control point calibration for the ARU-DART automatic dartboard scoring system. The system transforms pixel coordinates from each of 3 USB cameras to board-plane coordinates in millimeters using 17 manually clicked wire-wire intersection points to compute a per-camera homography matrix.

Manual control point calibration is the primary method, proven accurate and reliable across all camera angles. The user clicks on known board positions (bull center + 8 sector boundary intersections on inner triple ring + 8 on outer double ring), and the system computes a homography for each camera. Automatic feature detection (color-based) is preserved as an optional future enhancement but is not required for core functionality.

## Glossary

- **Spiderweb**: The wire structure of a dartboard consisting of concentric rings and radial wires that define scoring segments (NOTE: wires are too thin for reliable detection; color boundaries used instead)
- **Sector_Boundary**: The boundary between two adjacent sectors, detected via color transitions (black/white in singles, red/green in rings)
- **Color_Transition**: A change from one dartboard color to another (e.g., black to white, red to green) indicating a sector boundary
- **Bull_Center**: The center point of the dartboard at board coordinates (0, 0)
- **Double_Ring**: The outermost scoring ring at 162-170mm radius
- **Triple_Ring**: The middle scoring ring at 99-107mm radius
- **Single_Bull**: The outer bull ring at 6.35-15.9mm radius
- **Double_Bull**: The inner bull (bullseye) at 0-6.35mm radius
- **Radial_Wire**: One of 20 wires extending from bull to double ring, separating sectors (NOTE: too thin for reliable detection; use color boundaries instead)
- **Wire_Intersection**: A point where a radial wire crosses a ring edge (NOTE: replaced by boundary intersections)
- **Boundary_Intersection**: A point where a sector boundary (detected via color) crosses a ring edge
- **Homography**: A 3×3 transformation matrix mapping image plane to board plane
- **Intrinsic_Calibration**: Camera-specific parameters (focal length, distortion) that correct lens effects
- **Extrinsic_Calibration**: The homography transformation from camera view to board coordinates
- **Calibration_Drift**: Gradual change in calibration accuracy due to camera movement or board rotation
- **Coordinate_Mapper**: The component that transforms pixel coordinates to board coordinates

## Requirements

### Requirement 1: Board Feature Detection (Per-Camera)

**User Story:** As a system operator, I want the system to automatically detect dartboard features (bull, rings, sector boundaries via color) from each camera's perspective, so that per-camera calibration can be performed without external markers.

#### Acceptance Criteria

1. WHEN a camera image is provided, THE Feature_Detector SHALL detect the bull center using ellipse fitting (handles perspective distortion)
2. WHEN a camera image is provided, THE Feature_Detector SHALL detect the double ring as an ellipse (perspective-distorted circle)
3. WHEN a camera image is provided, THE Feature_Detector SHALL detect the triple ring as an ellipse (perspective-distorted circle)
4. WHEN a camera image is provided, THE Feature_Detector SHALL detect sector boundaries using color segmentation (black/white transitions in singles, red/green in rings)
5. WHEN sector boundaries are detected, THE Feature_Detector SHALL identify at least 8 boundaries in the camera's "good view" region
6. WHEN sector boundaries are detected, THE Feature_Detector SHALL identify boundary intersections with ring edges
7. IF the bull center cannot be detected, THEN THE Feature_Detector SHALL return an error indicating detection failure
8. IF fewer than 4 boundary intersections are detected, THEN THE Feature_Detector SHALL return an error indicating insufficient features
9. THE Feature_Detector SHALL prioritize features in the camera's near sectors where perspective distortion is minimal

### Requirement 2: Feature-to-Board Coordinate Mapping (Per-Camera)

**User Story:** As a developer, I want detected features matched to known board geometry for each camera, so that per-camera homography can be computed from pixel to board coordinates.

#### Acceptance Criteria

1. THE Feature_Matcher SHALL map detected bull center to board coordinate (0, 0)
2. THE Feature_Matcher SHALL map detected double ring edge points to 170mm radius
3. THE Feature_Matcher SHALL map detected triple ring edge points to 107mm radius
4. WHEN sector boundaries are detected, THE Feature_Matcher SHALL assign sector numbers based on color pattern (alternating black/white) and sector 20 being at top (12 o'clock)
5. THE Feature_Matcher SHALL compute boundary intersection board coordinates using known radii and sector angles
6. WHEN matching features, THE Feature_Matcher SHALL use RANSAC to reject outliers from misdetected features
7. THE Feature_Matcher SHALL weight features in the camera's near sectors more heavily than distorted far sectors
8. THE Feature_Matcher SHALL use color boundary confidence scores when weighting point pairs

### Requirement 3: Homography Computation (Per-Camera)

**User Story:** As a developer, I want to compute a per-camera homography matrix from matched feature points, so that any pixel coordinate from that camera can be transformed to board coordinates.

#### Acceptance Criteria

1. WHEN at least 4 matched point pairs are available, THE Homography_Calculator SHALL compute a 3×3 homography matrix using cv2.findHomography
2. THE Homography_Calculator SHALL use RANSAC with reprojection threshold of 5 pixels for robustness
3. WHEN homography is computed, THE Homography_Calculator SHALL verify reprojection error is less than 5mm average
4. IF homography computation fails, THEN THE Homography_Calculator SHALL return None and log the failure reason
5. THE Homography_Calculator SHALL save computed homography per camera to calibration/homography_cam{0,1,2}.json

### Requirement 4: Coordinate Transformation

**User Story:** As a developer, I want to transform pixel coordinates (u, v) to board coordinates (x, y) in millimeters, so that dart positions from different cameras can be compared and fused.

#### Acceptance Criteria

1. THE Coordinate_Mapper SHALL load intrinsic calibration (camera matrix, distortion) from JSON files
2. THE Coordinate_Mapper SHALL load homography matrix from JSON files
3. WHEN map_to_board(camera_id, u, v) is called, THE Coordinate_Mapper SHALL undistort the pixel using intrinsic parameters
4. WHEN map_to_board(camera_id, u, v) is called, THE Coordinate_Mapper SHALL apply homography to get board coordinates
5. THE Coordinate_Mapper SHALL use board coordinate system with origin (0, 0) at center, +X right, +Y up
6. IF transformation produces coordinates outside board bounds (radius > 200mm), THEN THE Coordinate_Mapper SHALL return None
7. THE Coordinate_Mapper SHALL provide map_to_image(camera_id, x, y) for inverse transformation
8. THE Coordinate_Mapper SHALL be thread-safe for concurrent multi-camera access

### Requirement 5: Continuous Calibration

**User Story:** As a system operator, I want the system to continuously validate and update calibration, so that accuracy is maintained during extended play sessions.

#### Acceptance Criteria

1. WHEN the system starts, THE Calibration_Manager SHALL perform full calibration detecting all board features
2. WHILE the system is running between throws, THE Calibration_Manager SHALL perform lightweight validation checking bull position and key intersections
3. WHEN lightweight validation detects drift exceeding 3mm, THE Calibration_Manager SHALL trigger full recalibration
4. WHEN full recalibration is triggered, THE Calibration_Manager SHALL update homography without interrupting scoring
5. THE Calibration_Manager SHALL expose calibration status: ready, calibrating, or error
6. WHEN calibration status changes, THE Calibration_Manager SHALL log the transition with timestamp

### Requirement 6: Calibration State Management

**User Story:** As a system operator, I want clear visibility into calibration state, so that I know when the system is ready for scoring.

#### Acceptance Criteria

1. THE Calibration_Manager SHALL maintain state: ready, calibrating, or error
2. WHEN state is "calibrating", THE System SHALL not process dart detections for scoring
3. WHEN state transitions to "ready", THE System SHALL resume normal dart detection and scoring
4. WHEN state is "error", THE System SHALL log diagnostic information and attempt recovery
5. THE Calibration_Manager SHALL provide get_status() returning current state and last calibration timestamp
6. WHEN calibration fails 3 consecutive times, THE Calibration_Manager SHALL enter "error" state and require manual intervention

### Requirement 7: Intrinsic Calibration (Preserved)

**User Story:** As a system operator, I want to calibrate each camera's intrinsic parameters using a chessboard pattern, so that lens distortion is corrected before coordinate transformation.

#### Acceptance Criteria

1. THE Intrinsic_Calibrator SHALL capture 20-30 chessboard images per camera at different angles
2. THE Intrinsic_Calibrator SHALL compute camera matrix and distortion coefficients using cv2.calibrateCamera
3. WHEN calibration completes, THE Intrinsic_Calibrator SHALL verify reprojection error is less than 0.5 pixels
4. THE Intrinsic_Calibrator SHALL save calibration to calibration/intrinsic_cam{0,1,2}.json
5. THE Intrinsic_Calibration SHALL be performed once per camera and reused until camera is moved

### Requirement 8: Calibration Verification

**User Story:** As a system operator, I want to verify calibration accuracy using known control points, so that I can ensure the coordinate mapping is accurate before using the system.

#### Acceptance Criteria

1. THE Verification_Tool SHALL allow manual marking of known points (T20 center, D20 center, bull center)
2. WHEN a point is marked, THE Verification_Tool SHALL transform it to board coordinates and display the result
3. THE Verification_Tool SHALL compute error between transformed coordinates and known ground truth
4. WHEN verification completes, THE Verification_Tool SHALL report average mapping error
5. IF average mapping error exceeds 5mm, THEN THE Verification_Tool SHALL recommend recalibration

## Board Specifications (Winmau Blade 6)

Standard dartboard dimensions used for feature matching:

- **Double Bull radius**: 6.35mm
- **Single Bull outer radius**: 15.9mm
- **Triple ring inner radius**: 99mm
- **Triple ring outer radius**: 107mm
- **Double ring inner radius**: 162mm
- **Double ring outer radius**: 170mm
- **Sector width**: 18° each (360° / 20 sectors)
- **Sector 20 position**: Top (12 o'clock, 0° in board coordinates)
- **Sector order (clockwise from 20)**: 20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5

## Per-Camera Calibration Architecture

Each of the 3 cameras has its own calibration due to different viewing angles:

- **cam0** (upper right, near sector 18): Best view of sectors 18, 4, 13, 6, 10
- **cam1** (lower right, near sector 17): Best view of sectors 17, 3, 19, 7, 16
- **cam2** (left, near sector 11): Best view of sectors 11, 14, 9, 12, 5

**Key insight**: Each camera's homography is computed independently using features visible from that camera's perspective. The bull center is visible from all cameras and serves as a common anchor point. Wire intersections in each camera's "good view" region provide additional correspondence points.

**Perspective distortion**: Features on the far side of the board (opposite the camera) appear compressed and may not be reliably detected. The calibration algorithm focuses on features in the near sectors where detection is reliable.

## Technical Constraints

- Calibration must work on both macOS (development) and Raspberry Pi (production)
- Feature detection must handle varying lighting conditions from LED ring
- Chessboard pattern for intrinsic: 9×6 inner corners, 25mm squares
- Homography assumes dart tips lie on board plane (ignoring dart tilt)
- Calibration files stored in JSON format for portability
- Full calibration should complete in < 5 seconds
- Lightweight validation should complete in < 100ms

## Dependencies

- OpenCV for image processing, edge detection, Hough transforms
- NumPy for matrix operations
- Existing camera capture system (Steps 1-2)
- Configuration system (config.toml)

## Success Metrics

- Bull center detection accuracy: < 2mm error (all cameras)
- Ring edge detection: > 50% of visible circumference detected per camera
- Sector boundary detection: ≥ 8 boundaries detected per camera (in good view region)
- Boundary intersection detection: ≥ 12 intersections per camera
- Homography reprojection error: < 5mm average per camera
- Control point mapping error: < 5mm average
- Full calibration time: < 5 seconds per camera
- Lightweight validation time: < 100ms
- Calibration drift detection threshold: 3mm
