# ARU-DART

Automatic Recognition Unit for Darts — an autoscoring system using 3 USB cameras mounted on an LED ring around a steel-tip dartboard.

Development supported by Amazon Kiro.

## Hardware Setup

- Winmau Blade 6 Triple Core board (standard 17" diameter)
- 3 OV9732 USB cameras at 120° intervals (800×600, MJPG)
- LED ring for stable illumination
- Raspberry Pi 4 (or macOS for development)
- Colored dart flights recommended (black flights reduce detection accuracy)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run 3-dart game mode (recommended)
python main.py --state-machine --dev-mode

# Run single-dart throw mode
python main.py --single-dart-test --dev-mode

# Run manual placement mode
python main.py --manual-dart-test --dev-mode
```

## Game Modes

### State Machine Mode (3-dart rounds)
```bash
python main.py --state-machine --dev-mode
```
Full game cycle: throw 3 darts → scores displayed → pull out darts → 2s cooldown → next round. Detects dart impacts via motion, scores each throw, counts to 3, then waits for pull-out before resetting.

### Single Dart Test (thrown darts)
```bash
python main.py --single-dart-test --dev-mode
```
Throw a dart, system detects impact and scores it. Remove dart, system resets background, ready for next throw. One dart at a time.

### Manual Dart Test (place by hand)
```bash
python main.py --manual-dart-test --dev-mode
```
Timed cycle: stabilize → "PUT IN NOW" (7s countdown) → detect → show result → "REMOVE DART" → repeat. For testing without throwing.


## Accuracy Testing

### Known Position Test
```bash
# Original 14-position set (DB, SB, T/D/BS/SS for sectors 20, 1, 5)
python main.py --accuracy-test --dev-mode

# Per-ring test across all 20 sectors
python main.py --accuracy-test --ring T --dev-mode   # Triples
python main.py --accuracy-test --ring D --dev-mode   # Doubles
python main.py --accuracy-test --ring BS --dev-mode  # Big singles
python main.py --accuracy-test --ring SS --dev-mode  # Small singles
```
Guides you through placing darts at specific board positions, compares detected vs expected scores, generates accuracy report.

### Feedback Mode (score confirmation)
```bash
python main.py --single-dart-test --feedback-mode --dev-mode
python main.py --manual-dart-test --feedback-mode --dev-mode
```
After each detection, shows score on screen with "Correct? (y)es / (n)o". Press y/n in the camera window. Feedback stored in `data/feedback/correct/` and `data/feedback/incorrect/`.

### Feedback Analysis
```bash
PYTHONPATH=. python scripts/analyze_feedback.py        # Accuracy report
PYTHONPATH=. python scripts/generate_heatmaps.py       # Board heatmap images
PYTHONPATH=. python scripts/export_dataset.py           # ML training dataset CSV
```

## Calibration

```bash
python main.py --calibrate --dev-mode              # Manual calibration
python main.py --calibrate-intrinsic --dev-mode    # Chessboard intrinsic calibration
python main.py --verify-calibration --dev-mode     # Verify calibration accuracy
```

Keyboard shortcuts in dev mode:
- `c` — trigger manual calibration
- `v` — toggle spiderweb overlay (projected board grid)

## All CLI Flags

| Flag | Description |
|------|-------------|
| `--config PATH` | Config file (default: config.toml) |
| `--dev-mode` | Enable camera preview windows |
| `--state-machine` | 3-dart round mode with pull-out detection |
| `--single-dart-test` | Single dart throw mode (motion-detected) |
| `--manual-dart-test` | Manual placement mode (countdown-based) |
| `--accuracy-test` | Test against known board positions |
| `--ring T\|D\|BS\|SS` | Ring filter for accuracy test |
| `--feedback-mode` | Enable score confirmation UI |
| `--diagnostics` | Enable per-throw JSON logging |
| `--calibrate` | Run manual calibration at startup |
| `--calibrate-intrinsic` | Run chessboard calibration |
| `--verify-calibration` | Run calibration verification |
| `--manual-test` | Legacy manual test (pause/place/detect) |
| `--record-mode` | Capture images for regression tests |
| `--single-camera N` | Test single camera (0, 1, or 2) |
| `--show-histogram` | Show RGB histogram overlay |

## Accuracy Results

| Ring | Manual Placement | Live Throws (colored flights) |
|------|-----------------|-------------------------------|
| Triples | 100% (20/20) | ~94% |
| Big Singles | 100% (20/20) | ~94% |
| Small Singles | 100% (20/20) | ~94% |
| Doubles | 80% (16/20) | ~80% |
| Bulls | 100% | 100% |

Doubles are the hardest ring — at the 170mm board edge where sub-mm calibration precision matters most.

## Project Structure

```
src/
├── calibration/          # Coordinate mapping, board geometry
├── camera/               # Camera management
├── processing/           # Motion detection, dart detection, background model
├── fusion/               # Multi-camera fusion, scoring, dart hit events
├── state_machine/        # Throw lifecycle (3-dart rounds, pull-out)
├── feedback/             # Score parser, feedback collection, storage
├── analysis/             # Accuracy analyzer, heatmaps, dataset export
├── diagnostics/          # Diagnostic logging, accuracy test runner
└── util/                 # Logging, metrics

scripts/
├── analyze_feedback.py   # Generate accuracy report from feedback data
├── generate_heatmaps.py  # Generate board accuracy heatmaps
└── export_dataset.py     # Export verified dataset for ML training

tests/                    # Unit tests + property-based tests (hypothesis)
data/
├── feedback/             # Feedback storage (correct/incorrect)
├── diagnostics/          # Per-session diagnostic data
├── throws/               # Per-session throw images
└── recordings/           # Regression test recordings
```

## Documentation

- `.kiro/steering/project-context.md` — Project overview and current status
- `.kiro/steering/development-knowledge.md` — Lessons learned, tuned parameters, CLI reference
- `.kiro/specs/` — Spec-driven development documents (requirements, design, tasks per step)
