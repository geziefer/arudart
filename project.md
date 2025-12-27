# Project ARU-DART

This project should implement an automatic darts scoring system.
For that, 3 USB cameras are mounted around a standard steel dart board and are connected to a Raspberry Pi that does multi-camera capture, dart event detection, coordinate calculation, and pushes JSON events over WebSockets, plus logging and saving annotated images for verification.

## 1. Overall goals and constraints

- Hardware:
  - Raspberry Pi 4, active cooling, slightly overclocked.
  - Three HBV **OV9732 1 MP USB cameras**, 1280×720, MJPG/YUY2, ~100° FOV, each on its own USB port.
  - Winmau Blade 6 Triple Core board, cameras mounted around an LED ring at 120° (similar but not identical to Autodarts recommended geometry).

- Phase 1 backend requirements:
  - Run **headless** on Pi OS / Linux.
  - Use **Python + OpenCV** for camera capture and image processing.
  - Stable operation with “as high as feasible” resolution and FPS per camera (target around 20–30 FPS, but detection does not need fluent video).
  - Detect:
    - New dart hit (throw event).
    - Dart tip board position in board-centered coordinates (e.g. mm or normalized).
    - Dart removal (pull-out) after throw.
  - Expose events over **WebSockets** + optionally simple REST for health/metrics.
  - Persist logs and selected images (for visual validation of detection).

- Accuracy target for later:
  - Eventually around **≥ 99.0% correct sector/ring**.
  - Phase 1 only needs a **working POC** with reasonable detection, not final accuracy.

## 2. Project structure

Proposed Python package layout:

- `src/`
  - `main.py` – entrypoint, argument parsing, startup of all components.
  - `config.py` – configuration model and loading (YAML/TOML/JSON).
  - `camera/`
    - `camera_manager.py` – handles multiple cameras, spawns capture threads.
    - `camera_stream.py` – per-camera capture abstraction (OpenCV VideoCapture).
  - `calibration/`
    - `intrinsic.py` – camera intrinsic calibration tools.
    - `extrinsic.py` – board-plane calibration and homography/pose estimation.
    - `markers.py` – ARUCO/marker-based calibration helpers.
  - `processing/`
    - `background_model.py` – background and “board state” representation.
    - `motion_detection.py` – impact / motion detector (downscaled diff).
    - `dart_detection.py` – localized dart contour/line detection.
    - `coordinate_mapping.py` – map image coordinates to board coordinates.
  - `events/`
    - `state_machine.py` – state machine for idle → impact → settled → pullout.
    - `event_model.py` – Python dataclasses / Pydantic models for events.
  - `server/`
    - `api.py` – FastAPI app with REST + WebSocket endpoints.
    - `pubsub.py` – simple internal pub/sub for pushing events to WebSocket clients (or use `fastapi_websocket_pubsub`).
  - `util/`
    - `logging_setup.py` – configure structured logging.
    - `metrics.py` – FPS, per-stage timings, counters.

A simple `pyproject.toml` or `requirements.txt` should include at least:

- `opencv-python` (or `opencv-python-headless` if no GUI is needed).
- `numpy`
- `fastapi`
- `uvicorn[standard]`
- Optionally `fastapi-websocket-pubsub` for WebSocket pub/sub convenience.

## 3. Configuration model

Use a single config file (e.g. `config.toml`) to control runtime behaviour:

Key sections:

- `cameras`:
  - List of cameras, each with:
    - `device_index` (0, 1, 2).
    - `resolution` (e.g. 1280×720 or 800×600).
    - `fps` (target, e.g. 25).
    - `pixel_format` (MJPG preferred).
    - `flip` / `rotate` options if needed.
- `calibration`:
  - Paths to saved intrinsic parameters per camera.
  - Board radius and ring radii (mm) for Winmau Blade 6.
  - Option to enable ARUCO markers around the board.
- `detection`:
  - Motion detection downscale factor (like `motion/scale` in Autodarts).
  - Diff image threshold for motion and dart detection.
  - Gaussian blur kernel sizes for motion/dart detection.
  - Min/max dart size (area in pixels) and min shaft length for detection.
- `events`:
  - Timeout thresholds (time after impact to consider board “settled”).
  - How many frames to consider for pull-out detection.
- `server`:
  - Host/port for FastAPI.
  - WebSocket endpoint path.
  - Whether to serve optional debug JPEG endpoints.

## 4. Step-by-step implementation plan

### Step 1: Single-camera capture and FPS measurement

**Goal:** Robust capture from one OV9732, measure achievable FPS at chosen resolution.

Tasks:

1. Implement `CameraStream`:
   - Open `cv2.VideoCapture(device_index)`.
   - Set resolution and FPS with `CAP_PROP_FRAME_WIDTH`, `CAP_PROP_FRAME_HEIGHT`, `CAP_PROP_FPS`.
   - Set MJPEG via `CAP_PROP_FOURCC` if supported (e.g. `'MJPG'`).
   - Run a dedicated thread/class that continuously grabs the latest frame and stores it in a thread-safe field.
2. Implement `CameraManager`:
   - For now, manage only one camera.
   - Provide `get_latest_frame(camera_id)`.

Verification:

- A simple `main.py` that:
  - Starts `CameraManager` with 1 camera.
  - Periodically reads frames for 10 seconds and logs effective FPS.
- Log:
  - Capture FPS.
  - Resolution and CPU usage (rough, via `psutil` or just `top` externally).

Success criterion:

- Stable capture ~20–30 FPS with target resolution (start with 800×600; if stable, try 1280×720).

### Step 2: Multi-camera capture (3 cameras)

**Goal:** Capture from all three cameras concurrently, keep latest frame per camera.

Tasks:

1. Extend `CameraManager`:
   - Spawn three `CameraStream` instances (indices 0, 1, 2).
2. Implement a simple test script:
   - For each camera, pull the latest frame at a fixed rate and compute per-camera FPS.
   - Log per-camera FPS, CPU usage, dropped frames if any.

Verification:

- Confirm that you can run 3 cameras simultaneously at chosen resolution and FPS (likely 800×600 @ ~25 FPS per cam).
- If bandwidth/CPU is an issue, drop FPS or resolution until stable.

Success criterion:

- All 3 streams run concurrently without frequent timeouts or capture errors for several minutes.

### Step 3: Basic motion detection (impact detection) on downscaled frames

**Goal:** Detect when a throw has happened, independent of exact dart position.

Concept:

- Maintain a **background frame** (board without motion).
- Downscale frames strongly (e.g. main resolution / 4) for motion detection.
- Compute abs difference to detect large motion (hand + dart) and smaller motion (dart impact).

Tasks:

1. Implement `MotionDetector`:
   - Takes downscaled grayscale frames from each camera.
   - Maintains one or more reference frames (pre-throw).
   - Computes `cv2.absdiff`, thresholding, optional Gaussian blur.
   - Returns:
     - Boolean “motion detected”.
     - Possibly motion bounding box / mask per camera.
2. Integrate with `CameraManager`:
   - At a fixed motion-FPS (e.g. 10–15 FPS), build a combined motion signal across cameras:
     - “Impact” = significant motion detected on at least one camera, then dropping below a “settled” threshold.

Verification:

- Log motion detection events while you move your hand in front of the board and throw test darts.
- Ensure that:
  - Normal noise (light flicker) does not trigger motion.
  - Proper throws cause a clear motion event.

Success criterion:

- Motion detector reliably indicates start of a throw and “settled board” afterwards, even if not yet pinpointing the dart.

### Step 4: Dart detection in one camera (image differencing)

**Goal:** For proof of concept, detect the dart shaft/tip in one camera’s image after motion.

Concept (classical CV):

- Keep a pre-impact frame (board state before dart).
- After impact and board settling, capture a post-impact frame.
- Compute `diff = abs(post - pre)` in the full-resolution image, masked to board region.
- Apply threshold + morphology, then find elongated contour that represents the dart.

Tasks:

1. Implement `BackgroundModel`:
   - For each camera, maintain “board without this dart” reference.
   - In phase 1, simplest is:
     - For each new throw: pre-impact frame = last settled frame.
2. Implement `DartDetector` for a single camera:
   - Input: `pre_frame`, `post_frame` (color or grayscale).
   - Steps:
     - Convert to grayscale.
     - `absdiff`, thresholding (diff threshold from config).
     - Gaussian blur or morphology to reduce noise.
     - Find contours.
     - Filter by area (dart size min/max) and elongation (aspect ratio / bounding box).
     - Approximate orientation via PCA or `fitLine`.
     - Decide which end is “tip” (likely closer to board center).
   - Output:
     - Tip coordinates in image (u,v).
     - Confidence score.
     - Debug mask / image.

Verification:

- Test with one camera:
  - Log detected tip coordinates and overlay on saved image:
    - Save `post_frame` and a copy with a circle drawn at detected tip.
- You can inspect saved images manually to see if detection roughly matches the dart.

Success criterion:

- For a set of ~20–30 test throws in different sectors, the single-camera detector finds a plausible dart shaft and tip in the annotated images.

### Step 5: Extend dart detection to 3 cameras (per-camera detections)

**Goal:** For each throw, get per-camera tip detections.

Tasks:

1. For each camera:
   - Maintain pre-impact and post-impact frames as before.
2. Run `DartDetector` on each camera’s pair.
3. Collect results:
   - Some cameras may fail to detect (occlusion, low contrast).
   - Represent detection as:
     - `None` or invalid if no dart found.
     - Valid detection with tip coordinates and confidence otherwise.

Verification:

- For each throw:
  - Log which cameras detected the dart.
  - Save annotated images from all three cameras into a per-throw folder.
- Monitor detection rate per camera.

Success criterion:

- At least one camera consistently detects a reasonable dart tip location for most test throws.

### Step 6: Coordinate mapping (per-camera image → board plane)

**Goal:** Map each camera’s tip pixel coordinates to a common board coordinate system.

Assumptions:

- The board is a **fixed plane** with known center and radius; dart tips lie on this plane (ignoring tilt).
- Each camera can be calibrated with intrinsics + extrinsics to compute a homography (or full pose).

Tasks:

1. Intrinsic calibration:
   - Use OpenCV’s chessboard calibration for each camera to get:
     - Camera matrix, distortion coefficients.
   - Save per-camera intrinsics to `calibration/intrinsic_camX.json`.
2. Extrinsic calibration and homography:
   - Option A (simpler for phase 1): homography mapping from image plane to board plane.
     - Place 4+ markers on known positions around the board (e.g. a printed square / ARUCO markers at known offsets in board coordinates).
     - Manually click their positions in an image for each camera (or detect ARUCO corners automatically).
     - Use `cv2.findHomography` to compute homography `H_cam`.  
   - For each later detection:
     - Convert image point `[u, v, 1]` to board coordinates `[x, y, w] = H_cam * [u, v, 1]` and normalize.
3. Coordinate system:
   - Define board center `(0, 0)`.
   - Measure radii for bull, single, triple, double etc. in mm and store in config (Winmau standard).  
   - Optionally store board radius as 170 mm (standard 17" board diameter ~ 340 mm) and ring radii from board spec.

Verification:

- Manually mark known points (e.g. T20, D20, bull) in image and confirm mapped coordinates give the expected radius and angle.
- For each camera, log mapping error for these control points.

Success criterion:

- Homography-based mapping gives reasonable coordinates (e.g. T20 mapped to correct sector and triple ring band) when you do a manual test.

### Step 7: Multi-camera fusion and score derivation

**Goal:** Combine the three per-camera tip points into one best estimate in board coordinates; derive score (segment + ring).

Tasks:

1. For each throw:
   - For each camera:
     - If detection valid → map to board coordinates `(x_i, y_i)` with confidence `c_i`.
2. Fusion:
   - If only one camera has valid detection:
     - Use its coordinate.
   - If multiple cameras:
     - Simple starting point: weighted average of `(x_i, y_i)` by `c_i`.
     - Or median of coordinates to reject outlier.
3. Score mapping:
   - Compute radius `r` and angle `theta` from fused `(x, y)`.
   - Determine ring:
     - Compare `r` against bull, single, triple, double radii thresholds from config.
   - Determine sector:
     - Use atan2 to compute angle and map to the correct wedge (20, 1, 18, …).
   - Output:
     - Base number, multiplier, raw coordinates, and which cameras contributed.

Verification:

- For test throws aimed at known segments (e.g. bull, T20, D16), log:
  - Fused coordinates.
  - Derived score.
- Compare manually, aided by the annotated images.

Success criterion:

- For a small sample of throws, the fused score matches expectation at least often enough to show principle viability.

### Step 8: Event state machine (throw vs pull-out)

**Goal:** Recognize the sequence: idle → impact → board settled with new dart → pull-out → back to idle.

Tasks:

1. Implement `StateMachine` with states:
   - `Idle` (no motion, baseline board state).
   - `ThrowInProgress` (motion detected).
   - `DartPresent` (board settled, dart detected).
   - `PullOutInProgress` (motion detected while dart present).
2. Transitions:
   - `Idle` → `ThrowInProgress` when strong motion.
   - `ThrowInProgress` → `DartPresent` when motion falls below threshold and a dart is detected.
   - `DartPresent` → `PullOutInProgress` when motion detected near known dart location.
   - `PullOutInProgress` → `Idle` when motion stops and dart is gone.
3. Output events:
   - On transition into `DartPresent`: emit `DartHitEvent`.
   - On transition into `Idle` when previously `DartPresent`: emit `DartRemovedEvent`.

Verification:

- Log state transitions and events as you:
  - Throw a dart.
  - Leave it for a moment.
  - Pull it out.
- Confirm the sequence of events matches physical actions.

Success criterion:

- Reasonably consistent event flow per throw, with exactly one `DartHitEvent` and one `DartRemovedEvent`.

### Step 9: Web API (FastAPI + WebSockets) and logging

**Goal:** Expose detection and events over network; keep metrics and images for debugging.

Tasks:

1. Implement `FastAPI` server (`server/api.py`):
   - REST:
     - `GET /health` – returns service status and per-camera FPS.
     - `GET /metrics` – returns summary metrics (counts, average FPS, detection latency).
   - WebSocket:
     - `GET /ws` – clients connect and receive real-time events.
2. Event format (JSON) for WebSocket:
   - `DartHitEvent`:
     - `event_type`: `"dart_hit"`.
     - `timestamp`.
     - `board_coordinates`: `{ "x": float, "y": float }`.
     - `score`: `{ "base": int (1–20 or 25/50), "multiplier": int }`.
     - `camera_hits`: list per camera: image coordinates, confidence.
     - Optional: ID/path of saved annotated images for this throw.
   - `DartRemovedEvent`:
     - `event_type`: `"dart_removed"`.
     - `timestamp`.
     - Reference to previous hit event ID (if desired).
3. Logging:
   - Configure logging to:
     - Write JSON logs or structured logs.
     - Include FPS, detection timings, errors.
   - On each `DartHitEvent`:
     - Save:
       - Raw frames used for detection (or just post-impact).
       - Annotated versions with overlays.
       - Possibly a downscaled diff image.

Verification:

- Create a simple WebSocket test client (e.g. small Python script or browser client) that:
  - Connects to `/ws`.
  - Prints incoming events.
- Confirm events appear as you throw/pull darts.

Success criterion:

- Stable WebSocket connection delivering structured events for each detected throw.
- Metrics and images available for manual accuracy checks.

### Step 10: POC validation plan

Once all steps are implemented:

1. Record a session of, say, 50–100 throws:
   - Use a manual log of intended target (e.g. “aim T20, D16, bull”) and true result.
   - The backend should log detected scores plus store annotated images.
2. Offline analysis:
   - Compare detected scores vs ground truth.
   - Inspect misdetections using saved images to identify common failure modes (lighting, occlusions, orientation).
3. Adjust:
   - Diff thresholds, blur parameters, dart size limits, etc., similar to Autodarts config tuning.
   - Possibly refine homography or camera positions.

The **POC is considered successful** when:

- The system consistently:
  - Detects throws and pull-outs.
  - Emits events with plausible board coordinates and scores.
  - Provides images showing the overlaid tip on the dart in most cases.
- Actual accuracy can be <99% at this stage; the goal is to prove the pipeline and integration.
