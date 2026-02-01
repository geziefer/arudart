# ARU-DART Project Context

## Project Overview

Automatic dartboard scoring system using 3 USB cameras (OV9732) at 120° intervals around a Winmau Blade 6 Triple Core board. The system detects dart throws via image differencing and multi-camera fusion.

## Hardware Setup

- **Raspberry Pi 4**: Active cooling, slightly overclocked
- **3 OV9732 USB Cameras**: 1280×720, MJPG, ~100° FOV, 120° spacing
- **LED Ring**: Provides stable, even illumination
- **Board**: Winmau Blade 6 Triple Core (standard 17" diameter)

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
