# Step 7.5: Human Feedback & Learning System

## Overview

Collect user feedback on detected scores during gameplay to build a verified dataset and identify systematic errors. This enables continuous improvement and provides ground truth data for future machine learning enhancements.

## User Stories

### US-7.5.1: Feedback Mode Operation
**As a** player  
**I want to** confirm or correct detected scores after each throw  
**So that** the system can learn from mistakes and improve over time

**Acceptance Criteria:**
- AC-7.5.1.1: System runs with `--feedback-mode` flag
- AC-7.5.1.2: After each detection, system displays detected score with confidence
- AC-7.5.1.3: User prompted with options: 'y' (correct), 'n' (wrong), 'c' (correct with manual entry)
- AC-7.5.1.4: If wrong, system prompts for actual score (e.g., "T20", "D16", "25")
- AC-7.5.1.5: Feedback collection doesn't interrupt game flow (< 5 seconds per throw)
- AC-7.5.1.6: User can skip feedback with 's' key (uses detected score)

### US-7.5.2: Feedback Data Storage
**As a** system  
**I want to** store feedback data with complete detection context  
**So that** I can analyze failures and improve detection algorithms

**Acceptance Criteria:**
- AC-7.5.2.1: Feedback stored in `data/feedback/` directory
- AC-7.5.2.2: Each throw saved with:
  - Metadata JSON (detected score, actual score, confidence, timestamp)
  - Images from all 3 cameras (pre, post, annotated)
  - Detection coordinates from each camera
  - Fused coordinates and score derivation
- AC-7.5.2.3: Feedback organized by correctness: `correct/` and `incorrect/` subdirectories
- AC-7.5.2.4: Filenames include timestamp and score for easy browsing
- AC-7.5.2.5: Storage is append-only (never overwrites existing feedback)

### US-7.5.3: Accuracy Analysis
**As a** developer  
**I want to** analyze feedback data to identify systematic errors  
**So that** I can prioritize improvements and tune detection parameters

**Acceptance Criteria:**
- AC-7.5.3.1: Analysis script computes overall accuracy (correct detections / total throws)
- AC-7.5.3.2: Per-sector accuracy computed (identify problematic sectors)
- AC-7.5.3.3: Per-ring accuracy computed (singles vs doubles vs triples)
- AC-7.5.3.4: Confusion matrix generated (detected vs actual scores)
- AC-7.5.3.5: Analysis identifies top 5 failure modes (e.g., "T20 detected as S20")
- AC-7.5.3.6: Results exported to `data/feedback/analysis_report.txt`

### US-7.5.4: Accuracy Heatmap
**As a** developer  
**I want to** visualize detection accuracy across the dartboard  
**So that** I can identify spatial patterns in errors

**Acceptance Criteria:**
- AC-7.5.4.1: Heatmap generated as image showing accuracy per board region
- AC-7.5.4.2: Color coding: green (>90% accurate), yellow (70-90%), red (<70%)
- AC-7.5.4.3: Heatmap overlaid on dartboard image for intuitive interpretation
- AC-7.5.4.4: Separate heatmaps for singles, doubles, triples
- AC-7.5.4.5: Heatmap saved to `data/feedback/accuracy_heatmap.png`

### US-7.5.5: Verified Dataset Export
**As a** developer  
**I want to** export verified feedback data in a standard format  
**So that** I can use it for future machine learning training

**Acceptance Criteria:**
- AC-7.5.5.1: Export script creates CSV with columns: timestamp, camera_id, image_path, tip_x, tip_y, actual_score, confidence
- AC-7.5.5.2: Only correct detections included in verified dataset
- AC-7.5.5.3: Dataset includes balanced samples across all sectors and rings
- AC-7.5.5.4: Dataset split into train/validation/test sets (70/15/15)
- AC-7.5.5.5: Export includes README with dataset statistics and usage instructions

## Feedback Workflow

1. **Throw dart** → System detects and displays score
2. **User feedback** → Confirm or correct score
3. **Data storage** → Save complete detection context
4. **Continue playing** → Repeat for next throw
5. **Periodic analysis** → Run analysis script after session

## Technical Constraints

- Feedback mode must not significantly slow down gameplay
- Storage must handle 100+ throws per session without performance degradation
- Analysis must complete in <10 seconds for 1000 throws
- Heatmap generation requires matplotlib or similar visualization library
- Dataset export must be compatible with common ML frameworks (PyTorch, TensorFlow)

## Score Input Format

User can enter scores in natural format:
- **Singles**: "20", "S20", "1", "S1"
- **Doubles**: "D20", "D1", "double 20"
- **Triples**: "T20", "T1", "triple 20"
- **Bulls**: "25", "SB", "single bull"
- **Double Bull**: "50", "DB", "bull", "double bull"
- **Miss**: "0", "miss", "bounce"

## Dependencies

- Step 7: Multi-camera fusion and score derivation
- Step 6: Coordinate mapping
- Image storage system (from Step 5)
- Configuration system

## Success Metrics

- Feedback collection: <5 seconds per throw
- Storage: <100MB per 100 throws
- Analysis: Identifies top 5 failure modes
- Accuracy: Baseline measurement for future improvements
- Dataset: >500 verified throws across all board regions

## Future Enhancements (Out of Scope)

- Automatic feedback using external camera (verify dart position)
- Real-time accuracy display during gameplay
- Adaptive detection parameters based on feedback
- Machine learning model training pipeline
