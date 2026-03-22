# Requirements Document

## Introduction

The ARU-DART system currently scores darts through a multi-camera fusion pipeline (tip detection, calibration mapping, coordinate fusion, polar conversion, sector/ring classification), but accuracy is poor — roughly one-third of detections land on the correct sector. Calibration verification shows 2.6–9mm error per camera, and sector wedges are only 18° wide, so small positional errors cause wrong sector classification.

This feature adds two capabilities to diagnose and quantify the problem:

1. **Diagnostic logging** — structured JSON output per detection capturing the full pipeline state (per-camera pixel/board coords, fusion result, polar coords, classification) plus annotated camera images, so error patterns can be analyzed after a testing session.

2. **Accuracy test mode** — a test workflow where the user places darts at known board positions (e.g., "middle of T20", "BS5", "SB") and the system compares detected score/position against the expected values, building a test report with quantifiable accuracy metrics.

## Glossary

- **Diagnostic_Logger**: Module that captures and persists structured pipeline data for each dart detection.
- **Accuracy_Test_Runner**: Test mode that orchestrates known-position dart placements and compares detected results against expected values.
- **Test_Report_Generator**: Module that aggregates per-throw accuracy results into a summary report.
- **Detection_Record**: A structured data object containing the full pipeline state for a single dart detection.
- **Known_Position**: A predefined board location with expected score, board coordinates, ring, and sector.
- **Board_Geometry**: Existing module that computes board coordinates for sector/ring combinations.
- **Score_Calculator**: Existing pipeline orchestrator that produces DartHitEvent objects.
- **DartHitEvent**: Existing dataclass containing fused coordinates, polar data, score, and per-camera detections.
- **Camera_Deviation**: The Euclidean distance in mm between a single camera's mapped board coordinates and the fused position.

## Requirements

### Requirement 1: Detection Record Structure

**User Story:** As a developer, I want each dart detection to produce a structured diagnostic record containing the full pipeline state, so that I can analyze error patterns after a testing session.

#### Acceptance Criteria

1. WHEN a dart detection completes, THE Diagnostic_Logger SHALL produce a Detection_Record containing per-camera data: pixel coordinates (u, v), detection confidence, and mapped board coordinates (x, y in mm).
2. WHEN a dart detection completes, THE Diagnostic_Logger SHALL include in the Detection_Record the fused board coordinates (x, y in mm), the list of contributing camera IDs, and the Camera_Deviation for each contributing camera.
3. WHEN a dart detection completes, THE Diagnostic_Logger SHALL include in the Detection_Record the polar coordinates (radius in mm, angle in degrees), the ring classification name, the sector number, and the final score.
4. THE Detection_Record SHALL be serializable to JSON format.
5. THE Detection_Record SHALL be deserializable from JSON format back to an equivalent Detection_Record (round-trip property).

### Requirement 2: Diagnostic Session Logging

**User Story:** As a developer, I want diagnostic records saved to disk as JSON log files organized by session, so that I can review and compare sessions over time.

#### Acceptance Criteria

1. WHEN a diagnostic session starts, THE Diagnostic_Logger SHALL create a session directory under `data/diagnostics/` named with a timestamp and sequential session number.
2. WHEN a Detection_Record is produced, THE Diagnostic_Logger SHALL write the record as a JSON file in the current session directory, named with the throw number and timestamp.
3. WHEN a Detection_Record is produced, THE Diagnostic_Logger SHALL save annotated camera images (showing detected tip positions) into the session directory, one per contributing camera.
4. THE Diagnostic_Logger SHALL write a session summary JSON file containing the total throw count, the number of successful detections, and the average fusion confidence across the session.

### Requirement 3: Diagnostic Integration with Existing Test Modes

**User Story:** As a developer, I want diagnostic logging to work with the existing `--manual-dart-test` and `--single-dart-test` modes, so that I can capture diagnostics during normal testing without a separate workflow.

#### Acceptance Criteria

1. WHEN the `--diagnostics` flag is provided, THE System SHALL enable diagnostic logging for the active test mode (`--manual-dart-test` or `--single-dart-test`).
2. WHILE diagnostic logging is enabled, THE Diagnostic_Logger SHALL capture a Detection_Record for every dart detection that produces a DartHitEvent.
3. WHILE diagnostic logging is enabled, THE System SHALL display the session directory path at startup.
4. IF the `--diagnostics` flag is provided without a test mode flag, THEN THE System SHALL report an error message and exit.

### Requirement 4: Known Position Definition

**User Story:** As a developer, I want a catalog of known board positions with expected coordinates and scores, so that accuracy testing has a ground truth to compare against.

#### Acceptance Criteria

1. THE Accuracy_Test_Runner SHALL define known positions for at minimum: DB (double bull), SB (single bull), T20, T1, T5, D20, D1, D5, BS20, BS1, BS5, SS20, SS1, SS5.
2. FOR EACH known position, THE Accuracy_Test_Runner SHALL store the expected board coordinates (x, y in mm), expected ring name, expected sector number, and expected total score.
3. THE Accuracy_Test_Runner SHALL compute expected board coordinates using the Board_Geometry module (center of the target ring at the sector angle).
4. WHEN the user starts accuracy test mode, THE Accuracy_Test_Runner SHALL allow the user to select a subset of known positions to test, or test all positions.

### Requirement 5: Accuracy Test Workflow

**User Story:** As a developer, I want a test mode where I place darts at known positions and the system automatically compares detected vs expected results, so that I can quantify scoring accuracy.

#### Acceptance Criteria

1. WHEN the `--accuracy-test` flag is provided, THE System SHALL enter accuracy test mode.
2. FOR EACH known position in the test sequence, THE Accuracy_Test_Runner SHALL display the target position name on the camera windows (e.g., "Place dart at: T20").
3. THE Accuracy_Test_Runner SHALL use the same detection pipeline as `--manual-dart-test` (countdown-based: stabilize, place, detect, result, remove cycle).
4. WHEN a dart is detected at a known position, THE Accuracy_Test_Runner SHALL compute the position error as the Euclidean distance in mm between the fused board coordinates and the expected board coordinates.
5. WHEN a dart is detected at a known position, THE Accuracy_Test_Runner SHALL compute the angular error in degrees between the detected angle and the expected angle.
6. WHEN a dart is detected at a known position, THE Accuracy_Test_Runner SHALL determine whether the detected ring matches the expected ring, and whether the detected sector matches the expected sector.
7. WHEN a dart is detected at a known position, THE Accuracy_Test_Runner SHALL display the comparison results on the camera windows: expected score, detected score, position error in mm, and whether ring/sector matched.

### Requirement 6: Accuracy Test Report

**User Story:** As a developer, I want a summary report after an accuracy test session showing overall and per-region accuracy metrics, so that I can identify systematic error patterns.

#### Acceptance Criteria

1. WHEN an accuracy test session completes, THE Test_Report_Generator SHALL produce a JSON report file in the session directory.
2. THE Test_Report_Generator SHALL include overall metrics: total throws, sector match rate (percentage), ring match rate (percentage), exact score match rate (percentage), mean position error in mm, and max position error in mm.
3. THE Test_Report_Generator SHALL include per-throw detail: target position name, expected score, detected score, position error in mm, angular error in degrees, ring match (boolean), and sector match (boolean).
4. THE Test_Report_Generator SHALL include per-camera metrics: mean Camera_Deviation in mm and max Camera_Deviation in mm for each camera across all throws.
5. WHEN an accuracy test session completes, THE Test_Report_Generator SHALL print a human-readable summary to the console showing the overall metrics.
6. THE Test_Report_Generator SHALL serialize the report to JSON and deserialize it back to an equivalent report (round-trip property).

### Requirement 7: Per-Camera Error Analysis in Diagnostics

**User Story:** As a developer, I want to see how far each camera's individual estimate was from the fused position, so that I can identify cameras that consistently pull the result in one direction.

#### Acceptance Criteria

1. FOR EACH contributing camera in a Detection_Record, THE Diagnostic_Logger SHALL compute and store the Camera_Deviation as the Euclidean distance between that camera's board coordinates and the fused board coordinates.
2. FOR EACH contributing camera in a Detection_Record, THE Diagnostic_Logger SHALL compute and store the deviation vector (dx, dy in mm) from the fused position to that camera's board coordinates.
3. WHEN a diagnostic session completes, THE Diagnostic_Logger SHALL include per-camera aggregate statistics in the session summary: mean deviation, max deviation, and mean deviation vector (to reveal directional bias).
