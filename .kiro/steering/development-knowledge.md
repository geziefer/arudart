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
✅ **Use moderate threshold (15)**: Filters noise, keeps dart signal (20-50px difference)
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
diff_threshold = 15        # High threshold (try first)
blur_kernel = 3
min_dart_area = 50
max_dart_area = 10000
min_shaft_length = 15
aspect_ratio_min = 1.2

[dart_detection.per_camera]
cam0 = { diff_threshold = 8 }  # Low threshold fallback
cam1 = { diff_threshold = 8 }
cam2 = { diff_threshold = 8 }
```

### Shape Filters
- Circularity < 0.8 (reject circular board features)
- Solidity > 0.4 (reject hollow wires)
- Aspect ratio > 1.0 (elongated shape)

## Testing Workflow

### Manual Testing Mode
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

## Performance Metrics

- **Detection Rate**: 94% (single-camera), 88% (multi-camera)
- **Tip Accuracy**: >90% (correct end identified)
- **Processing Time**: ~50-100ms per detection
- **Multi-camera Coverage**: 100% (≥1 camera), 75% (≥2 cameras)

## Common Issues & Solutions

### Issue: Camera auto-adjustments re-enabling
**Solution**: Re-apply camera settings before each detection

### Issue: Flight with gaps not detected
**Solution**: Larger closing kernels (15x15, 21x21, 27x27, 35x35)

### Issue: Tip detected at wrong end
**Solution**: Y-coordinate heuristic (primary), widest-part algorithm (fallback)

### Issue: Board noise larger than dart
**Solution**: Shape-based scoring instead of size-based selection


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
- `--verify-calibration`: Run verification script

**Keyboard shortcuts in dev mode**:
- `c`: Trigger manual calibration, reload coordinate mapper
- `v`: Toggle spiderweb overlay (projected board grid on camera view)

**Runtime behavior**:
- CoordinateMapper initializes after camera setup, loads existing calibration JSONs
- After each dart detection, pixel coords are transformed to board coords and logged
- Scoring skipped when CalibrationManager state is "calibrating"
- Spiderweb overlay cached per camera, invalidated on recalibration
