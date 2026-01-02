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
- **0.1** Single 17 large single
- **0.1** Single 17 large single
- **0.1** Single 2 large single 
- **0.1** Single 2 large single
- **0.1** Single 2 large single

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
   - Press 'r' to reset for next case (except if anoterh dart at the same time is part of the test)
4. Note results: "5/6 detected, 1.4 failed"
5. Report failure with throw folder name
6. Examine images together and fix
7. Re-test failed case
8. Move to next test case when all pass
