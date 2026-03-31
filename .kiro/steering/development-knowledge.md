---
inclusion: always
---

# Development Knowledge & Best Practices

## Critical Lessons Learned

### Camera Control

❌ **NEVER use OpenCV camera control on macOS** - `cv2.CAP_PROP_EXPOSURE` doesn't work
✅ **Use platform-specific tools**: uvc-util (macOS), v4l2-ctl (Linux)
✅ **Per-camera tuning required**: Each camera sees different lighting based on angle

### Detection Thresholds

❌ **NEVER use very low diff threshold (5)** - captures massive board noise
❌ **Threshold 15 too low for live throws** - sensor noise creates thousands of false contours
✅ **Use threshold 25**: Better signal-to-noise ratio for thrown darts (raised from 15)
✅ **Shape-based scoring**: `score = area × aspect_ratio × (1 - circularity)`

### Tip Identification

❌ **NEVER use board-center heuristic** - tip position relative to center depends on dart location
❌ **NEVER use endpoint width comparison** - fails when tip embedded
✅ **PRIMARY: Y-coordinate heuristic** - tip always has larger Y than flight (embedded vs sticking out)
✅ **FALLBACK: Widest-part algorithm** - find flight (widest), take opposite end as tip

### Morphological Operations

❌ **Small closing kernels (11x11)** - can't bridge large gaps
✅ **Progressive closing**: 15x15, 21x21, 27x27, 35x35 (multiple passes)
✅ **Multi-blob fallback**: Handle disconnected flight/shaft

### Multi-Camera Behavior

- **Geometric blind spots expected**: 120° spacing creates edge-on views
- **At least 2/3 detection rate**: 75% of throws should have ≥2 cameras
- **Tip position error systematic**: 20-30px offset, correctable by fusion
- **Previous dart masking disabled**: In multi-camera mode, fusion handles duplicates

### Dart Flight Color

❌ **Black flights** - blend with dark board areas, weak diff signal, causes false contour selection
✅ **Colored/bright flights** - strong contrast in image differencing, dramatically improves detection
- Switching from black to colored flights improved live throw accuracy from 54% to 94%

### Camera-Specific Issues

- **cam1 light ring**: cam1 (lower right) has the LED light ring visible in its upper portion (~88 rows)
- The bright light ring area creates noise in image differencing
- **Auto-masked**: DartDetector automatically detects and masks bright rows (mean > 100) in the top quarter
- **cam1 sensor noise**: cam1 has higher frame-to-frame noise than cam0/cam2 (likely due to lower exposure)

### Live Throw vs Manual Placement

- **Manual placement**: 100% accuracy (clean pre/post frames, no motion artifacts)
- **Live throws**: ~94% accuracy with colored flights (was 54% with black flights)
- Key difference: live throws have sensor noise, camera vibration from impact, and the dart in flight
- The Canny edge detection OR step in dart_detection.py adds board edges that create false contours — considered for removal but kept for now
- **persistent_change stays True** while dart is in board — state machine must suppress motion during settling

## Code Patterns

### Main Loop Structure

```python
while True:
    # 1. Get frames from all cameras
    frames = {cam_id: camera_manager.get_latest_frame(cam_id) for cam_id in camera_ids}
    
    # 2. Check motion (if not paused)
    if not paused and background_initialized:
        persistent_change, per_camera_motion, max_motion = motion_detector.detect_persistent_change(...)
        
        # State machine: idle → motion_detected → dart_detected → idle
        if motion_state == "idle" and persistent_change:
            motion_state = "motion_detected"
        elif motion_state == "motion_detected" and not persistent_change:
            motion_state = "dart_detected"
        elif motion_state == "dart_detected":
            # Run detection on all cameras
            # Save images
            # Update background
            motion_state = "idle"
    
    # 3. Display frames in dev mode
    # 4. Handle keypresses
```

### Per-Camera Detection Pattern

```python
for camera_id in camera_ids:
    pre_frame = background_model.get_pre_impact(camera_id)
    post_frame = background_model.get_post_impact(camera_id)
    
    tip_x, tip_y, confidence, debug_info = dart_detectors[camera_id].detect(
        pre_frame, post_frame, mask_previous=False
    )
    
    if tip_x is not None:
        detections.append((camera_id, tip_x, tip_y, confidence))
```

### Two-Step Threshold Approach

```python
# Step 1: Try high threshold first (clean detection)
tip_x, tip_y, confidence, debug_info = detect_with_threshold(pre, post, threshold=15)

# Step 2: If nothing found, retry with low threshold (catch weak signals)
if tip_x is None:
    low_threshold = per_camera_thresholds.get(camera_id, 15)  # e.g., 8
    if low_threshold < 15:
        tip_x, tip_y, confidence, debug_info = detect_with_threshold(pre, post, threshold=low_threshold)
```

## Configuration Values (Tuned)

### Camera Settings
```toml
[camera_settings]
width = 800
height = 600
fps = 25
fourcc = "MJPG"

[camera_control.per_camera]
cam0 = { exposure_time_ms = 3.7, contrast = 30, gamma = 250 }
cam1 = { exposure_time_ms = 3.2, contrast = 30, gamma = 200 }
cam2 = { exposure_time_ms = 3.5, contrast = 30, gamma = 380 }
```

### Detection Parameters
```toml
[dart_detection]
diff_threshold = 25        # Raised from 15 — reduces sensor noise for live throws
blur_kernel = 3
min_dart_area = 50
max_dart_area = 10000
min_shaft_length = 15
aspect_ratio_min = 1.0     # Lowered from 1.2

[dart_detection.per_camera]
cam0 = { diff_threshold = 8 }  # Low threshold fallback
cam1 = { diff_threshold = 8 }
cam2 = { diff_threshold = 8 }
```

### Fusion Parameters
```toml
[fusion]
outlier_threshold_mm = 25.0       # Tightened from 50.0
pairwise_rejection_mm = 20.0      # For 2-camera case
min_confidence = 0.3
angular_falloff = 1.0             # Cosine-based angular weighting
[fusion.camera_anchors]
cam0 = 81    # degrees
cam1 = 257
cam2 = 153
```

### Shape Filters
- Circularity < 0.8 (reject circular board features)
- Solidity > 0.4 (reject hollow wires)
- Aspect ratio > 1.0 (elongated shape)

## Testing Workflow

### Manual Placement Mode (place dart by hand)
```bash
python main.py --manual-dart-test --dev-mode
```
Cycle: stabilize → "PUT IN NOW" countdown → detect → show result → "REMOVE DART" → repeat

### Throw Mode (motion-detected single darts)
```bash
python main.py --single-dart-test --dev-mode
```
Cycle: stabilize → "THROW NOW" → wait for motion → detect → show result → repeat

### State Machine Mode (3-dart rounds with pull-out)
```bash
python main.py --state-machine --dev-mode
```
Full game cycle: WaitForThrow → ThrowDetected → score displayed → 3 darts → ThrowFinished → pull out → 2s cooldown → next round

### Accuracy Test Mode (known positions)
```bash
# Original 14-position set (DB, SB, T/D/BS/SS for sectors 20, 1, 5)
python main.py --accuracy-test --dev-mode

# Per-ring test (all 20 sectors)
python main.py --accuracy-test --ring T --dev-mode   # Triples
python main.py --accuracy-test --ring D --dev-mode   # Doubles
python main.py --accuracy-test --ring BS --dev-mode  # Big singles
python main.py --accuracy-test --ring SS --dev-mode  # Small singles
```

### Feedback Mode (confirm/correct scores)
```bash
# With manual placement
python main.py --manual-dart-test --feedback-mode --dev-mode

# With thrown darts
python main.py --single-dart-test --feedback-mode --dev-mode
```
After each detection: shows score + "Correct? (y)es / (n)o" on CV window

### Feedback Analysis Scripts
```bash
PYTHONPATH=. python scripts/analyze_feedback.py        # Accuracy report
PYTHONPATH=. python scripts/generate_heatmaps.py       # Heatmap images
PYTHONPATH=. python scripts/export_dataset.py           # ML dataset CSV
```

### Manual Testing Mode (legacy)
```bash
python main.py --dev-mode --manual-test
```

1. Press 'r' to capture clean background
2. Press 'p' to pause
3. Place dart manually
4. Press 'p' to detect
5. Remove dart, press 'r' to reset

### Recording Mode (Regression Tests)
```bash
python main.py --dev-mode --record-mode
```

1. Press 'r' to capture PRE frame
2. Place dart
3. Press 'c' to capture POST frame
4. Type description (e.g., "T20")
5. Repeat for next recording

### All CLI Flags Reference
```
--config PATH          Config file (default: config.toml)
--dev-mode             Enable preview windows
--manual-test          Legacy manual test (pause/place/detect)
--record-mode          Capture images for regression tests
--single-camera N      Test single camera (0, 1, or 2)
--calibrate            Run manual calibration at startup
--calibrate-intrinsic  Run chessboard calibration
--verify-calibration   Run calibration verification
--single-dart-test     Throw mode (motion-detected)
--manual-dart-test     Manual placement mode (countdown)
--state-machine        3-dart round mode with pull-out
--diagnostics          Enable diagnostic JSON logging
--accuracy-test        Accuracy test against known positions
--ring T|D|BS|SS       Ring filter for accuracy test
--feedback-mode        Enable score confirmation UI
```

## Performance Metrics

- **Manual placement accuracy**: 100% (20/20 throws, all rings)
- **Live throw accuracy**: 94% (17/18 throws with colored flights)
- **Per-ring accuracy (manual, all 20 sectors)**:
  - Triples: 100% (20/20), mean error 2.4mm
  - Big singles: 100% (20/20), mean error 5.6mm
  - Small singles: 100% (20/20), mean error 13.2mm
  - Doubles: 80% (16/20), mean error 13.8mm — hardest ring (board edge)
- **Camera coverage**: 44% 3-camera, 33% 2-camera, 22% 1-camera (live throws)
- **Processing Time**: ~50-100ms per detection
- **Fusion improvements**: Pairwise rejection (20mm), angular weighting, 25mm outlier threshold

## Common Issues & Solutions

### Issue: Camera auto-adjustments re-enabling
**Solution**: Re-apply camera settings before each detection

### Issue: Flight with gaps not detected
**Solution**: Larger closing kernels (15x15, 21x21, 27x27, 35x35)

### Issue: Tip detected at wrong end
**Solution**: Y-coordinate heuristic (primary), widest-part algorithm (fallback)

### Issue: Board noise larger than dart
**Solution**: Shape-based scoring instead of size-based selection

### Issue: Black flights invisible on dark board areas
**Solution**: Use colored/bright flights — improved live accuracy from 54% to 94%

### Issue: cam1 light ring creates noise
**Solution**: Auto-masking of bright rows in DartDetector (rows with mean > 100 excluded)

### Issue: Doubles ring boundary precision (170mm board edge)
**Solution**: No tolerance buffer added (would cause false doubles). Accept ~80% accuracy on doubles.

### Issue: False throw detection after pull-out
**Solution**: 2s cooldown after pull-out with continuous background updates during cooldown

### Issue: State machine settling — persistent_change stays True while dart in board
**Solution**: Suppress motion_detected while in ThrowDetected and PullOutStarted states


## Step 6: Coordinate Mapping - Feature Detection Success

### Bull Detection Algorithm (100% Accuracy)

**Problem**: Initial color-based detection was picking up red/green segments in triple/double rings instead of actual bull.

**Solution**: Multi-strategy approach with STRICT validation requiring BOTH red AND green colors.

**Key Insight**: The bull has BOTH red (double bull) AND green (single bull) colors simultaneously, while triple/double ring segments only have ONE color. This strict validation eliminates false positives.

**Implementation**:
1. **Strategy 1 (PRIMARY)**: Geometric center from line intersections
   - Uses HoughLinesP to detect sector boundaries
   - Computes intersection points (where radial lines converge)
   - Finds median of intersection cluster near image center
   - VALIDATES with strict color check: must have BOTH red AND green (≥3% each in 25px radius)

2. **Strategy 2**: Hough circles with same strict validation
   - Detects circles (radius 8-35px)
   - Tries each circle starting with closest to image center
   - VALIDATES: must have BOTH red AND green colors

3. **Strategy 3 (FALLBACK)**: Color-based detection
   - Uses AND operation on red and green masks (not OR)
   - Bull must have BOTH colors simultaneously

**Results**: 100% accurate bull detection across all 60 test images (20 per camera)
- cam0 (upper right): Always correct via geometric center
- cam1 (lower right): Usually geometric center, sometimes Hough circles
- cam2 (left, angled): Mix of geometric center and Hough circles

### Sector Boundary Detection - Adaptive Threshold

**Problem**: Fixed 75th percentile threshold was too high for cam2's angled perspective, resulting in 0 boundaries detected.

**Solution**: Adaptive threshold approach that tries progressively lower percentiles (75%, 70%, 65%, 60%, 55%, 50%) until ≥8 peaks are found.

**Implementation**:
- Uses edge detection on grayscale (more reliable than pure color segmentation)
- Creates angular histogram of edge points (360 bins, 1° per bin)
- Smooths histogram with moving average
- Tries progressively lower percentile thresholds until sufficient peaks found
- Detects local maxima in histogram as sector boundaries

**Results**:
- cam0: 12 boundaries detected ✅
- cam1: 9 boundaries detected ✅
- cam2: 8 boundaries detected ✅ (was 0 before fix)

### Manual Calibration Verification Results

Verification script tested 13 known board points per camera (bull, T20, T1, T5, D20, D1, D5, BS20, BS1, BS5, SS20, SS1, SS5).

**Results**:
- cam0: avg 2.61mm error, max 6.47mm — PASS
- cam1: avg 2.66mm error, max 6.51mm — PASS
- cam2: avg 4.49mm error, max 9.02mm — PASS
- All cameras under 5mm average error target
- Zero failures across all 39 measurements (13 per camera)

### main.py Integration Summary

**CLI flags added**:
- `--calibrate`: Run manual calibration before main loop
- `--calibrate-intrinsic`: Run intrinsic (chessboard) calibration
- `--verify-calibration`: Run calibration verification
- `--single-dart-test`: Throw mode (motion-detected single darts)
- `--manual-dart-test`: Manual placement mode (countdown-based)
- `--state-machine`: 3-dart round mode with pull-out detection
- `--accuracy-test`: Test against known board positions
- `--ring T|D|BS|SS`: Filter accuracy test by ring type (all 20 sectors)
- `--feedback-mode`: Enable score confirmation UI (y/n in CV window)
- `--diagnostics`: Enable per-throw JSON diagnostic logging

**Keyboard shortcuts in dev mode**:
- `c`: Trigger manual calibration, reload coordinate mapper
- `v`: Toggle spiderweb overlay (projected board grid on camera view)

**Runtime behavior**:
- CoordinateMapper initializes after camera setup, loads existing calibration JSONs
- After each dart detection, pixel coords are transformed to board coords and logged
- Scoring skipped when CalibrationManager state is "calibrating"
- Spiderweb overlay cached per camera, invalidated on recalibration
