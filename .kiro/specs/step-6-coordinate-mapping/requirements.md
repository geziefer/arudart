# Step 6: Coordinate Mapping (Image → Board Plane)

## Overview

Map camera pixel coordinates to board coordinate system using intrinsic and extrinsic calibration. This enables converting detected dart tip positions from each camera's image space to a common board-centered coordinate system in millimeters.

## User Stories

### US-6.1: Intrinsic Camera Calibration
**As a** system operator  
**I want to** calibrate each camera's intrinsic parameters (camera matrix, distortion coefficients)  
**So that** I can correct for lens distortion and accurately map image coordinates to real-world coordinates

**Acceptance Criteria:**
- AC-6.1.1: Calibration script captures 20-30 chessboard images per camera at different angles
- AC-6.1.2: Calibration computes camera matrix and distortion coefficients using `cv2.calibrateCamera`
- AC-6.1.3: Reprojection error is less than 0.5 pixels for each camera
- AC-6.1.4: Calibration results saved to `calibration/intrinsic_cam{0,1,2}.json`
- AC-6.1.5: Calibration is one-time unless cameras are moved

### US-6.2: ARUCO Marker Setup
**As a** system operator  
**I want to** place ARUCO markers at known positions around the dartboard  
**So that** the system can automatically detect reference points for extrinsic calibration

**Acceptance Criteria:**
- AC-6.2.1: Generate 4-6 ARUCO markers from DICT_4X4_50 dictionary
- AC-6.2.2: Markers printed at ~40mm square size
- AC-6.2.3: Markers mounted at known positions (12, 3, 6, 9 o'clock) outside double ring (~200mm from center)
- AC-6.2.4: Marker positions and IDs documented in `config.toml`
- AC-6.2.5: Markers reliably detected in all 3 camera views

### US-6.3: Extrinsic Calibration (Homography)
**As a** system operator  
**I want to** compute homography matrices mapping each camera's image plane to the board plane  
**So that** detected dart positions can be transformed to board coordinates

**Acceptance Criteria:**
- AC-6.3.1: System detects ARUCO markers in each camera view
- AC-6.3.2: Homography computed using `cv2.findHomography` with marker corners
- AC-6.3.3: Homography matrices saved per camera
- AC-6.3.4: Extrinsic calibration runs at startup (fast, <1 second)
- AC-6.3.5: System logs warning if markers not detected

### US-6.4: Coordinate Transformation
**As a** developer  
**I want to** transform image coordinates (u, v) to board coordinates (x, y) in millimeters  
**So that** dart positions from different cameras can be compared and fused

**Acceptance Criteria:**
- AC-6.4.1: `CoordinateMapper` class loads intrinsic and homography parameters
- AC-6.4.2: `map_to_board(camera_id, u, v)` returns (x, y) in mm
- AC-6.4.3: Points are undistorted using intrinsic parameters before transformation
- AC-6.4.4: Board coordinate system: center (0, 0), +X right, +Y up
- AC-6.4.5: Transformation handles edge cases (points outside board, invalid homography)

### US-6.5: Calibration Verification
**As a** system operator  
**I want to** verify calibration accuracy using known control points  
**So that** I can ensure the coordinate mapping is accurate before using the system

**Acceptance Criteria:**
- AC-6.5.1: Verification script allows manual marking of known points (T20, D20, bull)
- AC-6.5.2: System maps marked points to board coordinates
- AC-6.5.3: Mapping error computed for each control point
- AC-6.5.4: Average mapping error is less than 5mm
- AC-6.5.5: Verification results logged and saved

## Board Specifications (Winmau Blade 6)

- **Board diameter**: 340mm (17 inches)
- **Board radius**: 170mm
- **Bull (double bull)**: 12.7mm diameter (6.35mm radius)
- **Single bull**: 31.8mm diameter (15.9mm radius)
- **Triple ring**: inner 99mm, outer 107mm from center
- **Double ring**: inner 162mm, outer 170mm from center
- **Sector angles**: 20° wedges, starting at -9° for sector 20

## Technical Constraints

- Calibration must work on both macOS (development) and Raspberry Pi (production)
- Chessboard pattern: 9×6 squares, 25mm each (printable on A4)
- ARUCO markers: DICT_4X4_50, IDs 0-5
- Homography assumes dart tips lie on board plane (ignoring dart tilt)
- Calibration files stored in JSON format for portability

## Dependencies

- OpenCV with ARUCO module (`cv2.aruco`)
- NumPy for matrix operations
- Existing camera capture system (Steps 1-2)
- Configuration system (`config.toml`)

## Success Metrics

- Intrinsic calibration reprojection error < 0.5 pixels
- ARUCO markers detected in 100% of startup attempts (with proper lighting)
- Control point mapping error < 5mm average
- Calibration completes in < 5 seconds at startup
- System gracefully handles missing markers (logs warning, continues with last known calibration)
