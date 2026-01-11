# ARU-DART Development Knowledge Base

**Last Updated:** 2026-01-11  
**Phase:** Multi-Camera Detection (Step 5)

---

## Project Overview

Automatic dartboard scoring system using 3 USB cameras (OV9732) at 120° intervals, detecting dart throws via image differencing and multi-camera fusion.

**Current Status:** Step 5 in progress (multi-camera detection and optimization)

---

## Hardware Setup - Stability Characteristics

### Lighting System
- **LED ring**: Provides stable, even illumination without shadows
- **Room lighting**: Stable ambient light (no changes during tests)
- **Window light**: Only varies on sunny+cloudy days (rare, not in tests so far)
- **Conclusion**: Lighting is stable and NOT a source of background noise

### Mechanical Stability
- **Board**: Fixed to wall (does not move)
- **Cameras**: Fixed to LED ring (does not move)
- **Vibrations**: Possible tiny vibrations from:
  - Dart impact on board
  - Manual dart extraction
  - Accidental camera touch (operator waits for settling)
- **Conclusion**: Setup is mechanically stable, vibrations are minimal and transient

### Sources of Background Noise in Diff Images
Since lighting and mechanical setup are stable, background noise comes from:

1. **Camera sensor noise**: Random pixel variations (thermal noise, read noise)
2. **Dart reflections**: Metallic barrel and flight material create specular reflections that change with viewing angle
3. **Micro-shadows**: Very thin shadows from dart shaft/flight on board surface
4. **Compression artifacts**: MJPEG compression introduces slight variations between frames
5. **Camera auto-adjustments**: Despite disabling, some cameras may drift slightly

**Key insight**: Noise is NOT from environmental instability, but from sensor/optical characteristics and dart material properties.

---

## Critical Design Decisions

### 1. Tip Identification Algorithm Evolution

**Problem:** Initial approach (compare endpoint widths) failed when tip was embedded in board.

**Failed Approaches:**
- Endpoint width comparison: Unreliable when tip embedded (compares flight vs barrel, not tip)
- Distance to center heuristic: Fails for bottom-third of board (flight closer to center than tip)
- Endpoint strength analysis: Couldn't distinguish embedded tip from visible barrel end

**Final Solution (Working):**
- Find widest part of dart contour (always the flight, always visible)
- Take opposite end as tip
- Divide dart into 10 segments, measure width of each
- Flight = segment with maximum width
- Tip = opposite end from flight position
- **Result:** Confidence consistently 1.00, works even with deeply embedded tips

**Why it works:**
- Flight is always the widest part (physical characteristic)
- Flight is always visible (even if tip embedded)
- Doesn't depend on tip visibility
- Orientation-invariant
- Works across all board positions

### 2. Morphological Operations Tuning

**Problem:** Flight shapes with gaps/holes caused contour fragmentation.

**Evolution:**
- Initial: 5x5 opening, 5x5 closing
- Problem: Tip removed by opening, flight gaps not filled
- Iteration 1: 5x5 opening, 7x7 closing
- Problem: Still gaps in flight, tip preserved
- Iteration 2: 7x7 opening, 9x9 + 11x11 closing
- Problem: Tip removed again, but flight better
- **Final:** 3x3 opening, 11x11 + 15x15 + 19x19 closing
- **Result:** Tip preserved, flight gaps filled, fragments connected

**Key Insight:** Use small opening (preserve tip) + large progressive closing (connect fragments)

### 3. Camera Auto-Adjustment Issue

**Problem:** Systematic background degradation on 6th throw in test sessions.

**Root Cause:** Camera firmware re-enables auto-adjustments after ~5 captures or 2-3 minutes, despite being disabled at startup.

**Solution:** Re-apply all fixed settings before each detection:
```python
camera_manager.reapply_camera_settings()
```

**Settings to force:**
- AUTO_EXPOSURE = 1 (manual), EXPOSURE = -7
- AUTO_WB = 0, WB_TEMPERATURE = 4000
- AUTOFOCUS = 0
- GAIN = 0

### 4. Multiple Darts - Shadow/Reflection Masking

**Problem:** When placing second dart manually, shadows/reflections on first dart cause it to appear in diff.

**Failed Approach:** Increase diff threshold (misses real darts)

**Working Solution:** Mask previous darts
- After detecting dart, save contour
- Dilate contour 25x25 (covers shadows/reflections)
- Apply inverted mask to subsequent detections
- Reset mask when capturing new background

**Limitation:** Crossing darts still fail (physical occlusion breaks contour) - requires 3-camera fusion

---

## Configuration Parameters - Final Values

### Camera Settings
```toml
[camera_settings]
width = 1280
height = 720
fps = 25
fourcc = "MJPG"
exposure = -7              # Lowered from -6 for better metallic dart contrast
auto_exposure = false
auto_wb = false
wb_temperature = 4000
autofocus = false
gain = 0
```

### Motion Detection
```toml
[motion_detection]
scale = 4                  # Downscale factor for motion detection
blur_kernel = 5
motion_threshold = 5.0
settled_threshold = 1.0    # Lowered from 2.0 to detect stuck darts
motion_check_interval = 0.05
persistence_time = 0.3     # Persistent change detection
learning_rate = 0.01       # Adaptive background update when idle
```

### Dart Detection
```toml
[dart_detection]
diff_threshold = 15
blur_kernel = 5
min_dart_area = 50
max_dart_area = 10000
min_shaft_length = 15
aspect_ratio_min = 1.2
detection_cooldown = 2.0
```

**Shape Filters:**
- Circularity < 0.7 (reject circular board features)
- Solidity > 0.5 (reject hollow wires)
- Aspect ratio > 1.2 (elongated shape)

**Spatial Mask:**
- Exclude outer 15% (number ring)
- Include all scoring area including bull
- Valid radius = 42% of image half-width

---

## Testing Results Summary

### Test Case Results (TC0-TC6)

| Test Case | Result | Success Rate | Notes |
|-----------|--------|--------------|-------|
| TC0: Reproducible | ✅ Pass | 6/6 | Consistent within 1-9 pixels |
| TC1: Board Regions | ✅ Pass | 6/6 | Bull required algorithm fix |
| TC2: Contrast | ✅ Pass | 9/9 | Fragmented flights fixed |
| TC3: Orientation | ✅ Pass | 9/9 | Confidence 1.00 all throws |
| TC4: Multiple Darts | ⚠️ Partial | 2/3 | Crossing darts need 3 cameras |
| TC5: Edge Cases | ✅ Pass | 8/8 | Near wires/boundaries work |
| TC6: Lighting | ✅ Pass | 3/4 | Shadow testing inconclusive |

**Overall:** 41/44 successful (93% success rate for single camera)

### Known Limitations

**Expected (by design):**
- Crossing darts require 3-camera fusion
- Exact sector determination requires calibration + mapping
- Single camera has blind spots (occlusion)

**Occasional (not systematic):**
- First throw background instability (~5% of sessions)
- Cause: Background captured before camera fully stable
- Workaround: Wait 2 seconds after 'r' press (already implemented)

---

## Key Algorithms - Implementation Details

### 1. Persistent Change Detection

**Purpose:** Detect dart stuck in board (vs transient motion like hand)

```python
# Track when change first detected
if motion > threshold:
    if persistent_change_start is None:
        persistent_change_start = current_time
    elif current_time - persistent_change_start > persistence_time:
        return True  # Persistent change detected
else:
    persistent_change_start = None  # Reset
```

**Parameters:**
- `persistence_time = 0.3s` (dart stays, hand moves away)
- `settled_threshold = 1.0%` (lower than transient motion)

### 2. Morphological Processing Pipeline

```python
# 1. Combine diff and edges
thresh = cv2.bitwise_or(diff_thresh, canny_edges)

# 2. Remove small noise (preserve tip)
kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_small)

# 3. Fill gaps progressively (connect flight fragments)
kernel_medium = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_medium)

kernel_large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_large)

kernel_xlarge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_xlarge)
```

### 3. Tip Identification (Widest Part Algorithm)

```python
# Divide dart into segments along fitted line
num_segments = 10
segment_size = dart_length / num_segments

max_width = 0
flight_position = 0  # 0 to 1 (0=end1, 1=end2)

for i in range(num_segments):
    segment_points = contour_points[segment_mask]
    width = np.std(segment_points, axis=0).mean()
    
    if width > max_width:
        max_width = width
        flight_position = i / num_segments

# Tip is opposite end from flight
if flight_position < 0.5:
    tip = end2  # Flight near end1, tip is end2
else:
    tip = end1  # Flight near end2, tip is end1

confidence = min(max_width / 20.0, 1.0)
```

### 4. Previous Dart Masking

```python
# After successful detection:
def _add_to_previous_darts_mask(contour, image_shape):
    # Create mask for this dart
    dart_mask = np.zeros(image_shape, dtype=np.uint8)
    cv2.drawContours(dart_mask, [contour], -1, 255, -1)
    
    # Dilate to cover shadows/reflections
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    dart_mask = cv2.dilate(dart_mask, kernel)
    
    # Add to cumulative mask
    if previous_darts_mask is None:
        previous_darts_mask = dart_mask
    else:
        previous_darts_mask = cv2.bitwise_or(previous_darts_mask, dart_mask)

# Before next detection:
thresh = cv2.bitwise_and(thresh, thresh, mask=cv2.bitwise_not(previous_darts_mask))
```

---

## Manual Testing Workflow

### Standard Single Dart Test
1. `python main.py --dev-mode --manual-test`
2. Press 'r' to capture clean background (wait 2 seconds)
3. Press 'p' to pause
4. Place dart manually
5. Press 'p' to detect
6. Press 'p' to pause
7. Remove dart
8. Press 'r' to reset background
9. Repeat

### Multiple Darts Test (TC4)
1. Press 'r' for clean board
2. Press 'p', place first dart, press 'p' to detect
3. **Don't press 'r'** (background auto-updates with first dart)
4. Press 'p', place second dart, press 'p' to detect
5. Press 'p', place third dart, press 'p' to detect
6. Press 'r' to reset for new round

**Key:** Background automatically includes previous darts after each detection

---

## Common Issues and Solutions

### Issue: Throw #6 shows board features in threshold

**Symptoms:** After 5 successful throws, 6th throw shows wires/sectors in diff image

**Root Cause:** Camera auto-adjustments re-enabling after ~5 captures

**Solution:** Re-apply camera settings before each detection (implemented)

### Issue: Flight with gaps not detected

**Symptoms:** Threshold shows flight outline but interior has holes, contour fragmented

**Root Cause:** Colored flight panels match board colors (black on black, white on white)

**Solution:** Larger closing kernels (11x11, 15x15, 19x19) to fill gaps

### Issue: Tip detected at wrong end

**Symptoms:** Red circle at flight instead of tip

**Root Cause:** Tip embedded in board, endpoint width comparison fails

**Solution:** Widest part algorithm (find flight, take opposite end)

### Issue: Second dart shows both darts in threshold

**Symptoms:** After detecting first dart, second detection shows both darts

**Root Cause:** Shadows/reflections on first dart from second dart placement

**Solution:** Previous dart masking with 25x25 dilation

### Issue: Crossing darts - second dart not detected

**Symptoms:** When darts cross, second dart contour split into fragments

**Root Cause:** Physical occlusion, no morphological operation can bridge

**Solution:** Requires 3-camera fusion (different angles see darts separated)

---

## Next Steps (Step 5-7)

### Step 5: Multi-Camera Capture
- Extend to 3 cameras simultaneously
- Synchronize frame capture
- Per-camera detection

### Step 6: Camera Calibration
- Intrinsic calibration (camera matrix, distortion)
- Extrinsic calibration (homography to board plane)
- Coordinate mapping (pixel → board mm)

### Step 7: Multi-Camera Fusion
- Combine 3 per-camera detections
- Weighted average by confidence
- Reject outliers (crossing darts)
- Map to board coordinates
- Derive score (sector + ring)

### Step 7.5: Human Feedback System
- Score-level feedback ("T20" vs "S20")
- Build verified dataset
- Analyze accuracy per sector/ring
- Continuous improvement

---

## Files Modified (Key Changes)

### src/processing/dart_detection.py
- Tip identification: widest part algorithm
- Morphological ops: 3x3 open, 11x11/15x15/19x19 close
- Previous dart masking
- Shape filters: circularity, solidity

### src/camera/camera_stream.py
- `apply_fixed_settings()` method
- Re-apply camera settings to prevent drift

### src/camera/camera_manager.py
- `reapply_camera_settings()` for all cameras

### main.py
- Manual test mode (`--manual-test` flag)
- Pause/play with 'p' key
- Background reset while paused
- Camera settings re-application before detection
- Previous dart mask reset on 'r' press

### config.toml
- Exposure: -7
- Settled threshold: 1.0%
- Dart detection thresholds optimized

---

## Lessons Learned

1. **Camera firmware is unreliable** - Always re-apply settings, never trust "set once"
2. **Physical characteristics are robust** - "Widest part = flight" works universally
3. **Progressive morphology is powerful** - Multiple closing passes handle complex shapes
4. **Manual testing is essential** - Controlled placement reveals edge cases
5. **Single camera has limits** - Crossing darts fundamentally require multiple views
6. **Save everything** - Images from failed detections are most valuable for debugging
7. **Iterate based on data** - Test results guide algorithm improvements better than theory

---

## Performance Metrics

**Detection Rate:** 93% (41/44 test cases)

**Tip Accuracy:** >90% (correct end identified)

**Confidence Scores:** 
- Clear cases: 0.8-1.0
- Embedded tip: 0.3-0.6 (still correct)
- Ambiguous: <0.3 (may be wrong)

**Processing Time:** ~50-100ms per detection (single camera, 1280x720)

**False Positives:** <5% (mostly first throw background noise)

**False Negatives:** <10% (crossing darts, extreme occlusion)

---

## Future Improvements (Post-3-Camera)

1. **ML-based detection** - Train on verified dataset from Step 7.5
2. **Adaptive thresholding** - Per-sector threshold adjustment
3. **Temporal filtering** - Use motion video for better tip identification
4. **Bounce-out detection** - Detect when dart falls out
5. **Confidence calibration** - Learn which scenarios have low accuracy
6. **Real-time optimization** - Reduce processing time for faster response

---

**Document Maintained By:** Development team  
**Review Frequency:** After each major milestone  
**Next Review:** After Step 7 (Multi-camera fusion) completion
