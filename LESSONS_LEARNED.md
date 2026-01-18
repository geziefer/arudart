# ARU-DART Lessons Learned

**Project:** Automatic Dartboard Scoring System  
**Phase:** POC Development (Steps 1-5)  
**Last Updated:** 2026-01-11

---

## Camera Control & Exposure

### ❌ What Didn't Work

**OpenCV exposure control on macOS:**
- `cv2.CAP_PROP_EXPOSURE` and `cv2.CAP_PROP_BRIGHTNESS` don't work on macOS
- Settings appear to be accepted but have no effect
- Camera firmware ignores OpenCV property settings
- **Lesson:** Don't rely on OpenCV for camera control on macOS

**Single exposure value for all cameras:**
- Initially tried same exposure (-7) for all 3 cameras
- Failed because cameras at different angles receive different lighting
- Cam1 (seeing LED ring) was darker than cam0/cam2 (seeing only board)
- **Lesson:** Each camera needs individual tuning based on its viewing angle

### ✅ What Worked

**Platform-specific camera control tools:**
- **macOS:** uvc-util (local binary)
- **Linux:** v4l2-ctl (system-wide)
- Direct hardware control via command-line tools
- **Lesson:** Use platform-specific tools for reliable camera control

**Per-camera settings:**
- exposure_time_ms, contrast, gamma individually tuned
- Fixed brightness=-64 for all cameras
- Disable all auto features (exposure, white balance, focus)
- **Lesson:** Per-camera tuning is essential for multi-camera setups

---

## Detection Threshold & Noise

### ❌ What Didn't Work

**Very low diff threshold (5):**
- Intended to catch weak dart signals
- Actually captured massive board noise (sensor noise, compression artifacts)
- Board noise created larger blobs than dart
- Algorithm selected board blob instead of dart
- **Lesson:** Too sensitive threshold creates more problems than it solves

**Size-based contour selection:**
- Selecting largest contour by area
- Board noise blobs often larger than dart
- Failed when board had scattered noise
- **Lesson:** Size alone is not a reliable discriminator

### ✅ What Worked

**Moderate diff threshold (15):**
- Filters out board noise (weak signal)
- Keeps dart signal (strong signal: 20-50 pixel difference)
- Clean threshold images
- **Lesson:** Threshold should match signal strength, not be arbitrarily low

**Shape-based scoring:**
- `score = area × aspect_ratio × (1 - circularity)`
- Prioritizes elongated, non-circular shapes (darts)
- Rejects compact, circular shapes (board blobs)
- Dart wins even if smaller than noise blob
- **Lesson:** Shape characteristics are more reliable than size

**Multi-frame post-impact capture:**
- Capture 3 frames at 100ms intervals
- Select frame with lowest background noise
- Reduces random sensor noise and compression artifacts
- **Lesson:** Multiple samples reduce noise better than single frame

---

## Morphological Operations

### ❌ What Didn't Work

**Small closing kernels (11x11, 15x15, 19x19):**
- Couldn't bridge large gaps between flight and shaft
- Metallic shaft often weak/invisible on colored sectors
- Flight and shaft remained disconnected
- Algorithm only saw flight, placed tip at wrong end
- **Lesson:** Kernel size must match gap size in real images

**Single-blob assumption:**
- Assumed dart is always one connected contour
- Failed when flight and shaft disconnected
- No fallback for fragmented detections
- **Lesson:** Real-world images don't always match ideal assumptions

### ✅ What Worked

**Progressive closing with large kernels:**
- 15x15, 21x21, 27x27, 35x35 (progressively larger)
- Bridges most gaps between flight and shaft
- Connects fragmented flight pieces
- **Lesson:** Use multiple passes with increasing kernel sizes

**Multi-blob analysis as fallback:**
- Triggered when confidence < 0.5 or dart length < 40px
- Finds top 2-3 elongated blobs
- Checks if aligned (angle difference < 30°)
- Treats aligned blobs as single dart
- **Lesson:** Have fallback strategies for edge cases

---

## Spatial Masking

### ❌ What Didn't Work

**Too restrictive spatial mask (42% radius):**
- Intended to exclude outer number ring
- Actually excluded valid dart positions near edges
- Darts at 250px from center rejected (mask radius 168px)
- **Lesson:** Test mask with real dart positions, not just theory

### ✅ What Worked

**Larger spatial mask (42.5% radius):**
- Includes all valid dart positions
- Still excludes outer number ring
- Edge darts now detected
- **Lesson:** Mask should be based on actual dart distribution, not arbitrary percentage

---

## Algorithm Design Philosophy

### ❌ What Didn't Work

**Optimizing for ideal cases:**
- Assumed dart always connected, always visible
- Assumed single contour, clean shape
- Failed on real-world variations (weak shaft, fragmented flight)
- **Lesson:** Real data is messier than ideal assumptions

**Single-strategy approach:**
- One algorithm for all cases
- No fallback for failures
- Edge cases caused complete detection failure
- **Lesson:** Need multiple strategies for robustness

### ✅ What Worked

**Layered approach with fallbacks:**
1. Try main algorithm (widest-part tip identification)
2. If low confidence, try multi-blob analysis
3. If still failing, log for manual review
- **Lesson:** Fallback strategies handle edge cases without affecting normal cases

**Iterative refinement based on real data:**
- Test with real throws, not synthetic data
- Analyze failures, identify patterns
- Adjust parameters based on actual failure modes
- **Lesson:** Real-world testing reveals issues theory misses

---

## Hardware & Environment Assumptions

### ❌ What We Initially Assumed (Incorrectly)

**"Background noise comes from lighting changes":**
- Actually: Lighting is stable (LED ring + room light)
- Real source: Sensor noise, dart reflections, compression artifacts
- **Lesson:** Don't assume environmental instability without evidence

**"Background noise comes from board movement":**
- Actually: Board and cameras are fixed, mechanically stable
- Real source: Optical properties (reflections, micro-shadows)
- **Lesson:** Verify physical setup before blaming mechanical issues

**"All cameras need same settings":**
- Actually: Each camera sees different lighting based on angle
- Cam1 (sees LED ring) needs different exposure than cam0/cam2
- **Lesson:** Camera position affects optimal settings

### ✅ What We Learned About Hardware

**Lighting is stable:**
- LED ring provides even, shadow-free illumination
- Room lighting doesn't change during tests
- Window light only varies on sunny+cloudy days (rare)
- **Lesson:** Stable lighting is NOT the source of noise

**Mechanical setup is stable:**
- Board fixed to wall, cameras fixed to LED ring
- Only tiny vibrations from dart impact/extraction
- Operator waits for settling after accidental touch
- **Lesson:** Mechanical stability is NOT the problem

**Noise sources are optical/sensor:**
- Camera sensor noise (thermal, read noise)
- Dart reflections (metallic barrel, flight material)
- Micro-shadows from dart on board
- MJPEG compression artifacts
- **Lesson:** Noise is inherent to imaging, not environmental

---

## Development Process

### ❌ What Didn't Work

**Implementing all features before testing:**
- Built complex algorithms without validation
- Discovered fundamental issues late
- Had to refactor extensively
- **Lesson:** Test incrementally, validate assumptions early

**Trusting logs without inspecting images:**
- Logs said "detection successful"
- Images showed wrong tip location
- Missed systematic errors
- **Lesson:** Always inspect visual output, not just metrics

### ✅ What Worked

**Incremental testing with saved images:**
- Save all images (pre, post, diff, thresh, annotated)
- Inspect failures manually
- Identify patterns in failure modes
- **Lesson:** Visual inspection reveals issues logs miss

**Test-driven parameter tuning:**
- Run test cases (TC0-TC6)
- Analyze failures
- Adjust parameters
- Re-test same cases
- **Lesson:** Systematic testing beats trial-and-error

**Manual testing mode:**
- Pause/place dart/detect workflow
- Controlled, repeatable test cases
- No throwing skill required
- **Lesson:** Manual testing enables precise validation

---

## Key Takeaways

1. **Don't trust OpenCV camera control on macOS** - use platform-specific tools
2. **Each camera needs individual tuning** - viewing angle affects lighting
3. **Shape is more reliable than size** - use aspect ratio and circularity
4. **Multiple samples reduce noise** - capture 3 frames, select best
5. **Have fallback strategies** - multi-blob analysis for edge cases
6. **Test with real data** - synthetic assumptions fail in practice
7. **Inspect images, not just logs** - visual validation catches errors
8. **Iterate based on failures** - analyze patterns, adjust systematically
9. **Noise is optical, not environmental** - stable lighting still has sensor noise
10. **Manual testing enables precision** - controlled placement beats random throws
11. **❌ Board-center heuristic DOES NOT WORK** - tip position relative to center depends on dart location on board
12. **✅ Y-coordinate heuristic is PRIMARY method** - tip always has larger Y than flight (embedded vs sticking out), works across all camera angles except dart pointing at camera (impossible in real throws)
13. **Geometric blind spots are expected** - 120° camera spacing creates edge-on views when dart is close to one camera
14. **Multi-camera redundancy is essential** - at least 2/3 cameras detect in 75% of cases, fusion will handle outliers
15. **Two-step threshold has limits** - can't fix geometric invisibility, only helps with weak signals
16. **Previous dart masking causes more problems than it solves** - in multi-camera mode, masking blocks legitimate new darts, fusion handles duplicates better
17. **Visible tip portion often missing from contour** - morphological closing bridges barrel-to-board gap, contour ends at barrel bottom not actual tip insertion point
18. **Tip position error is systematic** - 20-30px offset is consistent across cameras, can be corrected by fusion averaging or calibration offset
19. **Dart movement in grouped throws is expected** - when 3rd dart hits T20, it often pushes 1st/2nd dart slightly, must distinguish new dart from moved darts
20. **Position tracking solves movement detection** - store known dart positions, compare with new detections, ignore positions within 30px of known darts (moved), only emit events for truly new positions
21. **Tip visibility varies by sector color** - steel tip in black sectors has weak contrast (5-15mm error), white/red/green sectors have better contrast (5-10mm error)
22. **Hardware optimization possible** - colored tips (instead of steel) improve detectability, colored flights (instead of black) improve contrast, system is personal so dart customization is viable option
23. **Measure before optimizing** - complete calibration and fusion first, measure actual error with real throws, then optimize if needed (targeted tip search, colored tips, or calibration offset)

---

## Future Considerations

**For multi-camera fusion (Step 7):**
- Expect varying detection rates per camera (occlusion, angle)
- Weight by confidence when fusing coordinates
- At least 2/3 cameras should detect in most throws
- Crossing darts will fail single-camera, need fusion

**For calibration (Step 6):**
- Per-camera intrinsic calibration (lens distortion)
- ARUCO markers for extrinsic calibration (board plane mapping)
- Homography per camera (image → board coordinates)

**For production deployment:**
- Camera control must work on Raspberry Pi (v4l2-ctl)
- USB bandwidth may be limiting factor (3 cameras @ 25fps)
- Consider lower resolution if needed (640×480 instead of 800×600)

---

**Document Purpose:** Capture mistakes and learnings to avoid repeating them in future phases. Read this before starting Step 6 (Calibration) and Step 7 (Fusion).
