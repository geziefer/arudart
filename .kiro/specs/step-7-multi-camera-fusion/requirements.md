# Step 7: Multi-Camera Fusion and Score Derivation

## Overview

Combine per-camera dart tip detections into a single best estimate in board coordinates, then derive the dart score (sector and ring). This is the core scoring logic that transforms raw detections into game-relevant information.

## User Stories

### US-7.1: Multi-Camera Coordinate Fusion
**As a** system  
**I want to** combine dart tip coordinates from multiple cameras into a single fused position  
**So that** I can leverage redundancy and improve accuracy over single-camera detection

**Acceptance Criteria:**
- AC-7.1.1: System collects valid detections from all 3 cameras (with coordinates and confidence)
- AC-7.1.2: If only 1 camera detects, use its coordinate directly
- AC-7.1.3: If 2+ cameras detect, compute weighted average by confidence
- AC-7.1.4: Outlier rejection: discard detections >50mm from median position
- AC-7.1.5: Fused coordinate has combined confidence score
- AC-7.1.6: System logs which cameras contributed to fusion

### US-7.2: Cartesian to Polar Conversion
**As a** system  
**I want to** convert fused board coordinates (x, y) to polar coordinates (r, θ)  
**So that** I can determine which ring and sector the dart hit

**Acceptance Criteria:**
- AC-7.2.1: Radius r computed as `sqrt(x² + y²)`
- AC-7.2.2: Angle θ computed using `atan2(y, x)` in radians
- AC-7.2.3: Angle normalized to [0, 2π) range
- AC-7.2.4: Conversion handles edge case (0, 0) → r=0, θ=0
- AC-7.2.5: Conversion is invertible (polar → cartesian → polar gives same result)

### US-7.3: Ring Determination
**As a** system  
**I want to** determine which ring the dart hit based on radius  
**So that** I can apply the correct score multiplier

**Acceptance Criteria:**
- AC-7.3.1: Bull (r < 6.35mm): score 50, multiplier N/A
- AC-7.3.2: Single bull (6.35mm ≤ r < 15.9mm): score 25, multiplier N/A
- AC-7.3.3: Triple ring (99mm ≤ r < 107mm): multiplier 3
- AC-7.3.4: Double ring (162mm ≤ r < 170mm): multiplier 2
- AC-7.3.5: Single ring (all other valid positions): multiplier 1
- AC-7.3.6: Out of bounds (r ≥ 170mm): score 0

### US-7.4: Sector Determination
**As a** system  
**I want to** determine which sector (1-20) the dart hit based on angle  
**So that** I can compute the base score

**Acceptance Criteria:**
- AC-7.4.1: Sector mapping follows standard dartboard layout: 20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5 (clockwise from top)
- AC-7.4.2: Each sector spans 18° (20° wedge with 2° wire gap)
- AC-7.4.3: Sector 20 centered at θ=0° (top of board)
- AC-7.4.4: Angle offset accounts for camera mounting rotation
- AC-7.4.5: Sector determination handles angle wraparound (359° → 0°)

### US-7.5: Score Calculation
**As a** system  
**I want to** compute the final dart score from sector and ring  
**So that** I can report the game-relevant score to the user

**Acceptance Criteria:**
- AC-7.5.1: Bull: score = 50 (no sector)
- AC-7.5.2: Single bull: score = 25 (no sector)
- AC-7.5.3: Other rings: score = sector_number × multiplier
- AC-7.5.4: Score includes base number, multiplier, and total
- AC-7.5.5: Score includes board coordinates (x, y, r, θ) for debugging

### US-7.6: Dart Hit Event Creation
**As a** system  
**I want to** create a structured `DartHitEvent` with all detection and scoring information  
**So that** downstream systems (logging, API, UI) have complete throw data

**Acceptance Criteria:**
- AC-7.6.1: Event includes timestamp (ISO 8601 format)
- AC-7.6.2: Event includes board coordinates (x, y in mm)
- AC-7.6.3: Event includes polar coordinates (r, θ)
- AC-7.6.4: Event includes score (base, multiplier, total)
- AC-7.6.5: Event includes per-camera detection data (coordinates, confidence)
- AC-7.6.6: Event includes image paths for annotated images
- AC-7.6.7: Event is JSON-serializable

## Technical Constraints

- Fusion must handle 0-3 valid detections per throw
- Coordinate mapping depends on Step 6 (calibration)
- Board dimensions from Winmau Blade 6 specifications
- Sector angle offset must be configurable (depends on camera mounting)
- Fusion algorithm must complete in <10ms (real-time requirement)

## Edge Cases

- **No detections**: Return null event, log warning
- **Single detection**: Use directly, mark as low confidence
- **Conflicting detections**: Use outlier rejection, log discarded cameras
- **Bull vs Single Bull boundary**: Use strict radius thresholds
- **Sector boundary**: Dart on wire → use closest sector center
- **Out of bounds**: Score = 0, log as miss

## Dependencies

- Step 6: Coordinate mapping (intrinsic + extrinsic calibration)
- Step 5: Multi-camera detection (per-camera tip coordinates)
- Configuration system (board dimensions, sector offset)
- Event model (DartHitEvent dataclass)

## Success Metrics

- Fusion accuracy: >90% correct sector/ring for test throws
- Fusion latency: <10ms average
- Outlier rejection: Correctly discards bad detections in >95% of cases
- Score derivation: 100% correct for known control points (T20, bull, etc.)
- Event completeness: All fields populated for valid detections
