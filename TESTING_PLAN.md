# Dart Detection Testing Plan

## Testing Approach

**Iterative testing works best:**
- Complete one test case at a time
- Report results after each test case
- Examine failure images together
- Make targeted fixes
- Verify fix before moving to next case

## Test Plan for Single-Camera Dart Detection

### Test Case 0: Reproducable Detection
**Goal:** Verify that same dart gives same results

- **0.1** Single 17 large single 
- **0.2** Single 17 large single
- **0.3** Single 17 large single
- **0.4** Single 2 large single 
- **0.5** Single 2 large single
- **0.6** Single 2 large single

**Expected:** All should detect tip correctly and all three of each number should be very similar

---

### Test Case 1: Basic Detection Validation
**Goal:** Verify detection works across different board regions

- **1.1** Bull's eye (center)
- **1.2** Single 17 (top center)
- **1.3** Triple 17 (top center, narrow ring)
- **1.4** Double 17 (outer ring, top)
- **1.5** Single 3 (left side)
- **1.6** Single 2 (right right)

**Expected:** All should detect with tip correctly identified

---

### Test Case 2: Contrast Challenges
**Goal:** Test detection on different colored sectors

- **2.1** White sector - metallic dart on white
- **2.1** Different white sector - metallic dart on white
- **2.2** Black sector - metallic dart on black
- **2.2** Different black sector - metallic dart on black
- **2.3** Red double ring
- **2.4** Green triple ring

**Expected:** Edge detection should help with white sectors

---

### Test Case 3: Dart Orientation
**Goal:** Test different entry angles

- **3.1** Straight in (perpendicular to board)
- **3.2** Angled left (~30° from perpendicular)
- **3.3** Angled right (~30° from perpendicular)
- **3.4** Angled up
- **3.5** Angled down

**Expected:** Tip identification should work regardless of angle

---

### Test Case 4: Multiple Darts (Occlusion)
**Goal:** Test with existing darts in frame

- **4.1** Second dart near first (same sector)
- **4.2** Second dart crossing first dart's shaft
- **4.3** Third dart in cluster

**Expected:** Background update should include previous darts; only new dart detected

---

### Test Case 5: Edge Cases
**Goal:** Test boundary conditions

- **5.1** Dart in triple close to single 
- **5.2** Dart in triple close to out
- **5.3** Dart in triple close to next triple
- **5.4** Dart in white single close to next single
- **5.5** Dart in black single close to next single

**Expected:** Wire interference, edge detection limits

---

### Test Case 6: Lighting Variations
**Goal:** Test robustness to lighting changes

- **6.1** Normal lighting (baseline)
- **6.2** Dimmer lighting
- **6.3** Brighter lighting
- **6.4** Shadow cast on board

**Expected:** Fixed exposure should help; may need threshold adjustments

---

## Testing Workflow

### For Each Test Case:

1. Run manual test mode: `python main.py --dev-mode --manual-test`
2. Press 'r' to capture clean background
3. For each throw in the test case:
   - Press 'p' to pause
   - Place dart manually
   - Press 'p' to resume and detect
   - Press 'p' again and remove dart (except for multiple darts)
   - Press 'r' to reset for next case (except multiple darts)
4. Note results: "5/6 detected, 1.4 failed"
5. Report failure with throw folder name
6. Examine images together and fix
7. Re-test failed case
8. Move to next test case when all pass

---

## Results Tracking

### Test Case 0: Reproducible Detection
- [x] 0.1 Single 17
- [x] 0.2 Single 17
- [x] 0.3 Single 17
- [x] 0.4 Single 2
- [x] 0.5 Single 2
- [x] 0.6 Single 2

**Status:** ✅ PASSED (Session_002_2026-01-03_09-07-30)
- Tip detection accurate (reaches actual steel point)
- Consistent coordinates across repeated placements
- Confidence: 0.30-0.49 (acceptable for gradual taper)

---

### Test Case 1: Basic Detection Validation
- [x] 1.1 Bull's eye
- [x] 1.2 Single 17
- [x] 1.3 Triple 17
- [x] 1.4 Double 17
- [x] 1.5 Single 3
- [x] 1.6 Single 2

**Status:** ✅ PASSED (Session_001_2026-01-03_09-16-33, Session_003_2026-01-03_09-41-45)
- All 6 throws successful across different board regions
- 1.1 Bull initially failed, required algorithm fix (changed from endpoint width comparison to finding widest part as flight)
- Algorithm now correctly handles embedded tips (common in bull throws)
- Detection works consistently across entire board

---

### Test Case 2: Contrast Challenges
- [ ] 2.1 White sector
- [ ] 2.2 Different white sector
- [ ] 2.3 Black sector
- [ ] 2.4 Different black sector
- [ ] 2.5 Red double
- [ ] 2.6 Green triple

**Status:** Not started

---

### Test Case 3: Dart Orientation
- [ ] 3.1 Straight in
- [ ] 3.2 Angled left
- [ ] 3.3 Angled right
- [ ] 3.4 Angled up
- [ ] 3.5 Angled down

**Status:** Not started

---

### Test Case 4: Multiple Darts
- [ ] 4.1 Second dart near first
- [ ] 4.2 Second dart crossing first
- [ ] 4.3 Third dart in cluster

**Status:** Not started

---

### Test Case 5: Edge Cases
- [ ] 5.1 Close to wire
- [ ] 5.2 Obscured by wire
- [ ] 5.3 Near number ring
- [ ] 5.4 Bounce-out

**Status:** Not started

---

### Test Case 6: Lighting Variations
- [ ] 6.1 Normal lighting
- [ ] 6.2 Dimmer lighting
- [ ] 6.3 Brighter lighting
- [ ] 6.4 Shadow on board

**Status:** Not started
