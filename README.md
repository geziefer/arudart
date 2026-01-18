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

Capture raw images for regression testing without running detection:

```bash
python main.py --dev-mode --record-mode
```

**Workflow:**
1. Place dart(s) on board
2. Press `c` to capture
3. Type description in overlay (e.g., "sector_20_triple")
4. Press Enter to save
5. Repeat for next recording

**Output:**
- Images saved to `data/recordings/`
- Format: `001_cam0_sector_20_triple.jpg`, `001_cam1_sector_20_triple.jpg`, etc.
- Auto-increments recording number

**Use cases:**
- Build regression test dataset
- Record edge cases
- Quick image capture without detection overhead

**Next steps:**
1. Annotate ground truth: `python tools/annotate_ground_truth.py` (to be implemented)
2. Run regression tests: `python tools/run_regression_tests.py` (to be implemented)

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
