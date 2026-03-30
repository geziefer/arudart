# Requirements Document

## Introduction

The ARU-DART multi-camera fusion currently uses equal-weight averaging across all 3 cameras, achieving 85.7% score accuracy (12/14 correct). Two systematic failure modes have been identified:

1. A single camera pair producing a wildly incorrect position (46mm deviation) drags the fused result off-target because the current outlier rejection only activates with 3+ detections and uses a generous 50mm threshold.
2. All cameras contribute equally regardless of the dart's angular position on the board, even though each camera has significantly better accuracy on its "near side" due to reduced perspective distortion and higher effective pixel density.

This feature improves fusion accuracy to >90% (target >95%) by introducing robust outlier rejection for 2-camera cases and angular proximity weighting based on each camera's known position relative to the board.

Explicitly out of scope: ring boundary tolerance or score-guessing heuristics. Accuracy improvements come solely from better coordinate fusion.

## Glossary

- **Fusion_Engine**: The coordinate fusion module (`CoordinateFusion`) that combines per-camera board coordinates into a single fused position.
- **Detection**: A single camera's dart tip observation, containing board coordinates (x, y) in mm, camera ID, and confidence score.
- **Inlier**: A detection that passes outlier rejection and contributes to the fused position.
- **Outlier**: A detection whose board coordinates deviate significantly from the consensus of other detections.
- **Angular_Weight**: A weight assigned to a detection based on the angular distance between the dart's board position and the camera's optimal viewing zone.
- **Camera_Anchor_Angle**: The board angle (in degrees) at which a camera has its best viewing perspective, corresponding to the sector directly in front of that camera.
- **Pairwise_Distance**: The Euclidean distance in mm between two detections' board coordinates.
- **Falloff_Parameter**: A configurable parameter controlling how rapidly angular weight decreases as a dart moves away from a camera's anchor angle.
- **Score_Calculator**: The orchestrator module (`ScoreCalculator`) that runs the full pipeline from fusion through scoring.

## Requirements

### Requirement 1: Pairwise Outlier Rejection for Two-Camera Detections

**User Story:** As a system operator, I want the fusion engine to detect and reject an outlier even when only two cameras report detections, so that a single bad detection does not corrupt the fused position.

#### Acceptance Criteria

1. WHEN exactly two detections pass the minimum confidence filter AND the pairwise distance between the two detections exceeds a configurable pairwise rejection threshold, THEN THE Fusion_Engine SHALL discard the detection with the lower confidence and use the remaining detection as the fused position.
2. WHEN exactly two detections pass the minimum confidence filter AND the pairwise distance is within the pairwise rejection threshold, THE Fusion_Engine SHALL retain both detections for weighted averaging.
3. THE Fusion_Engine SHALL use a default pairwise rejection threshold of 20mm, configurable via `fusion.pairwise_rejection_mm` in config.toml.
4. WHEN a detection is rejected by pairwise outlier rejection, THE Fusion_Engine SHALL log the rejected camera ID, the pairwise distance, and the threshold used.

### Requirement 2: Improved Three-Camera Outlier Rejection

**User Story:** As a system operator, I want the fusion engine to use a tighter outlier threshold for three-camera detections, so that a single camera producing a bad result is reliably excluded.

#### Acceptance Criteria

1. WHEN three detections pass the minimum confidence filter, THE Fusion_Engine SHALL compute the median position and reject any detection whose distance from the median exceeds the configurable outlier threshold.
2. THE Fusion_Engine SHALL use a default outlier threshold of 25mm for three-camera rejection, configurable via `fusion.outlier_threshold_mm` in config.toml.
3. WHEN a detection is rejected by median-based outlier rejection, THE Fusion_Engine SHALL log the rejected camera ID, the deviation distance, and the threshold.
4. IF all three detections are rejected as outliers, THEN THE Fusion_Engine SHALL fall back to using the detection with the highest confidence.

### Requirement 3: Angular Proximity Weighting

**User Story:** As a system operator, I want each camera's contribution to the fused position to be weighted by how close the dart is to that camera's optimal viewing zone, so that cameras with better perspective on the dart have more influence.

#### Acceptance Criteria

1. THE Fusion_Engine SHALL assign each camera a fixed anchor angle on the board: cam0 at 81° (sector 18 center), cam1 at 257° (sector 17 center), cam2 at 153° (sector 11 center), configurable via `fusion.camera_anchors` in config.toml.
2. WHEN computing the fused position from multiple inlier detections, THE Fusion_Engine SHALL compute an angular weight for each detection based on the angular distance between the dart's estimated board angle and that camera's anchor angle.
3. THE Fusion_Engine SHALL compute angular weight using a cosine-based falloff: `angular_weight = (1 + cos(angular_distance)) / 2`, where angular_distance is the shortest arc between the dart angle and the camera anchor angle.
4. THE Fusion_Engine SHALL combine angular weight with detection confidence to produce a final weight for each detection: `final_weight = confidence × angular_weight`.
5. THE Fusion_Engine SHALL compute the fused position as the weighted average of inlier detections using final weights.
6. THE Fusion_Engine SHALL use a configurable falloff parameter (default 1.0) via `fusion.angular_falloff` in config.toml that controls the sharpness of the angular weighting curve.
7. WHEN all inlier detections have angular weight below 0.1, THE Fusion_Engine SHALL fall back to confidence-only weighting to avoid numerical instability.

### Requirement 4: Two-Pass Fusion Strategy

**User Story:** As a system operator, I want the fusion to first estimate the dart's approximate angle for weighting purposes, then apply angular weights in a second pass, so that the angular weights are based on a reasonable position estimate.

#### Acceptance Criteria

1. WHEN multiple inlier detections are available, THE Fusion_Engine SHALL first compute a preliminary fused position using confidence-only weighted averaging (pass 1).
2. THE Fusion_Engine SHALL compute the board angle of the preliminary position using atan2.
3. THE Fusion_Engine SHALL then compute angular weights for each detection based on the preliminary angle and recompute the fused position using combined weights (pass 2).
4. WHEN only one inlier detection remains after outlier rejection, THE Fusion_Engine SHALL use that detection directly without angular weighting.

### Requirement 5: Fusion Diagnostics

**User Story:** As a system operator, I want the fusion engine to report detailed diagnostics about the weighting and rejection decisions, so that I can debug and tune the fusion parameters.

#### Acceptance Criteria

1. THE Fusion_Engine SHALL include in its return data: the per-camera angular weights, the per-camera final weights, and which cameras were rejected.
2. WHEN the Score_Calculator creates a DartHitEvent, THE Score_Calculator SHALL include the fusion diagnostics in the event metadata.
3. THE Fusion_Engine SHALL log at DEBUG level the per-detection angular distance, angular weight, confidence, and final weight for each fusion operation.

### Requirement 6: Configuration Defaults and Backward Compatibility

**User Story:** As a system operator, I want the improved fusion to work with the existing config.toml structure and fall back to sensible defaults, so that the system works without requiring config changes.

#### Acceptance Criteria

1. THE Fusion_Engine SHALL operate correctly with the existing config.toml format, using default values for any new parameters not present in the configuration.
2. THE Fusion_Engine SHALL use these defaults when parameters are absent: `pairwise_rejection_mm = 20.0`, `outlier_threshold_mm = 25.0`, `angular_falloff = 1.0`, `camera_anchors = {cam0: 81, cam1: 257, cam2: 153}`.
3. WHEN `fusion.camera_anchors` is not configured, THE Fusion_Engine SHALL use the default anchor angles and log a warning that default camera positions are being used.
4. THE Fusion_Engine SHALL maintain the existing return type signature `(fused_x, fused_y, confidence, cameras_used)` from `fuse_detections()` so that the Score_Calculator requires no changes to its calling code.

### Requirement 7: Accuracy Target

**User Story:** As a system operator, I want the improved fusion to achieve measurably better scoring accuracy on the existing test dataset, so that the improvement is validated.

#### Acceptance Criteria

1. WHEN evaluated against the Session_005 accuracy dataset (14 throws), THE Fusion_Engine SHALL achieve a score match rate of at least 90%.
2. WHEN evaluated against the Session_005 accuracy dataset, THE Fusion_Engine SHALL reduce the maximum position error below 25mm (currently 46.2mm).
3. WHEN evaluated against the Session_005 accuracy dataset, THE Fusion_Engine SHALL reduce the mean position error below 6mm (currently 7.7mm).
