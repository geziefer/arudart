# ARU-DART Specs Overview

This directory contains specifications for the remaining implementation steps (6-10) of the ARU-DART automatic dartboard scoring system.

## Spec Structure

Each spec follows the Kiro spec-driven development workflow:
1. **requirements.md** - User stories and acceptance criteria
2. **design.md** - Technical design and architecture (to be created)
3. **tasks.md** - Implementation tasks (to be created)

## Specs List

### Step 6: Coordinate Mapping
**Directory**: `step-6-coordinate-mapping/`  
**Status**: Requirements complete, ready for design  
**Goal**: Map camera pixel coordinates to board coordinate system using calibration

**Key Features:**
- Intrinsic camera calibration (lens distortion correction)
- ARUCO marker-based extrinsic calibration
- Homography transformation (image → board plane)
- Coordinate mapper with verification

**Dependencies**: Steps 1-5 (camera capture, detection)

---

### Step 7: Multi-Camera Fusion
**Directory**: `step-7-multi-camera-fusion/`  
**Status**: Requirements complete, ready for design  
**Goal**: Combine per-camera detections into single score

**Key Features:**
- Weighted coordinate fusion by confidence
- Outlier rejection
- Polar coordinate conversion
- Ring and sector determination
- Score calculation

**Dependencies**: Step 6 (coordinate mapping)

---

### Step 7.5: Feedback System
**Directory**: `step-7.5-feedback-system/`  
**Status**: Requirements complete, ready for design  
**Goal**: Collect user feedback to build verified dataset

**Key Features:**
- Interactive feedback mode
- Feedback data storage with images
- Accuracy analysis and heatmaps
- Verified dataset export for ML

**Dependencies**: Steps 6-7 (complete scoring pipeline)

---

### Step 8: State Machine
**Directory**: `step-8-state-machine/`  
**Status**: Requirements complete, ready for design  
**Goal**: Recognize throw sequences and emit events

**Key Features:**
- State machine (idle → throw → dart present → pull-out)
- Multiple dart tracking
- Bounce-out detection
- Throw miss detection
- Event model (DartHitEvent, DartRemovedEvent, etc.)

**Dependencies**: Step 7 (fusion and scoring)

---

### Step 9: Web API
**Directory**: `step-9-web-api/`  
**Status**: Requirements complete, ready for design  
**Goal**: Expose events and metrics over network

**Key Features:**
- REST endpoints (health, metrics)
- WebSocket event streaming
- JSON event format
- Multi-client support

**Dependencies**: Step 8 (event generation)

---

### Step 10: POC Validation
**Directory**: `step-10-poc-validation/`  
**Status**: Requirements complete, ready for design  
**Goal**: Validate complete system with structured testing

**Key Features:**
- Validation session execution (50-100 throws)
- Accuracy analysis
- Failure mode identification
- Performance metrics
- Validation report

**Dependencies**: Steps 1-9 (complete system)

---

## Implementation Order

1. **Step 6** (Coordinate Mapping) - Foundation for accurate scoring
2. **Step 7** (Multi-Camera Fusion) - Core scoring logic
3. **Step 8** (State Machine) - Game flow management
4. **Step 9** (Web API) - External interface
5. **Step 7.5** (Feedback System) - Continuous improvement (can be done in parallel with 8-9)
6. **Step 10** (POC Validation) - Final validation

## Property-Based Testing Strategy

**PBT Recommended For:**
- ✅ Coordinate transformations (Step 6): Homography properties, inverse transformations
- ✅ Fusion algorithms (Step 7): Weighted averaging, outlier rejection
- ✅ Score mapping (Step 7): Polar conversions, sector/ring determination

**Traditional Testing For:**
- ❌ Hardware-dependent code: Camera capture, image processing
- ❌ State machine (Step 8): Scenario-based integration tests
- ❌ API (Step 9): HTTP/WebSocket integration tests

## Next Steps

1. Review requirements for each spec
2. Create design documents (technical architecture)
3. Generate task lists from design
4. Execute tasks step-by-step
5. Run tests and validation

## Steering Files

The following steering files provide context for all specs:
- `.kiro/steering/development-knowledge.md` - Lessons learned and best practices
- `.kiro/steering/python-best-practices.md` - Python coding standards
- `.kiro/steering/project-context.md` - Project overview and hardware setup
