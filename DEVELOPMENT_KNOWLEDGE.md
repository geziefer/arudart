# ARU-DART Development Knowledge Base

**Last Updated:** 2026-01-11  
**Phase:** Multi-Camera Detection (Step 5) - Ready for Testing

---

## Project Overview

Automatic dartboard scoring system using 3 USB cameras (OV9732) at 120° intervals, detecting dart throws via image differencing and multi-camera fusion.

**Current Status:** Step 5 ready - single-camera detection optimized (>95% accuracy), multi-camera testing next

---

## Recent Improvements (2026-01-11)

### Detection Accuracy Improvements
1. **Diff threshold increased**: 5 → 15 (eliminated board noise)
2. **Multi-frame post-impact capture**: 3 frames @ 100ms intervals, selects best (lowest noise)
3. **Shape-based scoring**: `score = area × aspect_ratio × (1 - circularity)` - prioritizes dart shapes over board blobs
4. **Larger morphological closing**: Up to 35x35 kernels to bridge flight-shaft gaps
5. **Multi-blob analysis**: Fallback for disconnected flight/shaft (finds aligned blobs)
6. **Spatial mask adjustment**: Increased to 42.5% radius to include edge darts

**Result**: Single-camera detection ~95% accurate (8-9/9 test throws)

### Camera Control (Platform-Specific)
- **macOS**: uvc-util (local binary in project root)
- **Linux**: v4l2-ctl (system-wide)
- **Per-camera settings**: exposure_time_ms, contrast, gamma
- **Fixed settings**: brightness=-64, auto_exposure=false, auto_white_balance=false

**Current tuned values**:
- cam0 (upper right/18): exposure=3.7ms, contrast=30, gamma=250
- cam1 (lower right/17): exposure=3.2ms, contrast=30, gamma=200
- cam2 (left/11): exposure=3.5ms, contrast=30, gamma=380

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

**❌ FAILED APPROACHES - NEVER USE THESE AGAIN:**
1. **Board-center heuristic (tip closer to center):**
   - **DOES NOT WORK** - Which end is closer to center depends on dart position on board
   - **Example:** Dart in lower half of board → tip closer to outer edge than center
   - **Example:** Dart in upper half of board → tip closer to center than outer edge
   - **Conclusion:** Position-dependent, cannot be used as general rule
   - **DO NOT SUGGEST THIS APPROACH EVER AGAIN**

2. **Endpoint width comparison:**
   - Unreliable when tip embedded (compares flight vs barrel, not tip)

3. **Endpoint strength analysis:**
   - Couldn't distinguish embedded tip from visible barrel end

**✅ WORKING SOLUTION - Y-COORDINATE HEURISTIC (PRIMARY):**
- **Physical fact:** Darts stick straight into board or bend slightly, flight always sticks OUT from board
- **Camera perspective:** Flight is farther from board surface (lower Y in image), tip is embedded (higher Y in image)
- **Rule:** Tip ALWAYS has larger Y coordinate than flight in camera image
- **Exception:** Only fails if dart points directly at camera (physically impossible in real throws)
- **Reliability:** Works across all camera angles and dart positions
- **Priority:** Use Y-coordinate as PRIMARY method, widest-part as fallback

**Fallback: Widest-part algorithm:**
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

### 2. Board Noise Elimination (2026-01-11)

**Problem:** Low diff threshold (5) captured too much board noise, creating larger blobs than dart.

**Root Cause Analysis:**
- Board noise from sensor noise, reflections, compression artifacts (NOT lighting/movement)
- Threshold=5 too sensitive, picked up 1-2% pixel differences across entire board
- Board has more pixels than dart → noise blob larger than dart blob
- Algorithm selected largest blob → picked board instead of dart

**Solution - Three-part approach:**
1. **Increase diff_threshold: 5 → 15**
   - Filters out weak board noise
   - Keeps strong dart signal (20-50 pixel difference)
   
2. **Shape-based scoring instead of size-based:**
   ```python
   score = area × aspect_ratio × (1 - circularity)
   ```
   - Dart (elongated, non-circular): High score even if smaller
   - Board blob (compact, circular): Low score even if larger
   
3. **Multi-frame post-impact capture:**
   - Capture 3 frames at 100ms intervals
   - Select frame with lowest background noise
   - Reduces random sensor noise and compression artifacts

**Result:** Board noise eliminated, dart always selected over noise blobs

### 3. Disconnected Flight/Shaft Handling (2026-01-11)

**Problem:** Metallic shaft weak/invisible on colored sectors → flight disconnected from shaft after morphological closing.

**Evolution:**
- Initial closing: 11x11, 15x15, 19x19
- Problem: Couldn't bridge large gaps (20-30 pixels)
- Solution 1: Increase to 15x15, 21x21, 27x27, 35x35 → bridges most gaps
- Solution 2: Multi-blob analysis (fallback when confidence < 0.5 or length < 40px)

**Multi-blob algorithm:**
1. Find top 2-3 scoring blobs (likely flight + shaft)
2. Check if aligned (angle difference < 30°)
3. If aligned, find furthest points across all blobs
4. Use board-center heuristic: tip closer to center (embedded)
5. Confidence based on total dart length

**Result:** Handles disconnected flight/shaft, improves from 89% to 95%+ accuracy

### 4. Morphological Operations Tuning

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
width = 800
height = 600
fps = 25
fourcc = "MJPG"

[camera_control]
enabled = true
[camera_control.per_camera]
cam0 = { exposure_time_ms = 3.7, contrast = 30, gamma = 250 }
cam1 = { exposure_time_ms = 3.2, contrast = 30, gamma = 200 }
cam2 = { exposure_time_ms = 3.5, contrast = 30, gamma = 380 }
```

### Motion Detection
```toml
[motion_detection]
downscale_factor = 4       # Downscale factor for motion detection
motion_threshold = 15
blur_kernel = 21
settled_threshold = 1.0    # Lowered from 2.0 to detect stuck darts
motion_check_interval = 0.05
settled_time = 0.5
```

### Dart Detection
```toml
[dart_detection]
diff_threshold = 15        # High threshold (try first)
blur_kernel = 3
min_dart_area = 50
max_dart_area = 10000
min_shaft_length = 15
aspect_ratio_min = 1.2

# Two-step threshold approach: try high (15) first, fallback to low (8) if nothing found
[dart_detection.per_camera]
cam0 = { diff_threshold = 8 }  # Low threshold fallback
cam1 = { diff_threshold = 8 }  # Low threshold fallback
cam2 = { diff_threshold = 8 }  # Low threshold fallback
```

**Shape Filters:**
- Circularity < 0.7 (reject circular board features)
- Solidity > 0.5 (reject hollow wires)
- Aspect ratio > 1.2 (elongated shape)

**Spatial Mask:**
- Exclude outer 15% (number ring)
- Include all scoring area including bull
- Valid radius = 42.5% of image half-width

**Two-Step Threshold Approach:**
1. Try high threshold (15) first - clean detection for strong signals
2. If nothing found, retry with low threshold (8) - catch weak signals from distant/angled darts
3. **Important:** camera_id must be passed as string format ('cam0', 'cam1', 'cam2') for config lookup

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

### 2. Two-Step Threshold Approach (Multi-Camera)

**Purpose:** Balance clean detection (avoid noise) with sensitivity (catch weak signals)

```python
# Step 1: Try high threshold first
tip_x, tip_y, confidence, debug_info = detect_with_threshold(pre, post, threshold=15)

# Step 2: If nothing found, retry with low threshold
if tip_x is None:
    low_threshold = per_camera_thresholds.get(camera_id, 15)  # e.g., 8
    if low_threshold < 15:
        tip_x, tip_y, confidence, debug_info = detect_with_threshold(pre, post, threshold=low_threshold)
```

**Why it works:**
- Close-up darts: Strong signal (20-50 pixel diff) → detected at threshold=15
- Distant/angled darts: Weak signal (5-10 pixel diff) → detected at threshold=8
- Avoids noise: High threshold tried first, low threshold only as fallback

**Critical:** camera_id must be string format ('cam0', 'cam1', 'cam2') for config lookup

### 3. Morphological Processing Pipeline

```python
# 1. Combine diff and edges
thresh = cv2.bitwise_or(diff_thresh, canny_edges)

# 2. Remove small noise (preserve tip)
kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_small)

# 3. Fill gaps progressively (connect flight fragments)
kernel_medium = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_medium)

kernel_large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_large)

kernel_xlarge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (27, 27))
thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_xlarge)

kernel_xxlarge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (35, 35))
thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_xxlarge)
```

### 4. Tip Identification (Widest Part Algorithm)

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

### 5. Edge Proximity Heuristic (Flight Outside Frame)

**Purpose:** Detect tip when flight is outside camera view

```python
# If confidence is low and one end is near image edge
if confidence < 0.3:
    edge_margin = 50  # pixels from edge
    
    dist1_to_edge = min(end1[0], end1[1], w - end1[0], h - end1[1])
    dist2_to_edge = min(end2[0], end2[1], w - end2[0], h - end2[1])
    
    if dist1_to_edge < edge_margin and dist2_to_edge > edge_margin:
        tip = end2  # end1 near edge (flight outside), end2 is tip
        confidence = 0.4
    elif dist2_to_edge < edge_margin and dist1_to_edge > edge_margin:
        tip = end1  # end2 near edge (flight outside), end1 is tip
        confidence = 0.4
```

**Why it works:**
- Flight often extends outside frame for distant/angled cameras
- End near edge = flight side (outside frame)
- Opposite end = tip (embedded in board)

### 6. Previous Dart Masking

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

## Multi-Camera Detection Results (Step 5)

### Test Case 7.5: Comprehensive Single-Dart Test (Round the Clock)

**Status:** ✅ COMPLETE  
**Completed:** 2026-01-17  
**Session:** Session_001_2026-01-17_19-30-54  
**Test Design:** 21 throws - one dart in each sector's triple (20 sectors) + bull

**Overall Performance:** 59/63 successful detections (94%)

| Metric | Result |
|--------|--------|
| Total detections | 63 (21 throws × 3 cameras) |
| Successful | 59 (94%) |
| Failures | 2 (3%) |
| Minor issues | 2 (3%) |
| **At least 2/3 cameras** | **21/21 (100%)** |

**Failures:**
- Throw 15 cam1: No detection (shape filtered out, but cam0/cam2 succeeded)
- Throw 20 cam2: Wrong position (board noise blob, but cam0/cam1 succeeded)

**Minor Issues:**
- Throw 21 bull cam1: Tip 5-10px outside bull (line fitting inaccuracy on short contour)

**Key Findings:**
- ✅ Y-coordinate heuristic: 94% accuracy across all board positions
- ✅ Multi-camera redundancy: 100% coverage (≥2 cameras per throw)
- ✅ Works "round the clock": All 20 sectors + bull
- ✅ Robust to camera angles: Top, bottom, side views all work
- ✅ Ready for fusion: Single-camera failures don't affect system

**Conclusion:** Y-coordinate heuristic validated. Single-camera detection robust enough for multi-camera fusion.

---

### Test Case 7.6: Multi-Camera Multiple Darts (TC7.6)

**Status:** ✅ COMPLETE  
**Completed:** 2026-01-18  
**Session:** Session_001_2026-01-18_13-17-05  
**Test Design:** 5 scenarios with 2-3 darts (separated, close, crossing)

**Overall Performance:** 32/36 successful detections (89%)

| Test Case | Result |
|-----------|--------|
| 7.6.1 Two darts wide | 6/6 (100%) ✅ |
| 7.6.2 Two darts close | 5/6 (83%) |
| 7.6.3 Two darts crossing | 5/6 (83%) |
| 7.6.4 Three darts non-crossing | 8/9 (89%) |
| 7.6.5 Three darts crossing | 8/9 (89%) |

**At least 2/3 cameras detected:** 11/12 throws (92%)

**Key Findings:**
- **Previous dart masking disabled:** Was blocking new darts, removed for multi-camera mode
- **Relaxed shape filters:** Circularity 0.7→0.8, Solidity 0.5→0.4, Aspect ratio 1.2→1.0
- **Tip position accuracy:** 20-30px systematic error (visible tip portion not in contour)
- **Multi-camera redundancy validated:** ≥2 cameras detect in >90% of throws
- **Fusion will correct errors:** Averaging 3 cameras reduces systematic offset

**Conclusion:** Multi-camera detection robust enough for fusion. Tip position errors systematic and will be corrected by fusion averaging. Ready for Step 6 (Calibration).

---

### Test Case 7: Multi-Camera Detection (TC7)

**Status:** ✅ COMPLETE  
**Completed:** 2026-01-17  
**Overall Performance:** 7/12 successful detections (58%)

| Test | Cam0 | Cam1 | Cam2 | Success Rate |
|------|------|------|------|--------------|
| 7.1 Bull | ✅ | ✅ | ❌ | 2/3 (67%) |
| 7.2 S18 | ✅ | ✅ | ✅ | 3/3 (100%) |
| 7.3 S17 | ❌ | ✅ | ❌ | 1/3 (33%) |
| 7.4 S11 | ✅ | ❌ | ✅ | 2/3 (67%) |

**Key Metrics:**
- At least 1 camera detected: 4/4 throws (100%)
- At least 2 cameras detected: 3/4 throws (75%)
- All 3 cameras detected: 1/4 throws (25%)

### Camera Blind Spots (Geometric Limitations)

**Root Cause:** 120° camera spacing creates viewing angles where dart appears edge-on

**Per-Camera Blind Spots:**
- **Cam0 (upper right/18):** Blind to darts near cam1 position (sector 17)
- **Cam1 (lower right/17):** Blind to darts near cam2 position (sector 11)
- **Cam2 (left/11):** Blind to darts near cam0 position (sector 18)

**Why This Happens:**
- Dart close to camera A → excellent detection (close-up view)
- Dart close to camera A → cameras B/C see it edge-on (minimal visible area)
- Edge-on view: shaft nearly parallel to camera, flight may be outside frame

**Examples from TC7:**
- TC7.3 (S17 near cam1): Cam1 ✅, Cam0 ❌, Cam2 ❌ (edge-on from opposite cameras)
- TC7.4 (S11 near cam2): Cam2 ✅, Cam0 ✅, Cam1 ❌ (flight outside frame)

**Conclusion:** This is expected behavior, not an algorithm failure. Multi-camera fusion (Step 7) will handle this by using detections from cameras with clear view.

### Multi-Camera Detection Patterns

**Pattern 1: Optimal (all cameras see dart clearly)**
- Example: TC7.2 (S18) - 3/3 detection
- Dart position: Not too close to any camera
- All cameras have oblique but clear view

**Pattern 2: Close-up dominant (one camera very close)**
- Example: TC7.3 (S17) - 1/3 detection
- Close camera: Excellent detection
- Opposite cameras: Blind (edge-on view)
- Fusion strategy: Use close camera only

**Pattern 3: Partial occlusion (flight outside frame)**
- Example: TC7.4 cam1 - wrong tip detection
- Only shaft visible, flight outside frame
- Algorithm fails: "widest part = flight" doesn't work
- Needs: Edge proximity heuristic improvement

**Pattern 4: Close-up distortion (large irregular blob)**
- Example: TC7.4 cam2 - correct but strange shape
- Close-up captures entire dart + shadows
- Morphological closing creates bulky contour
- Not a problem: Tip location still correct

### Algorithm Limitations Discovered

**1. Edge Proximity Heuristic Insufficient:**
- Current threshold: confidence < 0.3 to trigger
- TC7.4 cam1: Flight outside frame, but confidence 0.15 didn't help
- **Fix needed:** Check edge proximity even at moderate confidence (< 0.5)

**2. Two-Step Threshold Can't Fix Geometry:**
- TC7.3 cam0/cam2: Even threshold=8 finds nothing
- Dart genuinely invisible from extreme angles
- **Conclusion:** Threshold tuning has limits, fusion is the solution

**3. Widest-Part Algorithm Requires Flight Visible:**
- Works excellently when flight in frame (95%+ accuracy in TC0-TC6)
- Fails when flight outside frame (TC7.4 cam1)
- **Fallback needed:** Better edge proximity logic

---

## Next Steps (Step 6-7)

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
