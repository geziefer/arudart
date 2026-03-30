# Implementation Plan: Fusion Accuracy Improvements

## Overview

Modify `CoordinateFusion` in-place to add pairwise outlier rejection (2-camera case), tighten the 3-camera threshold to 25mm, introduce angular proximity weighting via a two-pass fusion strategy, and update config. All core changes are in `src/fusion/coordinate_fusion.py`. New tests go in `tests/test_fusion_accuracy.py` and `tests/test_fusion_accuracy_properties.py`.

## Tasks

- [x] 1. Update `CoordinateFusion.__init__` to load new config parameters
  - Add `pairwise_rejection_mm` (default 20.0) from `fusion.pairwise_rejection_mm`
  - Add `angular_falloff` (default 1.0) from `fusion.angular_falloff`
  - Add `camera_anchors` (default `{0: 81, 1: 257, 2: 153}`) from `fusion.camera_anchors`
  - Change default for `outlier_threshold_mm` from 50.0 to 25.0
  - Log a warning when `camera_anchors` is absent from config and defaults are used
  - _Requirements: 1.3, 2.2, 3.1, 6.1, 6.2, 6.3_

- [x] 2. Implement `reject_outliers_pairwise`
  - [x] 2.1 Add `reject_outliers_pairwise(detections: list[dict]) -> list[dict]` method
    - Accept exactly 2 detections
    - Compute Euclidean distance between their board positions
    - If distance ≤ `pairwise_rejection_mm`: return both unchanged
    - If distance > `pairwise_rejection_mm`: discard the lower-confidence detection, return the other
    - Log rejected camera ID, pairwise distance, and threshold at INFO level
    - _Requirements: 1.1, 1.2, 1.4_

  - [x] 2.2 Write property test for `reject_outliers_pairwise` (Property 1)
    - **Property 1: Pairwise Rejection Correctness**
    - **Validates: Requirements 1.1, 1.2**
    - Generate random pairs of detections with random positions and confidences
    - If distance > threshold: verify only the higher-confidence detection is returned
    - If distance ≤ threshold: verify both detections are returned unchanged
    - Use `@settings(max_examples=100, deadline=None)`
    - Tag: `Feature: step-7.1-fusion-accuracy, Property 1: Pairwise Rejection Correctness`

- [x] 3. Update `reject_outliers` — tighten threshold, remove 2-camera guard
  - Remove the `if len(detections) <= 2: return detections` early-return guard
  - The default threshold is now 25mm (set in `__init__`, not here)
  - No other logic changes needed — median-based rejection algorithm stays the same
  - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.1 Write property test for `reject_outliers` (Property 2)
    - **Property 2: Median-Based Outlier Rejection Correctness**
    - **Validates: Requirements 2.1**
    - Generate 3 random detections; compute median position manually
    - Verify retained detections are exactly those within `outlier_threshold_mm` of median
    - Use `@settings(max_examples=100, deadline=None)`
    - Tag: `Feature: step-7.1-fusion-accuracy, Property 2: Median-Based Outlier Rejection Correctness`

- [x] 4. Implement `compute_angular_weight`
  - [x] 4.1 Add `compute_angular_weight(board_angle_rad: float, camera_id: int) -> float` method
    - Look up `anchor_deg` from `self.camera_anchors[camera_id]`
    - If `camera_id` not in anchors: use 0.5 (neutral) and log a warning
    - Compute `delta` as shortest arc between `board_angle_rad` and `anchor_rad`
    - Return `((1 + cos(delta)) / 2) ** self.angular_falloff`
    - Result is always ≥ 0.0
    - _Requirements: 3.2, 3.3, 3.6_

  - [x] 4.2 Write property test for `compute_angular_weight` (Property 4)
    - **Property 4: Angular Weight Formula**
    - **Validates: Requirements 3.2, 3.3, 3.4**
    - Generate random board angles and camera IDs (0, 1, 2)
    - Verify result matches `((1 + cos(shortest_arc)) / 2) ** falloff`
    - Verify result is 1.0 when dart angle equals camera anchor angle
    - Verify result approaches 0.0 at 180° away
    - Use `@settings(max_examples=100, deadline=None)`
    - Tag: `Feature: step-7.1-fusion-accuracy, Property 4: Angular Weight Formula`

- [x] 5. Update `compute_weighted_average` to accept optional weights parameter
  - Add `weights: dict | None = None` parameter
  - If `weights is None`: use confidence-only weighting (existing behavior, backward compatible)
  - If `weights` provided: use `weights[id(d)]` as the weight for each detection
  - If total weight is zero: fall back to simple arithmetic mean and log a warning
  - _Requirements: 3.4, 3.5, 6.4_

- [x] 6. Update `fuse_detections` — two-pass strategy, wire everything together
  - [x] 6.1 Update routing logic for 2-camera vs 3-camera cases
    - After confidence filtering: if `len(valid) == 2`, call `reject_outliers_pairwise(valid)`
    - If `len(valid) >= 3`, call `reject_outliers(valid)`
    - If `len(inliers) == 0` (only possible from 3-camera path): fall back to highest-confidence detection from `valid`
    - Log the fallback at WARNING level
    - _Requirements: 1.1, 2.4, 4.4_

  - [x] 6.2 Implement two-pass angular weighting
    - Pass 1: `(px, py) = compute_weighted_average(inliers)` — confidence-only
    - Compute `board_angle = atan2(py, px)`
    - Compute per-detection angular weights via `compute_angular_weight`
    - Build combined weights dict: `{id(d): d["confidence"] * angular_weight}`
    - If all angular weights < 0.1: fall back to confidence-only weights and log at DEBUG
    - Pass 2: `(fx, fy) = compute_weighted_average(inliers, weights=combined_weights)`
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.7, 4.1, 4.2, 4.3_

  - [x] 6.3 Log per-detection diagnostics and preserve return signature
    - Log at DEBUG: per-detection angular distance, angular weight, confidence, final weight
    - Return `(fx, fy, combined_confidence, cameras_used)` — signature unchanged
    - _Requirements: 5.3, 6.4_

- [x] 7. Checkpoint — run existing tests to confirm no regressions
  - Run `PYTHONPATH=. venv/bin/pytest tests/test_coordinate_fusion.py tests/test_coordinate_fusion_properties.py -v`
  - All existing tests must pass before proceeding
  - Note: existing tests use `outlier_threshold_mm = 50.0` in their config dict, so the new 25mm default does not affect them
  - Ask the user if any tests fail before continuing

- [x] 8. Write unit tests in `tests/test_fusion_accuracy.py`
  - [x] 8.1 Test pairwise rejection: two detections 30mm apart → lower confidence rejected
    - _Requirements: 1.1_
  - [x] 8.2 Test pairwise rejection: two detections 15mm apart → both kept
    - _Requirements: 1.2_
  - [x] 8.3 Test tighter 3-camera threshold: one detection 30mm from median → rejected (would pass old 50mm threshold)
    - _Requirements: 2.1, 2.2_
  - [x] 8.4 Test total rejection fallback: all 3 detections >25mm from median → highest-confidence returned, not None
    - _Requirements: 2.4_
  - [x] 8.5 Test angular weight at known angles: cam0 anchor=81°, dart at 81° → weight=1.0; dart at 261° → weight≈0.0; dart at 171° → weight≈0.5
    - _Requirements: 3.2, 3.3_
  - [x] 8.6 Test angular weight fallback: all cameras far from dart angle (all weights < 0.1) → confidence-only weighting used
    - _Requirements: 3.7_
  - [x] 8.7 Test backward compatibility: old config dict (no new keys) → defaults applied, fusion returns valid result
    - _Requirements: 6.1, 6.2_
  - [x] 8.8 Test return type: `fuse_detections()` always returns `(float, float, float, list[int])` or `None`
    - _Requirements: 6.4_

- [x] 9. Write property tests in `tests/test_fusion_accuracy_properties.py`
  - [x] 9.1 Property 1: Pairwise Rejection Correctness
    - **Property 1: Pairwise Rejection Correctness**
    - **Validates: Requirements 1.1, 1.2**
    - (See task 2.2 for full spec)

  - [x] 9.2 Property 2: Median-Based Outlier Rejection Correctness
    - **Property 2: Median-Based Outlier Rejection Correctness**
    - **Validates: Requirements 2.1**
    - (See task 3.1 for full spec)

  - [x] 9.3 Property 3: Total Rejection Fallback
    - **Property 3: Total Rejection Fallback**
    - **Validates: Requirements 2.4**
    - Generate 3 detections all far apart (all > 25mm from median)
    - Verify `fuse_detections` returns a non-None result using the highest-confidence detection's position
    - Use `@settings(max_examples=100, deadline=None)`
    - Tag: `Feature: step-7.1-fusion-accuracy, Property 3: Total Rejection Fallback`

  - [x] 9.4 Property 4: Angular Weight Formula
    - **Property 4: Angular Weight Formula**
    - **Validates: Requirements 3.2, 3.3, 3.4**
    - (See task 4.2 for full spec)

  - [x] 9.5 Property 5: Two-Pass Fusion Weighted Average
    - **Property 5: Two-Pass Fusion Weighted Average**
    - **Validates: Requirements 3.5, 4.1, 6.4**
    - Generate 2-3 close detections (within pairwise/outlier threshold)
    - Manually compute expected result: pass 1 confidence-only avg → board angle → angular weights → pass 2 weighted avg
    - Verify `fuse_detections` output matches within 1e-6 tolerance
    - Verify return is always a 4-tuple `(float, float, float, list[int])` or None
    - Use `@settings(max_examples=100, deadline=None)`
    - Tag: `Feature: step-7.1-fusion-accuracy, Property 5: Two-Pass Fusion Weighted Average`

- [x] 10. Update `config.toml` — add new fusion parameters
  - Replace the existing `[fusion]` section with the updated values:
    ```toml
    [fusion]
    outlier_threshold_mm = 25.0       # tightened from 50.0
    pairwise_rejection_mm = 20.0      # new — for 2-camera case
    min_confidence = 0.3              # unchanged
    angular_falloff = 1.0             # new — cosine exponent
    [fusion.camera_anchors]
    cam0 = 81
    cam1 = 257
    cam2 = 153
    ```
  - _Requirements: 1.3, 2.2, 3.1, 3.6, 6.1, 6.2_

- [x] 11. Final checkpoint — ensure all tests pass
  - Run `PYTHONPATH=. venv/bin/pytest tests/test_coordinate_fusion.py tests/test_coordinate_fusion_properties.py tests/test_fusion_accuracy.py tests/test_fusion_accuracy_properties.py -v`
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property tests 9.1 and 9.2 overlap with sub-tasks 2.2 and 3.1 — implement them once in `tests/test_fusion_accuracy_properties.py`
- Existing tests use `{"fusion": {"outlier_threshold_mm": 50.0, "min_confidence": 0.3}}` — the new 25mm default only applies when no config is passed
- The `compute_weighted_average` signature change is backward compatible (weights defaults to None)
- `reject_outliers` no longer has the `<= 2` guard, but it is only called for 3+ detections from `fuse_detections`
