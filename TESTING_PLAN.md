# Dart Detection Testing Plan

## Testing Approach

**Iterative testing works best:**
- Complete one test case at a time
- Report results after each test case
- Examine failure images together
- Make targeted fixes
- Verify fix before moving to next case

---

## Single-Camera Tests (TC0-TC6)

### Test Case 0: Reproducible Detection ✅ PASSED
**Goal:** Verify that same dart gives same results

**Status:** ✅ PASSED (Session_002_2026-01-03_09-07-30)
- Tip detection accurate (reaches actual steel point)
- Consistent coordinates across repeated placements
- Confidence: 0.30-0.49 (acceptable for gradual taper)

---

### Test Case 1: Basic Detection Validation ✅ PASSED
**Goal:** Verify detection works across different board regions

**Status:** ✅ PASSED (Session_001_2026-01-03_09-16-33, Session_003_2026-01-03_09-41-45)
- All 6 throws successful across different board regions
- Detection works consistently across entire board

---

### Test Case 2: Contrast Challenges ✅ PASSED
**Goal:** Test detection on different colored sectors

**Status:** ✅ PASSED (Session_007_2026-01-03_17-03-40)
- All 9 throws successful
- Detection robust across different colored sectors (white, black, red, green)

---

### Test Case 3: Dart Orientation ✅ PASSED
**Goal:** Test different entry angles

**Status:** ✅ PASSED (Session_002_2026-01-03_17-16-24)
- All 9 throws successful
- Tip identification correct across all orientations
- Algorithm is orientation-invariant

---

### Test Case 4: Multiple Darts (Occlusion) ⚠️ PARTIAL
**Goal:** Test with existing darts in frame

**Status:** ⚠️ PARTIALLY PASSED (Session_005_2026-01-03_19-44-32)
- Side-by-side darts: ✅ Works
- Crossing darts: ❌ Physical occlusion (requires 3 cameras)
- Cluster of 3: ✅ Works

**Re-test Required:** After 3-camera system implementation (Step 5-7)

---

### Test Case 5: Edge Cases ✅ PASSED
**Goal:** Test boundary conditions

**Status:** ✅ PASSED (Session_006_2026-01-03_20-00-59)
- 8/8 throws detected correctly
- Tip detection works near wires and sector boundaries

---

### Test Case 6: Lighting Variations ✅ PASSED
**Goal:** Test robustness to lighting changes

**Status:** ✅ PASSED (Session_008_2026-01-03_20-34-30)
- 3/3 lighting variations successful (normal, dimmer, brighter)
- Fixed camera exposure settings provide good robustness

---

## Multi-Camera Tests (TC7-TC9)

### Test Case 7: Multi-Camera Detection ✅ PASSED
**Goal:** Verify detection works across all 3 cameras simultaneously

**Test Cases:**
- 7.1 Bull's eye
- 7.2 Single 18 (near cam0)
- 7.3 Single 17 (near cam1)
- 7.4 Single 11 (near cam2)

**Status:** ✅ PASSED (Session_012_2026-01-17_16-29-26)
- 7/12 successful detections (58% overall)
- At least 1 camera detected: 4/4 throws (100%)
- At least 2 cameras detected: 3/4 throws (75%)

**Conclusion:** Geometric blind spots confirmed (expected). Multi-camera redundancy working.

---

### Test Case 7.5: Comprehensive Single-Dart Test (Round the Clock) ✅ PASSED
**Goal:** Validate Y-coordinate heuristic across all board positions

**Test Design:** 21 throws - one dart in each sector's triple (20 sectors) + bull

**Status:** ✅ PASSED (Session_001_2026-01-17_19-30-54)
- 59/63 successful detections (94% overall)
- At least 2/3 cameras detected: 21/21 throws (100%)
- Failures: 2 (Throw 15 cam1, Throw 20 cam2)
- Minor issues: 1 (Throw 21 bull cam1 tip 5-10px offset)

**Conclusion:** Y-coordinate heuristic validated. Single-camera detection robust enough for multi-camera fusion.

---

### Test Case 7.6: Multi-Camera Multiple Darts ⏳ PENDING
**Goal:** Verify multi-camera detection with multiple darts (both separated and overlapping)

**Test Cases:**
- 7.6.1 Two darts side-by-side (same sector, 20mm apart)
- 7.6.2 Two darts close (same sector, 10mm apart)
- 7.6.3 Two darts crossing (barrels intersect)
- 7.6.4 Three darts in cluster (not crossing)
- 7.6.5 Three darts with one crossing

**Expected:**
- Side-by-side: All 3 cameras detect both darts
- Close darts: At least 2/3 cameras detect both darts
- Crossing darts: At least 2/3 cameras detect both darts (different angles see separation)
- Cluster: At least 2/3 cameras detect all darts

**Success Criteria:**
- ≥2 cameras detect each dart in all scenarios
- Crossing darts work better than single-camera (TC4.2 retry)
- Background update includes all previous darts correctly

---

### Test Case 8: Camera Synchronization ⏳ PENDING
**Goal:** Verify all cameras capture frames at the same moment

**Test Cases:**
- 8.1 Fast hand movement across board
- 8.2 Dart throw with visible motion blur
- 8.3 Check timestamps in saved images

**Expected:**
- Pre/post frames from all cameras show same board state
- No significant time lag between camera captures
- Motion detection triggers on all cameras simultaneously

---

### Test Case 9: Per-Camera Detection Rates ⏳ PENDING
**Goal:** Identify which camera angles work best

**Test Design:** 20 throws across different board regions

**Expected:**
- Track detection rate per camera
- Identify blind spots per camera
- Verify at least 1 camera detects in >95% of throws

---

## Testing Workflow

### For Single-Camera Tests (TC0-TC6):
1. Run: `python main.py --dev-mode --manual-test --single-camera 0`
2. Press 'r' to capture clean background
3. For each throw:
   - Press 'p' to pause
   - Place dart manually
   - Press 'p' to resume and detect
   - Remove dart, press 'r' to reset (except for multiple darts)

### For Multi-Camera Tests (TC7-TC9):
1. Run: `python main.py --dev-mode --manual-test`
2. Press 'r' to capture clean background (all cameras)
3. For each throw:
   - Press 'p' to pause
   - Place dart manually
   - Press 'p' to resume and detect
   - For multiple darts: don't press 'r' between darts (background auto-updates)
   - After all darts: remove all, press 'r' to reset

---

## Test Status Summary

| Test Case | Status | Detection Rate | Notes |
|-----------|--------|----------------|-------|
| TC0 | ✅ PASSED | 6/6 (100%) | Reproducible |
| TC1 | ✅ PASSED | 6/6 (100%) | All board regions |
| TC2 | ✅ PASSED | 9/9 (100%) | All colors |
| TC3 | ✅ PASSED | 9/9 (100%) | All orientations |
| TC4 | ⚠️ PARTIAL | 2/3 (67%) | Crossing darts need 3 cameras |
| TC5 | ✅ PASSED | 8/8 (100%) | Edge cases |
| TC6 | ✅ PASSED | 3/4 (75%) | Lighting variations |
| TC7 | ✅ PASSED | 7/12 (58%) | Multi-camera blind spots expected |
| TC7.5 | ✅ PASSED | 59/63 (94%) | Y-coordinate validated |
| TC7.6 | ⏳ PENDING | - | Multi-dart with 3 cameras |
| TC8 | ⏳ PENDING | - | Camera sync |
| TC9 | ⏳ PENDING | - | Per-camera rates |

**Overall Single-Camera:** 41/44 successful (93%)  
**Overall Multi-Camera:** 66/75 successful (88%)  
**Ready for:** Step 6 (Calibration) after TC7.6 completion
