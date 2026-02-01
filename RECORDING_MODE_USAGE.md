# Recording Mode Usage Guide

## Purpose

Recording mode captures **pre-frame** (clean board) and **post-frame** (with dart) pairs for regression testing. This accounts for lighting changes over time by using image differencing in tests.

## Usage

### Start Recording Mode

```bash
python main.py --dev-mode --record-mode
```

### Workflow

1. **Press 'r'** - Capture PRE-frame (clean board)
   - System captures current frame from all 3 cameras
   - Status shows: `[REC #001 - Press 'c' for POST]`

2. **Place dart manually**
   - Position dart on board
   - Take your time, no rush

3. **Press 'c'** - Capture POST-frame (with dart)
   - System captures current frame from all 3 cameras
   - Console prompts: `Enter description (e.g., 'T20', 'bull', 'two_darts_crossing'):`
   - Type description and press ENTER

4. **Repeat** for next recording
   - System auto-increments to recording #002
   - Status shows: `[REC #002 - Press 'r' for PRE]`

### Example Session

```
# Recording 001
Press 'r' → captures pre-frame
Place dart in T20
Press 'c' → captures post-frame
Type: T20

# Recording 002
Press 'r' → captures pre-frame
Place dart in bull
Press 'c' → captures post-frame
Type: bull

# Recording 003
Press 'r' → captures pre-frame
Place 2 darts crossing
Press 'c' → captures post-frame
Type: two_darts_crossing
```

## Output Files

All files saved to `data/recordings/`:

```
001_cam0_pre_T20.jpg
001_cam0_post_T20.jpg
001_cam1_pre_T20.jpg
001_cam1_post_T20.jpg
001_cam2_pre_T20.jpg
001_cam2_post_T20.jpg

002_cam0_pre_bull.jpg
002_cam0_post_bull.jpg
...
```

**Naming format:** `{number}_cam{0,1,2}_{pre|post}_{description}.jpg`

## Key Points

- **6 images per recording** (3 cameras × 2 frames)
- **Pre-frame** = board state before dart (clean or with existing darts)
- **Post-frame** = board state with new dart
- **Description** = human-readable label for test case
- **Auto-increment** = recording number increases automatically
- **No detection** = just raw image capture, no processing

## Next Steps

After recording images:

1. **Annotate ground truth** - Use `tools/annotate_ground_truth.py` to click tip positions
2. **Run regression tests** - Use `pytest tests/test_detection_regression.py` to validate detection

## Why Pre/Post Pairs?

Regression tests need to run the same detection algorithm as production:

```python
# Production detection
pre_frame = background_model.get_pre_impact(camera_id)
post_frame = background_model.get_post_impact(camera_id)
tip_x, tip_y, conf, _ = detector.detect(pre_frame, post_frame)

# Regression test (same algorithm)
pre_frame = cv2.imread("001_cam0_pre_T20.jpg")
post_frame = cv2.imread("001_cam0_post_T20.jpg")
tip_x, tip_y, conf, _ = detector.detect(pre_frame, post_frame)
```

This accounts for lighting changes over time - the diff between pre/post is what matters, not absolute brightness.
