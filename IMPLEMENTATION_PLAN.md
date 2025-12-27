# ARU-DART Implementation Plan & Progress Tracker

**Project Start**: 2025-12-27  
**Current Phase**: Phase 1 - POC Development  
**Status**: Planning Complete - Ready to Start

---

## Implementation Steps

### ✅ Step 0: Project Setup & Planning
**Status**: COMPLETE  
**Completed**: 2025-12-27

- [x] Review project requirements
- [x] Clarify hardware setup and constraints
- [x] Define technical approach
- [x] Create implementation plan

---

### ✅ Step 1: Single-Camera Capture and FPS Measurement
**Status**: COMPLETE  
**Completed**: 2025-12-27  
**Goal**: Robust capture from one OV9732, measure achievable FPS at chosen resolution

#### Tasks:
- [x] Create project structure (`src/`, subdirectories)
- [x] Set up `pyproject.toml` or `requirements.txt` with dependencies
- [x] Implement `config.py` with TOML loading
- [x] Create initial `config.toml` with single camera configuration
- [x] Implement `camera/camera_stream.py`:
  - [x] `CameraStream` class with threaded capture
  - [x] OpenCV VideoCapture initialization
  - [x] Set resolution (start with 800×600)
  - [x] Set FPS target (~25)
  - [x] Set MJPEG format via FOURCC
  - [x] Thread-safe frame storage
  - [x] Manual exposure control for LED ring
- [x] Implement `camera/camera_manager.py`:
  - [x] `CameraManager` class
  - [x] Single camera management
  - [x] `get_latest_frame(camera_id)` method
- [x] Implement `util/logging_setup.py`:
  - [x] Structured logging configuration
- [x] Implement `util/metrics.py`:
  - [x] FPS counter with rolling window
  - [x] Basic timing metrics
- [x] Create `main.py`:
  - [x] Argument parsing (--config, --dev-mode)
  - [x] Camera initialization
  - [x] FPS measurement loop (10 seconds)
  - [x] Logging output
  - [x] Preview window in dev mode

#### Verification:
- [x] Test on Mac with single camera
- [x] Achieve stable ~20-30 FPS at 800×600
- [x] Log capture FPS and resolution
- [x] No frame drops or timeout errors

#### Success Criteria:
- ✅ Stable capture for 10+ seconds without errors
- ✅ FPS within acceptable range (achieved 35 FPS)
- ✅ Clean log output with metrics

#### Results:
- Camera opened at 800×600, achieved 35 FPS (exceeded target)
- Image quality good with LED ring, no overexposure issues
- Manual exposure setting (-6) works well

---

### ✅ Step 2: Multi-Camera Capture (3 Cameras)
**Status**: COMPLETE  
**Completed**: 2025-12-27  
**Goal**: Capture from all three cameras concurrently with auto-detection

#### Tasks:
- [x] Update `config.toml` for camera auto-detection
  - [x] Add `[camera_detection]` section with auto_detect flag
  - [x] Add `[camera_settings]` for common settings
  - [x] Support exclude_builtin to skip Mac built-in camera
- [x] Extend `CameraManager`:
  - [x] Implement auto-detection logic
  - [x] Scan camera indices 0-10
  - [x] Filter by resolution capability (≤1280×720 for OV9732)
  - [x] Exclude built-in cameras (>1280×720 resolution)
  - [x] Spawn multiple `CameraStream` instances
  - [x] Per-camera frame retrieval
  - [x] Graceful failure for missing cameras
  - [x] Add `get_camera_ids()` method
- [x] Update `CameraStream`:
  - [x] Add `opened` flag for graceful failure
  - [x] Log WARNING instead of exception on failure
- [x] Update `main.py`:
  - [x] Initialize all detected cameras
  - [x] Per-camera FPS counters
  - [x] Log per-camera FPS
  - [x] Multiple preview windows in dev mode
  - [x] Exit gracefully if no cameras found

#### Verification:
- [x] Test on Mac with 1 USB camera (built-in excluded)
- [x] Test with 3 USB cameras connected
- [x] All cameras capture simultaneously
- [x] Per-camera FPS logged
- [x] No resource exhaustion

#### Success Criteria:
- ✅ All detected cameras run for several minutes without errors
- ✅ Consistent FPS across cameras
- ✅ CPU usage acceptable
- ✅ Auto-detection works on both Mac (with built-in) and Pi (without)

#### Results:
- Auto-detection successfully excludes Mac built-in cameras (>1280×720)
- OV9732 USB cameras detected correctly
- Multi-camera support working with per-camera FPS tracking
- Graceful failure handling for missing cameras

#### Notes:
- Auto-detection filters cameras by max resolution (OV9732 = 1280×720 max)
- Built-in Mac cameras typically >1280×720, so they're excluded
- On Pi, all USB cameras will be detected starting from index 0
- Each camera on separate USB port (USB 3.0 preferred)

---

### ⬜ Step 3: Basic Motion Detection (Impact Detection)
**Status**: NOT STARTED  
**Goal**: Detect when a throw has happened via motion detection

#### Tasks:
- [ ] Add motion detection config to `config.toml`:
  - [ ] Downscale factor (e.g., 4)
  - [ ] Motion threshold
  - [ ] Gaussian blur kernel size
  - [ ] Settled threshold
- [ ] Implement `processing/motion_detection.py`:
  - [ ] `MotionDetector` class
  - [ ] Background frame maintenance
  - [ ] Downscaled frame processing
  - [ ] `cv2.absdiff` computation
  - [ ] Thresholding and blur
  - [ ] Motion detection logic
  - [ ] Return motion boolean + bounding box
- [ ] Integrate with `CameraManager`:
  - [ ] Motion detection at ~10-15 FPS
  - [ ] Combined motion signal across cameras
  - [ ] Impact and settled detection
- [ ] Update `main.py`:
  - [ ] Motion detection loop
  - [ ] Log motion events

#### Verification:
- [ ] Test with hand movements in front of board
- [ ] Test with actual dart throws
- [ ] No false positives from light flicker
- [ ] Clear motion signal on throws

#### Success Criteria:
- Reliable detection of throw start
- Reliable detection of board settled state
- Minimal false positives

#### Notes:
- Downscale heavily for performance (e.g., 200×150)
- May need per-camera motion thresholds

---

### ⬜ Step 3.5: Exposure/Brightness Adjustment
**Status**: NOT STARTED  
**Goal**: Handle bright LED ring, ensure good image quality for detection

#### Tasks:
- [ ] Add camera exposure settings to `config.toml`:
  - [ ] Auto-exposure on/off
  - [ ] Fixed exposure value
  - [ ] Brightness/contrast adjustments
- [ ] Implement exposure control in `CameraStream`:
  - [ ] Set `CAP_PROP_AUTO_EXPOSURE` to manual
  - [ ] Set `CAP_PROP_EXPOSURE` to fixed value
  - [ ] Optional: brightness/contrast via `CAP_PROP_BRIGHTNESS`
- [ ] Test and tune exposure values:
  - [ ] Capture test frames with LED ring on
  - [ ] Check histogram distribution
  - [ ] Adjust until board is clearly visible without overexposure
- [ ] Optional: Implement post-processing:
  - [ ] CLAHE (Contrast Limited Adaptive Histogram Equalization)
  - [ ] Only if fixed exposure insufficient

#### Verification:
- [ ] Capture frames with LED ring on
- [ ] Board surface clearly visible
- [ ] No overexposed regions on board
- [ ] Dart contrast sufficient for detection

#### Success Criteria:
- Consistent image brightness across frames
- Board details visible in all lighting conditions
- No blown-out highlights from LED ring

#### Notes:
- Fixed exposure critical for stable background subtraction
- May need different exposure per camera depending on angle

---

### ⬜ Step 4: Dart Detection in One Camera
**Status**: NOT STARTED  
**Goal**: Detect dart shaft/tip in single camera via image differencing

#### Tasks:
- [ ] Add dart detection config to `config.toml`:
  - [ ] Diff threshold
  - [ ] Gaussian blur kernel
  - [ ] Min/max dart area (pixels)
  - [ ] Min shaft length
  - [ ] Aspect ratio thresholds
- [ ] Implement `processing/background_model.py`:
  - [ ] `BackgroundModel` class
  - [ ] Per-camera pre-impact frame storage
  - [ ] Update on settled state
- [ ] Implement `processing/dart_detection.py`:
  - [ ] `DartDetector` class
  - [ ] Input: pre_frame, post_frame
  - [ ] Grayscale conversion
  - [ ] `cv2.absdiff` and thresholding
  - [ ] Gaussian blur
  - [ ] Contour detection
  - [ ] Filter by area and elongation
  - [ ] Orientation via PCA or `fitLine`
  - [ ] Tip identification (closer to board center)
  - [ ] Output: tip coordinates (u, v), confidence, debug mask
- [ ] Integrate with motion detection:
  - [ ] Capture pre-impact frame before throw
  - [ ] Capture post-impact frame after settled
  - [ ] Run dart detection
- [ ] Implement image saving:
  - [ ] Save post_frame with annotated tip
  - [ ] Save diff mask for debugging
  - [ ] Organize by timestamp/throw ID
- [ ] Update `main.py`:
  - [ ] Dart detection on motion settled
  - [ ] Log detected coordinates
  - [ ] Save annotated images in dev mode

#### Verification:
- [ ] Test with 20-30 throws in different sectors
- [ ] Inspect saved annotated images
- [ ] Verify tip detection roughly matches dart position
- [ ] Check detection rate (should be >70% for single camera)

#### Success Criteria:
- Plausible dart shaft and tip detected in most throws
- Annotated images show detection overlay
- Confidence scores correlate with visual quality

#### Notes:
- Start with one camera (index 0)
- May need to tune thresholds per camera
- Elongation filter critical to reject noise

---

### ⬜ Step 5: Extend Dart Detection to 3 Cameras
**Status**: NOT STARTED  
**Goal**: Get per-camera tip detections for each throw

#### Tasks:
- [ ] Extend `BackgroundModel`:
  - [ ] Maintain pre/post frames for all 3 cameras
- [ ] Run `DartDetector` on all cameras:
  - [ ] Parallel or sequential processing
  - [ ] Handle detection failures (None/invalid)
- [ ] Collect per-camera results:
  - [ ] List of detections with camera ID
  - [ ] Coordinates, confidence, validity flag
- [ ] Update image saving:
  - [ ] Save annotated images from all 3 cameras
  - [ ] Organize in per-throw folder structure
- [ ] Update logging:
  - [ ] Log which cameras detected dart
  - [ ] Log per-camera confidence scores

#### Verification:
- [ ] Test with multiple throws
- [ ] Check per-throw folders with 3 annotated images
- [ ] Monitor detection rate per camera
- [ ] At least 1 camera should detect in most throws

#### Success Criteria:
- Per-camera detections logged and saved
- At least one camera consistently detects dart
- Images available for manual validation

#### Notes:
- Some cameras may fail due to occlusion
- Expect varying detection rates per camera angle

---

### ⬜ Step 6: Coordinate Mapping (Image → Board Plane)
**Status**: NOT STARTED  
**Goal**: Map camera pixel coordinates to board coordinate system

#### Tasks:
- [ ] **Intrinsic Calibration** (one-time per camera):
  - [ ] Create `calibration/calibrate_intrinsics.py` script
  - [ ] Print chessboard pattern (e.g., 9×6 squares, 25mm each)
  - [ ] Capture 20-30 images per camera at different angles
  - [ ] Use `cv2.calibrateCamera` to compute:
    - [ ] Camera matrix
    - [ ] Distortion coefficients
  - [ ] Save to `calibration/intrinsic_cam{0,1,2}.json`
  - [ ] Run calibration for all 3 cameras
- [ ] **ARUCO Marker Setup**:
  - [ ] Generate 4-6 ARUCO markers (4×4 or 5×5 bits, dictionary DICT_4X4_50)
  - [ ] Print markers on A4 paper
  - [ ] Mount at known positions around board:
    - [ ] Suggested: 12, 3, 6, 9 o'clock positions
    - [ ] Measure exact positions in mm from board center
  - [ ] Document marker IDs and positions in config
- [ ] Add calibration config to `config.toml`:
  - [ ] Paths to intrinsic files
  - [ ] Board radius (170mm for standard board)
  - [ ] Ring radii (bull, single bull, triple, double)
  - [ ] ARUCO marker positions and IDs
- [ ] Implement `calibration/markers.py`:
  - [ ] ARUCO marker detection
  - [ ] Extract marker corners
- [ ] Implement `calibration/extrinsic.py`:
  - [ ] Load intrinsic parameters
  - [ ] Detect ARUCO markers in frame
  - [ ] Compute homography from image to board plane
  - [ ] Save homography per camera
- [ ] Implement `processing/coordinate_mapping.py`:
  - [ ] `CoordinateMapper` class
  - [ ] Load homography per camera
  - [ ] `map_to_board(camera_id, u, v)` → (x, y) in mm
  - [ ] Undistort points using intrinsics
- [ ] Add calibration step to `main.py`:
  - [ ] Run extrinsic calibration at startup
  - [ ] Or load pre-computed homographies
- [ ] Create calibration verification script:
  - [ ] Manually mark known points (T20, D20, bull)
  - [ ] Map to board coordinates
  - [ ] Compute mapping error

#### Verification:
- [ ] Intrinsic calibration: reprojection error <0.5 pixels
- [ ] ARUCO markers detected reliably in all cameras
- [ ] Homography computed successfully
- [ ] Known points (T20, bull, etc.) map to correct coordinates
- [ ] Mapping error <5mm for control points

#### Success Criteria:
- All 3 cameras calibrated (intrinsic + extrinsic)
- Homography mapping gives reasonable board coordinates
- Control points validate accuracy

#### Notes:
- Intrinsic calibration is one-time unless cameras moved
- Extrinsic calibration can run at each startup (fast with ARUCO)
- Board coordinate system: center (0,0), +X right, +Y up

**ARUCO Marker Instructions** (to be provided to user):
- Print 4 markers from DICT_4X4_50 (IDs: 0, 1, 2, 3)
- Each marker ~40mm square
- Mount at: 12 o'clock (top), 3 o'clock (right), 6 o'clock (bottom), 9 o'clock (left)
- Distance from board center: ~200mm (outside double ring)
- Measure exact positions and record in config

---

### ⬜ Step 7: Multi-Camera Fusion and Score Derivation
**Status**: NOT STARTED  
**Goal**: Combine per-camera detections into single board coordinate and derive score

#### Tasks:
- [ ] Implement fusion logic in `processing/coordinate_mapping.py`:
  - [ ] Input: list of per-camera detections with coordinates and confidence
  - [ ] Filter invalid detections
  - [ ] If single valid detection: use it
  - [ ] If multiple: weighted average by confidence
  - [ ] Optional: median filter to reject outliers
  - [ ] Output: fused (x, y) in board coordinates
- [ ] Implement score mapping:
  - [ ] Convert (x, y) to polar (r, θ)
  - [ ] Determine ring from radius:
    - [ ] Bull (r < 6.35mm): score 50
    - [ ] Single bull (6.35mm < r < 15.9mm): score 25
    - [ ] Triple ring (99mm < r < 107mm): multiplier 3
    - [ ] Double ring (162mm < r < 170mm): multiplier 2
    - [ ] Single ring: multiplier 1
  - [ ] Determine sector from angle:
    - [ ] Map θ to wedge (20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5)
    - [ ] Account for rotation offset
  - [ ] Output: base number, multiplier, score
- [ ] Implement `events/event_model.py`:
  - [ ] `DartHitEvent` dataclass/Pydantic model:
    - [ ] event_type, timestamp
    - [ ] board_coordinates (x, y)
    - [ ] score (base, multiplier, total)
    - [ ] camera_hits (per-camera data)
    - [ ] image_paths (annotated images)
  - [ ] `DartRemovedEvent` dataclass
- [ ] Integrate fusion into main loop:
  - [ ] After per-camera detection
  - [ ] Fuse coordinates
  - [ ] Derive score
  - [ ] Create `DartHitEvent`
  - [ ] Log event
- [ ] Update logging:
  - [ ] Log fused coordinates
  - [ ] Log derived score
  - [ ] Log which cameras contributed

#### Verification:
- [ ] Test throws at known targets (bull, T20, D16, etc.)
- [ ] Compare detected score with ground truth
- [ ] Inspect annotated images for misdetections
- [ ] Check fusion logic with single vs. multiple camera detections

#### Success Criteria:
- Fused coordinates reasonable for test throws
- Score derivation matches expectation in >60% of cases
- Clear correlation between detection quality and accuracy

#### Notes:
- Winmau Blade 6 dimensions (verify):
  - Bull: 12.7mm diameter (6.35mm radius)
  - Single bull: 31.8mm diameter (15.9mm radius)
  - Triple ring: inner 99mm, outer 107mm
  - Double ring: inner 162mm, outer 170mm
- Sector angles: 20° wedges, starting at -9° for sector 20

---

### ⬜ Step 8: Event State Machine (Throw vs Pull-Out)
**Status**: NOT STARTED  
**Goal**: Recognize throw sequence: idle → impact → dart present → pull-out → idle

#### Tasks:
- [ ] Add state machine config to `config.toml`:
  - [ ] Settled timeout (ms)
  - [ ] Pull-out motion threshold
  - [ ] Pull-out timeout (ms)
- [ ] Implement `events/state_machine.py`:
  - [ ] `DartboardState` enum: Idle, ThrowInProgress, DartPresent, PullOutInProgress
  - [ ] `StateMachine` class:
    - [ ] Current state tracking
    - [ ] Transition logic
    - [ ] Timeout handling
  - [ ] Transitions:
    - [ ] Idle → ThrowInProgress: strong motion detected
    - [ ] ThrowInProgress → DartPresent: motion settled + dart detected
    - [ ] DartPresent → PullOutInProgress: motion near dart location
    - [ ] PullOutInProgress → Idle: motion stopped + dart gone
  - [ ] Event emission:
    - [ ] Emit `DartHitEvent` on enter DartPresent
    - [ ] Emit `DartRemovedEvent` on enter Idle from PullOutInProgress
- [ ] Integrate state machine into main loop:
  - [ ] Feed motion detection results
  - [ ] Feed dart detection results
  - [ ] Handle state transitions
  - [ ] Emit events
- [ ] Update logging:
  - [ ] Log state transitions
  - [ ] Log event emissions

#### Verification:
- [ ] Test full sequence: throw → settle → pull-out
- [ ] Verify state transitions match physical actions
- [ ] Confirm exactly one DartHitEvent and one DartRemovedEvent per throw
- [ ] Test with 3 consecutive darts

#### Success Criteria:
- Consistent state flow for each throw
- Events emitted at correct times
- No missed or duplicate events
- Handles 3-dart sequence correctly

#### Notes:
- Pull-out detection may need tuning (motion threshold, location)
- Consider dart location history for pull-out validation

---

### ⬜ Step 9: Web API (FastAPI + WebSockets) and Logging
**Status**: NOT STARTED  
**Goal**: Expose events over network, provide metrics and health endpoints

#### Tasks:
- [ ] Add server config to `config.toml`:
  - [ ] Host (default: 0.0.0.0)
  - [ ] Port (default: 8000)
  - [ ] WebSocket endpoint path (default: /ws)
  - [ ] Enable debug JPEG endpoints (optional)
- [ ] Implement `server/pubsub.py`:
  - [ ] Simple pub/sub for event broadcasting
  - [ ] Or use `fastapi-websocket-pubsub` library
- [ ] Implement `server/api.py`:
  - [ ] FastAPI app initialization
  - [ ] REST endpoints:
    - [ ] `GET /health`: service status, per-camera FPS
    - [ ] `GET /metrics`: detection counts, latency, FPS
    - [ ] Optional: `GET /debug/camera/{id}/latest`: latest frame as JPEG
  - [ ] WebSocket endpoint:
    - [ ] `GET /ws`: client connection
    - [ ] Broadcast events as JSON
  - [ ] Event serialization (JSON):
    - [ ] DartHitEvent format
    - [ ] DartRemovedEvent format
- [ ] Integrate server with main loop:
  - [ ] Run FastAPI with uvicorn in separate thread
  - [ ] Publish events to WebSocket clients
  - [ ] Update metrics on each event
- [ ] Enhance logging:
  - [ ] JSON structured logs
  - [ ] Per-event logging with full details
  - [ ] FPS and timing metrics
  - [ ] Error logging
- [ ] Implement image persistence:
  - [ ] Save raw frames per throw
  - [ ] Save annotated frames per camera
  - [ ] Save diff masks
  - [ ] Organize by timestamp/throw ID
  - [ ] Include image paths in events

#### Verification:
- [ ] Start server and check `/health` endpoint
- [ ] Connect WebSocket client (Python script or browser)
- [ ] Verify events received in real-time
- [ ] Check `/metrics` for accurate counts
- [ ] Inspect saved images for each throw

#### Success Criteria:
- Stable WebSocket connection
- Events delivered in real-time
- REST endpoints return correct data
- Images saved and accessible
- Logs structured and complete

#### Notes:
- Use uvicorn with `--reload` in dev mode
- WebSocket JSON format should be well-documented
- Consider CORS settings for browser clients

---

### ⬜ Step 10: POC Validation Plan
**Status**: NOT STARTED  
**Goal**: Validate complete system with test session

#### Tasks:
- [ ] Prepare validation session:
  - [ ] Plan 50-100 test throws
  - [ ] Target various sectors (T20, T19, bull, doubles, etc.)
  - [ ] Manually log intended target and actual result
- [ ] Run validation session:
  - [ ] System running with all components
  - [ ] Record all events and images
  - [ ] Note any errors or anomalies
- [ ] Offline analysis:
  - [ ] Compare detected scores vs. ground truth
  - [ ] Calculate accuracy metrics:
    - [ ] Exact match rate
    - [ ] Sector accuracy
    - [ ] Ring accuracy
  - [ ] Inspect misdetections:
    - [ ] Review annotated images
    - [ ] Identify failure modes (lighting, occlusion, etc.)
  - [ ] Analyze detection latency
- [ ] Tuning and adjustment:
  - [ ] Adjust thresholds based on failure analysis
  - [ ] Refine homography if systematic errors
  - [ ] Optimize camera positions if needed
- [ ] Document results:
  - [ ] Accuracy report
  - [ ] Known limitations
  - [ ] Recommendations for Phase 2

#### Verification:
- [ ] System runs for full session without crashes
- [ ] All throws detected and logged
- [ ] Images saved for all throws
- [ ] Accuracy metrics computed

#### Success Criteria:
- System consistently detects throws and pull-outs
- Events emitted with plausible coordinates and scores
- Annotated images show correct tip overlay in most cases
- Accuracy >60% for POC (exact score match)
- Clear path to improvement identified

#### Notes:
- POC success is about proving the pipeline, not final accuracy
- Focus on identifying systematic issues
- Document all findings for Phase 2 planning

---

## Technical Decisions Log

### Camera Settings
- **Format**: MJPEG (lower USB bandwidth, acceptable CPU decode on Pi 4)
- **Resolution**: Start 800×600, test 1280×720 if stable
- **FPS**: Target 25 FPS per camera
- **Exposure**: Fixed manual exposure to handle LED ring brightness

### Calibration Approach
- **Intrinsic**: One-time chessboard calibration per camera
- **Extrinsic**: ARUCO markers for automatic homography at startup
- **Coordinate System**: Board center (0,0), +X right, +Y up, units in mm

### Configuration
- **Format**: TOML
- **Location**: `./config.toml` in project root
- **Override**: `--config` command-line flag

### Development Mode
- **Flag**: `--dev-mode`
- **Features**:
  - Preview windows on Mac
  - More verbose logging
  - Save all debug images
  - Single-camera testing option

---

## Dependencies

### Core
- `opencv-python` or `opencv-python-headless` (headless for Pi, full for Mac dev)
- `numpy`
- `fastapi`
- `uvicorn[standard]`
- `python-multipart`
- `websockets`

### Optional
- `fastapi-websocket-pubsub` (WebSocket pub/sub)
- `pydantic` (data validation)
- `toml` or `tomli` (TOML parsing)
- `psutil` (CPU/memory monitoring)

### Development
- `pytest` (testing)
- `black` (code formatting)
- `ruff` (linting)

---

## Project Structure

```
arudart/
├── config.toml
├── pyproject.toml or requirements.txt
├── README.md
├── project.md
├── IMPLEMENTATION_PLAN.md (this file)
├── calibration/
│   ├── intrinsic_cam0.json
│   ├── intrinsic_cam1.json
│   ├── intrinsic_cam2.json
│   ├── calibrate_intrinsics.py
│   └── chessboard_pattern.pdf (to print)
├── markers/
│   └── aruco_markers.pdf (to print)
├── src/
│   ├── main.py
│   ├── config.py
│   ├── camera/
│   │   ├── __init__.py
│   │   ├── camera_manager.py
│   │   └── camera_stream.py
│   ├── calibration/
│   │   ├── __init__.py
│   │   ├── intrinsic.py
│   │   ├── extrinsic.py
│   │   └── markers.py
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── background_model.py
│   │   ├── motion_detection.py
│   │   ├── dart_detection.py
│   │   └── coordinate_mapping.py
│   ├── events/
│   │   ├── __init__.py
│   │   ├── state_machine.py
│   │   └── event_model.py
│   ├── server/
│   │   ├── __init__.py
│   │   ├── api.py
│   │   └── pubsub.py
│   └── util/
│       ├── __init__.py
│       ├── logging_setup.py
│       └── metrics.py
├── logs/
│   └── (runtime logs)
├── data/
│   └── throws/
│       └── (saved images per throw)
└── tests/
    └── (unit tests)
```

---

## Next Actions

1. **Start Step 1**: Single-camera capture implementation
2. **Create project structure**: directories and initial files
3. **Set up dependencies**: `requirements.txt` or `pyproject.toml`
4. **Implement basic camera capture**: `CameraStream` and `CameraManager`

---

## Notes & Observations

- LED ring brightness requires fixed exposure control
- Multi-dart tracking needs background model update after each throw
- ARUCO markers will simplify calibration significantly
- Dev mode on Mac allows faster iteration before Pi deployment
- Pull-out detection is critical for complete flow but can be simplified initially

---

## Questions & Blockers

None currently - ready to start implementation.
