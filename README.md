# arudart
Autoscoring Recognition Unit for Darts

A darts autoscoring system for my home setup with 3 cameras mounted on LED ring on stelldart board.

Development is supported heavily by Amazon Kiro.

---

## Documentation

- **[Project Overview](project.md)** - System architecture and requirements
- **[Implementation Plan](IMPLEMENTATION_PLAN.md)** - Step-by-step development plan and progress
- **[Testing Plan](TESTING_PLAN.md)** - Test cases and validation procedures
- **[Development Knowledge](DEVELOPMENT_KNOWLEDGE.md)** - Code structure and technical details
- **[Lessons Learned](LESSONS_LEARNED.md)** - Key insights and design decisions

---

## Usage

### Normal Operation Mode (Automatic Detection)

Runs continuous dart detection with motion-based triggering:

```bash
python main.py --dev-mode
```

**Features:**
- Automatic background initialization (2 seconds after startup)
- Motion detection triggers dart detection
- Saves annotated images per throw
- Multi-camera detection (all 3 cameras)

**Controls:**
- `r` - Reset background (after removing darts)
- `q` - Quit

---

### Manual Testing Mode

Controlled testing with pause/play for precise dart placement:

```bash
python main.py --dev-mode --manual-test
```

**Workflow:**
1. Press `p` to pause
2. Place dart manually
3. Press `p` again to trigger detection
4. Remove dart, press `r` to reset
5. Repeat

**Use cases:**
- Test specific dart positions
- Validate detection accuracy
- Run test cases (TC0-TC6)

---

### Recording Mode (Regression Test Dataset)

Capture raw image pairs (pre+post) for regression testing without running detection:

```bash
python main.py --dev-mode --record-mode
```

**Mode Selection:**
- Press `1` for single dart recording
- Press `3` for 3-dart sequence recording

**Single Dart Workflow:**
1. Press `c` to capture PRE frame (clean board)
2. Place dart on board
3. Press `c` to capture POST frame (with dart)
4. Type description (e.g., "BS1", "T20")
5. Press Enter to save

**3-Dart Sequence Workflow:**
1. Press `c` to capture PRE frame (clean board)
2. Place dart 1
3. Press `c` to capture POST frame
4. Type description for dart 1 (e.g., "T20")
5. Place dart 2 (dart 1 stays)
6. Press `c` to capture POST frame
7. Type description for dart 2 (e.g., "T19")
8. Place dart 3 (dart 1+2 stay)
9. Press `c` to capture POST frame
10. Type description for dart 3 (e.g., "T20")
11. All 6 images saved

**Output:**
- Images saved to `data/recordings/`
- Single dart format: 
  - `001_cam0_BS1_throw1_pre.jpg`
  - `001_cam0_BS1_throw1_post.jpg`
- 3-dart sequence format:
  - `001_cam0_T20_throw1_pre.jpg` / `_post.jpg`
  - `001_cam0_T19_throw2_pre.jpg` / `_post.jpg`
  - `001_cam0_T20_throw3_pre.jpg` / `_post.jpg`

**Use cases:**
- Single dart: Basic detection testing
- 3-dart sequence: Multi-dart scenarios, state machine testing
- Paired images ensure reliable regression tests with matched lighting

**Next steps:**
1. **Annotate ground truth:** `python tools/annotate_ground_truth.py`
2. **Run regression tests:** `python tools/run_regression_tests.py`

---

### Regression Testing

After recording and annotating images, run automated regression tests:

```bash
# Run with default tolerance (10 pixels)
python tools/run_regression_tests.py

# Run with custom tolerance
python tools/run_regression_tests.py --tolerance 20
```

**Options:**
- `--tolerance PIXELS` - Position error tolerance in pixels (default: 10)
  - 10px: Strict (2-3mm on board)
  - 20px: Moderate (4-6mm on board)
  - 30px: Loose (7-9mm on board)

**Prerequisites:**
- Annotated ground truth files in `data/testimages/` (`.json` for each POST image)
- Paired pre/post images in `data/testimages/`:
  - `001_cam0_BS1_pre.jpg` - Clean board
  - `001_cam0_BS1_post.jpg` - With dart (annotated)
  - `001_cam0_BS1_post.json` - Ground truth

**Directory structure:**
```
data/
├── recordings/           # Working directory (recording + annotation)
│   ├── 001_cam0_BS1_pre.jpg
│   ├── 001_cam0_BS1_post.jpg
│   ├── 001_cam0_BS1_post.json
│   └── ...
└── testimages/           # Test dataset (organized, ready for regression tests)
    ├── 001_cam0_BS1_pre.jpg
    ├── 001_cam0_BS1_post.jpg
    ├── 001_cam0_BS1_post.json
    └── ...
```

**What it does:**
1. Loads pre-images (clean board) for each camera
2. For each test image:
   - Runs detection (pre-image + test image)
   - Compares detected tip with ground truth
   - Reports pass/fail (10px tolerance)
3. Generates summary statistics:
   - Overall pass rate
   - Per-camera pass rate
   - Per-ring pass rate (BS, SS, D, T, SB, DB)

**Output:**
- Console: Real-time test results
- `tests/regression_report.txt`: Summary report

**Use cases:**
- Verify detection quality after code changes
- Catch regressions before committing
- Measure detection accuracy per sector type
- Baseline for future optimizations

---

### Annotation Tool (Ground Truth Creation)

After recording images, annotate dart tip positions for regression testing:

```bash
python tools/annotate_ground_truth.py
```

**Workflow:**
1. Tool displays first unannotated image
2. Click on dart tip position
3. Press `s` to save annotation
4. Automatically moves to next camera (cam0 → cam1 → cam2)
5. Repeats for all recordings

**Controls:**
- **Click** - Mark tip position (shows green circle)
- `s` - Save annotation and continue
- `n` - Skip image (no dart visible in this camera)
- `q` - Quit annotation session

**Output:**
- Creates JSON file for each image: `001_cam0_BS_20.json`
- Format:
  ```json
  {
    "image": "001_cam0_BS_20.jpg",
    "tip_x": 450,
    "tip_y": 280,
    "description": "BS_20",
    "expected_ring": "BS",
    "expected_number": 20
  }
  ```
- Automatically parses sector from filename (BS_20, T_19, SB, DB, etc.)

**Supported sector formats:**
- `BS_<number>` - Big Single (1-20)
- `SS_<number>` - Small Single (1-20)
- `D_<number>` - Double (1-20)
- `T_<number>` - Triple (1-20)
- `SB` or `SB_<direction>` - Single Bull (25)
- `DB` - Double Bull (50)

**Features:**
- Shows crosshair at mouse position for precision
- Groups images by recording number (annotate all 3 cameras of same throw together)
- Skips already-annotated images
- Progress tracking (shows count of annotated/skipped)

---

### Single-Camera Testing Mode

Test individual cameras before multi-camera fusion:

```bash
python main.py --dev-mode --manual-test --single-camera 0  # Test cam0
python main.py --dev-mode --manual-test --single-camera 1  # Test cam1
python main.py --dev-mode --manual-test --single-camera 2  # Test cam2
```

**Use cases:**
- Per-camera exposure/contrast tuning
- Validate detection on each camera independently
- Debug camera-specific issues

---

### Additional Options

**Show histogram:**
```bash
python main.py --dev-mode --show-histogram
```
- Displays RGB histogram overlay
- Useful for verifying exposure settings

**Custom config:**
```bash
python main.py --config custom_config.toml
```
- Load alternative configuration file

---

## Backend (Phase 1)
Python based system for image capturing and processing for detecting dart scores.

**Current Status:** Step 5 complete (multi-camera detection), Step 5.5 in progress (regression tests)

## Frontend (Phase 2)
Connect existing Flutter based App to backend for using darts as alternative input for local games.
