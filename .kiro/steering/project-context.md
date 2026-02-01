# ARU-DART Project Context

## Project Overview

Automatic dartboard scoring system using 3 USB cameras (OV9732) at 120° intervals around a Winmau Blade 6 Triple Core board. The system detects dart throws via image differencing and multi-camera fusion.

## Hardware Setup

- **Raspberry Pi 4**: Active cooling, slightly overclocked
- **3 OV9732 USB Cameras**: 1280×720, MJPG, ~100° FOV, 120° spacing
- **LED Ring**: Provides stable, even illumination
- **Board**: Winmau Blade 6 Triple Core (standard 17" diameter)

## Dartboard Terminology

Standard dartboard scoring abbreviations:
- **BS** = Big Single (outer single ring, larger area)
- **SS** = Small Single (inner single ring, smaller area between triple and bull)
- **T** = Triple (triple ring)
- **D** = Double (outer double ring)
- **SB** = Single Bull (outer bull, 25 points)
- **DB** = Double Bull (inner bull/bullseye, 50 points)
- **O** = Out (missed the board entirely)

Example: BS20 = Big Single 20 (outer single area of sector 20)

## Camera Positions

- **cam0**: Upper right (near sector 18)
- **cam1**: Lower right (near sector 17)  
- **cam2**: Left (near sector 11)

## Current Status (Phase 1 - POC)

- ✅ Steps 0-5 complete: Multi-camera detection working
- ⏳ Step 5.5 in progress: Regression testing infrastructure
- 📋 Steps 6-10 planned: Calibration, fusion, state machine, API, validation

## Technology Stack

- **Language**: Python 3.x
- **Computer Vision**: OpenCV (cv2)
- **Camera Control**: 
  - macOS: uvc-util (local binary)
  - Linux: v4l2-ctl (system-wide)
- **Future API**: FastAPI + WebSockets (Step 9)

## Key Design Principles

1. **Fixed exposure**: Manual camera control prevents auto-adjustment drift
2. **Per-camera tuning**: Each camera needs individual exposure/contrast/gamma
3. **Image differencing**: Pre/post frame comparison for dart detection
4. **Multi-camera redundancy**: At least 2/3 cameras should detect each throw
5. **Shape-based detection**: Prioritize elongated, non-circular contours
6. **Y-coordinate heuristic**: Tip always has larger Y than flight (embedded vs sticking out)

## Development Workflow

- **Dev mode**: `--dev-mode` flag enables preview windows and verbose logging
- **Manual testing**: `--manual-test` flag for pause/play controlled testing
- **Single camera**: `--single-camera N` for per-camera validation
- **Recording mode**: `--record-mode` for regression test dataset capture

## Spec-Driven Development Guidelines

### Design Document Style

- **High-level architecture**: Design documents should focus on architecture, algorithms, and data flow
- **Pseudocode over Python**: Use pseudocode or high-level descriptions instead of extensive Python code
- **Interface definitions**: Show method signatures and data structures, not full implementations
- **Algorithm descriptions**: Describe algorithms in plain language or pseudocode, not complete code
- **Keep it concise**: Design documents should be readable and maintainable, not code repositories

**Example - Good (pseudocode)**:
```
fuse_detections(detections):
    1. Filter by minimum confidence
    2. If single detection: return directly
    3. If multiple: compute weighted average
    4. Return fused position
```

**Example - Avoid (extensive Python)**:
```python
def fuse_detections(self, detections: list[dict]) -> tuple[float, float, float, list[int]] | None:
    valid_detections = [d for d in detections if d['confidence'] >= self.min_confidence]
    if len(valid_detections) == 0:
        return None
    # ... 50 more lines of implementation ...
```

**Rationale**: Design documents are for understanding architecture and approach. Full implementations belong in the actual code files during task execution.
