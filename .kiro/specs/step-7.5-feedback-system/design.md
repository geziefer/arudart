# Step 7.5: Human Feedback & Learning System - Design Document

## Overview

This design document specifies the architecture for collecting human feedback on detected dart scores during gameplay, storing complete detection context, and analyzing the data to identify systematic errors. The system enables continuous improvement by building a verified dataset of ground truth scores.

The feedback system operates in a special `--feedback-mode` where after each dart detection, the user confirms or corrects the detected score. All feedback is stored with complete context (images, coordinates, fusion data) for later analysis. Analysis tools compute accuracy metrics, generate heatmaps, and export verified datasets for future machine learning enhancements.

**Key Design Principles**:
- Non-intrusive feedback collection (< 5 seconds per throw)
- Complete context storage (images + metadata + coordinates)
- Flexible score input parsing (natural language formats)
- Comprehensive analysis (accuracy, confusion matrix, failure modes)
- Verified dataset export for ML training
- Append-only storage (never overwrite existing data)

## Architecture

### Module Structure

```
src/feedback/
├── __init__.py
├── feedback_collector.py       # FeedbackCollector class (main interface)
├── score_parser.py             # ScoreParser class
├── feedback_storage.py         # FeedbackStorage class
└── feedback_prompt.py          # FeedbackPrompt class (user interaction)

src/analysis/
├── __init__.py
├── accuracy_analyzer.py        # AccuracyAnalyzer class
├── heatmap_generator.py        # HeatmapGenerator class
└── dataset_exporter.py         # DatasetExporter class

scripts/
├── analyze_feedback.py         # Analysis script (CLI)
├── generate_heatmaps.py        # Heatmap generation script (CLI)
└── export_dataset.py           # Dataset export script (CLI)

data/feedback/
├── correct/                    # Correct detections
│   ├── 20240115_143218_T20/
│   │   ├── metadata.json
│   │   ├── cam0_pre.jpg
│   │   ├── cam0_post.jpg
│   │   ├── cam0_annotated.jpg
│   │   ├── cam1_pre.jpg
│   │   ├── cam1_post.jpg
│   │   ├── cam1_annotated.jpg
│   │   ├── cam2_pre.jpg
│   │   ├── cam2_post.jpg
│   │   └── cam2_annotated.jpg
│   └── ...
├── incorrect/                  # Incorrect detections
│   ├── 20240115_143305_D20_actual_S20/
│   │   └── ... (same structure)
│   └── ...
├── analysis_report.txt         # Generated analysis report
├── accuracy_heatmap.png        # Overall accuracy heatmap
├── accuracy_heatmap_singles.png
├── accuracy_heatmap_doubles.png
├── accuracy_heatmap_triples.png
└── verified_dataset/           # Exported dataset
    ├── train.csv
    ├── validation.csv
    ├── test.csv
    └── README.md
```

### Class Hierarchy

```
FeedbackCollector (main interface)
├── Uses FeedbackPrompt for user interaction
├── Uses ScoreParser for input validation
├── Uses FeedbackStorage for data persistence
└── Integrates with main detection loop

ScoreParser
└── parse_score(input_string) → ParsedScore

FeedbackStorage
├── save_feedback(feedback_data) → feedback_id
├── load_all_feedback() → list of feedback entries
└── organize_by_correctness()

FeedbackPrompt
├── prompt_confirmation(detected_score, confidence) → user_response
└── prompt_score_input() → score_string

AccuracyAnalyzer
├── compute_overall_accuracy() → float
├── compute_per_sector_accuracy() → dict
├── compute_per_ring_accuracy() → dict
├── generate_confusion_matrix() → matrix
├── identify_failure_modes(top_n) → list
└── export_report(output_path)

HeatmapGenerator
├── generate_heatmap(accuracy_data, ring_filter) → image
└── save_heatmap(image, output_path)

DatasetExporter
├── filter_correct_detections() → verified_dataset
├── split_dataset(train_ratio, val_ratio, test_ratio) → splits
└── export_csv(dataset, output_path)
```

### Data Flow

```
Dart Detection (from Step 7)
    ↓
DartHitEvent (detected score, confidence, coordinates)
    ↓
[FeedbackPrompt.prompt_confirmation()]
    ↓
User Response ('y', 'n', 'c', 's')
    ↓
If 'n' or 'c': [FeedbackPrompt.prompt_score_input()]
    ↓
Score String (e.g., "T20", "D16", "25")
    ↓
[ScoreParser.parse_score()]
    ↓
ParsedScore (ring, sector, total)
    ↓
[FeedbackStorage.save_feedback()]
    ↓
Feedback Entry (metadata.json + images)
    ↓
Organized into correct/ or incorrect/ subdirectory
    ↓
[AccuracyAnalyzer.analyze()] (periodic)
    ↓
Analysis Report + Confusion Matrix + Failure Modes
    ↓
[HeatmapGenerator.generate()] (periodic)
    ↓
Accuracy Heatmaps (overall + per-ring)
    ↓
[DatasetExporter.export()] (periodic)
    ↓
Verified Dataset (train/val/test CSV + README)
```

### Integration with Existing System

The feedback system integrates after score derivation in the main detection loop:

```
main():
    # Parse command-line arguments
    feedback_mode = args.feedback_mode
    
    # Initialize components
    if feedback_mode:
        feedback_collector = FeedbackCollector(config)
    
    # Main loop
    while true:
        # ... existing motion detection and dart detection ...
        
        if motion_state == "dart_detected":
            # ... existing detection and fusion ...
            dart_hit_event = score_calculator.process_detections(detections)
            
            if dart_hit_event not null:
                # Display detected score
                display_score(dart_hit_event)
                
                # NEW: Collect feedback in feedback mode
                if feedback_mode:
                    feedback_collector.collect_feedback(dart_hit_event, image_paths)
                
                # Continue with game logic...
            
            motion_state = "idle"
```

## Components and Interfaces

### 1. FeedbackCollector Class

**Purpose**: Main interface for collecting user feedback during gameplay. Orchestrates prompting, parsing, and storage.

**Interface**:
```
FeedbackCollector:
    Components:
        feedback_prompt: FeedbackPrompt instance
        score_parser: ScoreParser instance
        feedback_storage: FeedbackStorage instance
    
    Methods:
        collect_feedback(dart_hit_event, image_paths) → feedback_id or null
            Input: DartHitEvent from Step 7, dictionary of image paths per camera
            Output: Unique feedback ID if saved, null if skipped
            
            Algorithm:
                1. Display detected score and confidence
                2. Prompt user for confirmation ('y', 'n', 'c', 's')
                3. If 'y' or 's': actual_score = detected_score
                4. If 'n' or 'c': prompt for actual score, parse input
                5. Determine correctness (detected == actual)
                6. Save feedback with complete context
                7. Return feedback_id
        
        display_detected_score(dart_hit_event)
            - Show score in clear format: "Detected: T20 (60 points), Confidence: 0.85"
```

### 2. ScoreParser Class

**Purpose**: Parse user score input in various natural language formats into structured score data.

**Interface**:
```
ScoreParser:
    Methods:
        parse_score(input_string) → ParsedScore or null
            Input: User input string (e.g., "T20", "D16", "25", "miss")
            Output: ParsedScore object or null if invalid
            
            Supported Formats:
                Singles: "20", "S20", "1", "single 20"
                Doubles: "D20", "D1", "double 20"
                Triples: "T20", "T1", "triple 20"
                Bulls: "25", "SB", "single bull"
                Double Bull: "50", "DB", "bull", "double bull"
                Miss: "0", "miss", "bounce"
            
            Algorithm:
                1. Normalize input (lowercase, strip whitespace)
                2. Try pattern matching in order:
                   a. Explicit ring prefix (T/D/S + number)
                   b. Bull variants (50, DB, bull, 25, SB)
                   c. Miss variants (0, miss, bounce)
                   d. Plain number (assume single)
                3. Extract ring and sector
                4. Validate sector (1-20 for regular, null for bulls/miss)
                5. Calculate total score
                6. Return ParsedScore(ring, sector, total)

ParsedScore:
    ring: string ("single", "double", "triple", "bull", "single_bull", "miss")
    sector: integer (1-20) or null
    total: integer (final score)
```

### 3. FeedbackStorage Class

**Purpose**: Persist feedback data with complete context (metadata, images) in organized directory structure.

**Interface**:
```
FeedbackStorage:
    Configuration:
        feedback_dir: "data/feedback/"
        correct_dir: "data/feedback/correct/"
        incorrect_dir: "data/feedback/incorrect/"
    
    Methods:
        save_feedback(feedback_data) → feedback_id
            Input: FeedbackData object with all context
            Output: Unique feedback ID (timestamp-based)
            
            Algorithm:
                1. Generate unique ID: timestamp + detected_score
                2. Determine subdirectory (correct/ or incorrect/)
                3. Create feedback directory: {subdir}/{id}/
                4. Save metadata.json with all data
                5. Copy images from temp to feedback directory
                6. Return feedback_id
        
        load_all_feedback() → list of FeedbackData
            - Scan correct/ and incorrect/ directories
            - Load all metadata.json files
            - Return list of FeedbackData objects
        
        get_feedback_by_id(feedback_id) → FeedbackData or null
            - Load specific feedback entry by ID

FeedbackData:
    feedback_id: string (timestamp-based unique ID)
    timestamp: string (ISO 8601)
    detected_score: ParsedScore
    actual_score: ParsedScore
    is_correct: boolean
    dart_hit_event: DartHitEvent (from Step 7)
    image_paths: dictionary mapping camera_id → image paths
    user_response: string ('y', 'n', 'c', 's')
```

### 4. FeedbackPrompt Class

**Purpose**: Handle user interaction for feedback collection with clear prompts and input validation.

**Interface**:
```
FeedbackPrompt:
    Methods:
        prompt_confirmation(detected_score, confidence) → user_response
            Input: Detected score string, confidence value
            Output: User response ('y', 'n', 'c', 's')
            
            Display:
                "Detected: {detected_score} ({total} points)"
                "Confidence: {confidence:.2f}"
                "Is this correct? (y)es / (n)o / (c)orrect score / (s)kip: "
            
            Validation:
                - Accept only 'y', 'n', 'c', 's' (case-insensitive)
                - Re-prompt on invalid input
                - Timeout after 30 seconds → default to 's' (skip)
        
        prompt_score_input() → score_string
            Display:
                "Enter actual score (e.g., T20, D16, 25, miss): "
            
            Validation:
                - Accept any string (parsed by ScoreParser)
                - Re-prompt if parsing fails
                - Show examples on repeated failures
```

### 5. AccuracyAnalyzer Class

**Purpose**: Analyze feedback data to compute accuracy metrics, confusion matrix, and identify failure modes.

**Interface**:
```
AccuracyAnalyzer:
    Methods:
        analyze(feedback_data_list) → AnalysisResults
            Input: List of all FeedbackData entries
            Output: AnalysisResults object with all metrics
            
            Algorithm:
                1. Compute overall accuracy
                2. Group by sector, compute per-sector accuracy
                3. Group by ring, compute per-ring accuracy
                4. Build confusion matrix (detected vs actual)
                5. Identify top N failure modes
                6. Return AnalysisResults
        
        compute_overall_accuracy(feedback_list) → float
            - Count correct detections
            - Divide by total throws
            - Return accuracy as percentage
        
        compute_per_sector_accuracy(feedback_list) → dict
            - Group feedback by actual sector
            - Compute accuracy for each sector
            - Return {sector: accuracy} mapping
        
        compute_per_ring_accuracy(feedback_list) → dict
            - Group feedback by actual ring
            - Compute accuracy for each ring type
            - Return {ring: accuracy} mapping
        
        generate_confusion_matrix(feedback_list) → matrix
            - Create 2D matrix: detected_score × actual_score
            - Count occurrences of each (detected, actual) pair
            - Return confusion matrix
        
        identify_failure_modes(feedback_list, top_n) → list
            - Filter incorrect detections
            - Group by (detected, actual) pair
            - Sort by frequency (descending)
            - Return top N failure modes with counts
        
        export_report(analysis_results, output_path)
            - Format analysis results as text report
            - Include all metrics and failure modes
            - Save to file

AnalysisResults:
    overall_accuracy: float
    per_sector_accuracy: dict
    per_ring_accuracy: dict
    confusion_matrix: 2D array
    failure_modes: list of (detected, actual, count) tuples
    total_throws: integer
    correct_throws: integer
    incorrect_throws: integer
```

### 6. HeatmapGenerator Class

**Purpose**: Generate visual heatmaps showing detection accuracy across different board regions.

**Interface**:
```
HeatmapGenerator:
    Configuration:
        board_radius_mm: 170.0
        grid_resolution: 20x20 (divide board into grid cells)
    
    Methods:
        generate_heatmap(feedback_list, ring_filter) → heatmap_image
            Input: Feedback data, optional ring filter ("single", "double", "triple", or null for all)
            Output: Heatmap image (numpy array)
            
            Algorithm:
                1. Filter feedback by ring type (if specified)
                2. Create 2D grid covering board area
                3. For each grid cell:
                   a. Find feedback entries with positions in cell
                   b. Compute accuracy for that cell
                   c. Assign color based on accuracy
                4. Overlay grid on dartboard background image
                5. Return heatmap image
        
        assign_color(accuracy) → RGB color
            - accuracy > 0.90: green (0, 255, 0)
            - 0.70 ≤ accuracy ≤ 0.90: yellow (255, 255, 0)
            - accuracy < 0.70: red (255, 0, 0)
            - no data: gray (128, 128, 128)
        
        save_heatmap(image, output_path)
            - Save heatmap image to file (PNG format)
```

### 7. DatasetExporter Class

**Purpose**: Export verified feedback data as CSV dataset for machine learning training.

**Interface**:
```
DatasetExporter:
    Methods:
        export_dataset(feedback_list, output_dir) → dataset_paths
            Input: All feedback data, output directory path
            Output: Paths to train/val/test CSV files
            
            Algorithm:
                1. Filter correct detections only
                2. Shuffle dataset randomly
                3. Split into train/val/test (70/15/15)
                4. Export each split to CSV
                5. Generate README with statistics
                6. Return paths to CSV files
        
        filter_correct_detections(feedback_list) → verified_list
            - Keep only entries where detected == actual
            - Return filtered list
        
        split_dataset(dataset, train_ratio, val_ratio, test_ratio) → (train, val, test)
            - Shuffle dataset randomly
            - Split according to ratios
            - Return three subsets
        
        export_csv(dataset, output_path)
            Columns: timestamp, camera_id, image_path, tip_x, tip_y, actual_score, confidence
            - Write header row
            - Write one row per camera detection
            - Save to CSV file
        
        generate_readme(dataset_stats, output_path)
            - Include total samples, per-sector distribution, per-ring distribution
            - Include usage instructions
            - Save to README.md

DatasetStats:
    total_samples: integer
    per_sector_counts: dict
    per_ring_counts: dict
    train_samples: integer
    val_samples: integer
    test_samples: integer
```

## Data Models

### Metadata JSON Format

**Example feedback metadata.json**:
```json
{
  "feedback_id": "20240115_143218_T20",
  "timestamp": "2024-01-15T14:32:18.123456Z",
  "detected_score": {
    "ring": "triple",
    "sector": 20,
    "total": 60
  },
  "actual_score": {
    "ring": "triple",
    "sector": 20,
    "total": 60
  },
  "is_correct": true,
  "user_response": "y",
  "dart_hit_event": {
    "board_coordinates": {"x_mm": 2.3, "y_mm": 98.7},
    "polar_coordinates": {"radius_mm": 98.7, "angle_deg": 88.6},
    "score": {"base": 20, "multiplier": 3, "total": 60, "ring": "triple", "sector": 20},
    "fusion": {"confidence": 0.82, "cameras_used": [0, 1, 2], "num_cameras": 3},
    "detections": [
      {"camera_id": 0, "pixel": {"x": 412.3, "y": 287.5}, "board": {"x": 1.8, "y": 99.2}, "confidence": 0.85},
      {"camera_id": 1, "pixel": {"x": 398.7, "y": 301.2}, "board": {"x": 2.5, "y": 98.5}, "confidence": 0.78},
      {"camera_id": 2, "pixel": {"x": 425.1, "y": 295.8}, "board": {"x": 2.6, "y": 98.4}, "confidence": 0.83}
    ]
  },
  "image_paths": {
    "0": {
      "pre": "cam0_pre.jpg",
      "post": "cam0_post.jpg",
      "annotated": "cam0_annotated.jpg"
    },
    "1": {
      "pre": "cam1_pre.jpg",
      "post": "cam1_post.jpg",
      "annotated": "cam1_annotated.jpg"
    },
    "2": {
      "pre": "cam2_pre.jpg",
      "post": "cam2_post.jpg",
      "annotated": "cam2_annotated.jpg"
    }
  }
}
```

### Analysis Report Format

**Example analysis_report.txt**:
```
ARU-DART Feedback Analysis Report
Generated: 2024-01-15 15:30:00
=====================================

Overall Statistics
------------------
Total Throws: 150
Correct Detections: 132
Incorrect Detections: 18
Overall Accuracy: 88.0%

Per-Sector Accuracy
-------------------
Sector 20: 95.0% (19/20)
Sector 1: 85.0% (17/20)
Sector 18: 90.0% (18/20)
...

Per-Ring Accuracy
-----------------
Singles: 92.0% (46/50)
Doubles: 85.0% (34/40)
Triples: 83.3% (25/30)
Bulls: 90.0% (18/20)
Single Bulls: 100.0% (10/10)

Top 5 Failure Modes
-------------------
1. T20 detected as S20: 5 occurrences
2. D16 detected as S16: 3 occurrences
3. T19 detected as T3: 2 occurrences
4. S5 detected as S20: 2 occurrences
5. D20 detected as T20: 1 occurrence

Confusion Matrix
----------------
(See confusion_matrix.csv for full matrix)
```

### Dataset CSV Format

**Example train.csv**:
```csv
timestamp,camera_id,image_path,tip_x,tip_y,actual_score,confidence
2024-01-15T14:32:18.123456Z,0,data/feedback/correct/20240115_143218_T20/cam0_annotated.jpg,412.3,287.5,T20,0.85
2024-01-15T14:32:18.123456Z,1,data/feedback/correct/20240115_143218_T20/cam1_annotated.jpg,398.7,301.2,T20,0.78
2024-01-15T14:32:18.123456Z,2,data/feedback/correct/20240115_143218_T20/cam2_annotated.jpg,425.1,295.8,T20,0.83
...
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After analyzing all acceptance criteria, I identified the following testable properties and eliminated redundancy:

**Redundancy Analysis**:
- AC-7.5.3.1, AC-7.5.3.2, AC-7.5.3.3 (accuracy calculations) → Combined into Property 2 (accuracy computation correctness)
- AC-7.5.2.2, AC-7.5.2.4 (data completeness and filename format) → Combined into Property 3 (feedback entry completeness)
- AC-7.5.5.1, AC-7.5.5.2 (CSV structure and filtering) → Combined into Property 6 (dataset export correctness)

**Properties to Test**:
1. Score parsing correctness (all valid formats)
2. Accuracy computation correctness
3. Feedback entry completeness
4. Filename uniqueness (append-only storage)
5. Confusion matrix correctness
6. Dataset export correctness
7. Dataset split ratios
8. Color mapping for heatmaps

### Property 1: Score Parsing Correctness

*For any* valid score string in the supported formats (singles, doubles, triples, bulls, miss), the score parser should correctly extract the ring type, sector number, and total score.

**Validates: Requirements Score Input Format, AC-7.5.1.4**

**Test Strategy**: Generate random score strings in all supported formats:
- Singles: "20", "S20", "1", "single 20" → (ring="single", sector=20, total=20)
- Doubles: "D20", "double 20" → (ring="double", sector=20, total=40)
- Triples: "T20", "triple 20" → (ring="triple", sector=20, total=60)
- Bulls: "50", "DB", "bull" → (ring="bull", sector=null, total=50)
- Single Bulls: "25", "SB" → (ring="single_bull", sector=null, total=25)
- Miss: "0", "miss" → (ring="miss", sector=null, total=0)

Verify parser extracts correct ring, sector, and total for each format.

### Property 2: Accuracy Computation Correctness

*For any* set of feedback entries, the computed accuracy should equal the count of correct detections divided by the total count, and per-sector/per-ring accuracies should be computed correctly by grouping.

**Validates: Requirements AC-7.5.3.1, AC-7.5.3.2, AC-7.5.3.3**

**Test Strategy**: Generate random feedback datasets with known correct/incorrect counts. Verify:
- Overall accuracy = correct_count / total_count
- Per-sector accuracy computed by grouping by actual sector
- Per-ring accuracy computed by grouping by actual ring
- Edge cases: empty dataset, all correct, all incorrect, single entry

### Property 3: Feedback Entry Completeness

*For any* saved feedback entry, the metadata JSON should contain all required fields (feedback_id, timestamp, detected_score, actual_score, is_correct, dart_hit_event, image_paths), and the filename should include timestamp and detected score.

**Validates: Requirements AC-7.5.2.2, AC-7.5.2.4**

**Test Strategy**: Generate random feedback entries, save them, reload metadata JSON. Verify:
- All required fields present and non-null
- Timestamp in ISO 8601 format
- Filename format: {timestamp}_{detected_score}/
- Image paths reference existing files (relative paths)

### Property 4: Filename Uniqueness (Append-Only Storage)

*For any* two feedback entries saved at different times, they should have unique feedback IDs and directory names, ensuring no overwrites occur.

**Validates: Requirements AC-7.5.2.5**

**Test Strategy**: Generate multiple feedback entries with same detected score but different timestamps. Verify:
- Each entry gets unique feedback_id
- Each entry saved to unique directory
- No directory overwrites occur
- Timestamp precision sufficient for uniqueness (microseconds)

### Property 5: Confusion Matrix Correctness

*For any* set of feedback entries, the confusion matrix should correctly count the occurrences of each (detected_score, actual_score) pair, with row sums and column sums matching the total counts.

**Validates: Requirements AC-7.5.3.4**

**Test Strategy**: Generate random feedback datasets with known (detected, actual) pairs. Verify:
- Matrix[detected][actual] = count of that pair
- Sum of row = total detections of that score
- Sum of column = total actual occurrences of that score
- Matrix diagonal = correct detections

### Property 6: Dataset Export Correctness

*For any* feedback dataset, the exported CSV should contain only correct detections, have the specified columns in order, and include one row per camera detection with correct data.

**Validates: Requirements AC-7.5.5.1, AC-7.5.5.2**

**Test Strategy**: Generate random feedback datasets with correct and incorrect entries. Export to CSV. Verify:
- Only correct detections included (detected == actual)
- CSV has correct columns: timestamp, camera_id, image_path, tip_x, tip_y, actual_score, confidence
- One row per camera detection (3 rows per throw for 3-camera detection)
- Data matches source feedback entries

### Property 7: Dataset Split Ratios

*For any* dataset split with specified ratios (e.g., 70/15/15), the actual split sizes should be within ±1 sample of the expected sizes due to rounding.

**Validates: Requirements AC-7.5.5.4**

**Test Strategy**: Generate random datasets of various sizes. Split with 70/15/15 ratios. Verify:
- train_size ≈ 0.70 × total_size (within ±1)
- val_size ≈ 0.15 × total_size (within ±1)
- test_size ≈ 0.15 × total_size (within ±1)
- train_size + val_size + test_size = total_size (no samples lost)

### Property 8: Color Mapping for Heatmaps

*For any* accuracy value, the assigned color should match the specified thresholds: green for >90%, yellow for 70-90%, red for <70%.

**Validates: Requirements AC-7.5.4.2**

**Test Strategy**: Generate random accuracy values in range [0, 1]. Verify color assignment:
- accuracy > 0.90 → green (0, 255, 0)
- 0.70 ≤ accuracy ≤ 0.90 → yellow (255, 255, 0)
- accuracy < 0.70 → red (255, 0, 0)
- Boundary cases: exactly 0.70, exactly 0.90

## Error Handling

### Invalid Score Input

**Scenario**: User enters unparseable score string (e.g., "xyz", "T25", "D0")

**Handling**:
```
parse_score(input_string):
    try:
        parsed = attempt_parsing(input_string)
        if parsed is null:
            log_warning("Invalid score format: " + input_string)
            return null
    except:
        log_error("Parse error: " + input_string)
        return null
```

**Behavior**:
- Return null from parse_score()
- FeedbackPrompt re-prompts user with examples
- After 3 failed attempts, show detailed format help
- Allow user to skip with 's' key

### Missing Image Files

**Scenario**: Image files not found when saving feedback (deleted or moved)

**Handling**:
```
save_feedback(feedback_data):
    for each image_path in feedback_data.image_paths:
        if not file_exists(image_path):
            log_error("Image not found: " + image_path)
            # Continue with available images
    
    # Save metadata even if some images missing
    save_metadata_json(feedback_data)
```

**Behavior**:
- Log error for missing images
- Save metadata with available image paths
- Mark missing images as null in metadata
- Feedback entry still created (partial data better than none)

### Empty Feedback Dataset

**Scenario**: Analysis or export attempted with no feedback data

**Handling**:
```
analyze(feedback_list):
    if count(feedback_list) == 0:
        log_warning("No feedback data to analyze")
        return AnalysisResults(empty=true)

export_dataset(feedback_list):
    verified = filter_correct_detections(feedback_list)
    if count(verified) == 0:
        log_warning("No correct detections to export")
        return null
```

**Behavior**:
- Return empty results or null
- Log warning message
- Do not create output files
- Inform user that more feedback data needed

### Disk Space Exhaustion

**Scenario**: Insufficient disk space when saving feedback images

**Handling**:
```
save_feedback(feedback_data):
    try:
        create_feedback_directory(feedback_id)
        copy_images_to_directory(image_paths, feedback_dir)
        save_metadata_json(feedback_data, feedback_dir)
    except DiskFullError:
        log_error("Disk space exhausted, cannot save feedback")
        cleanup_partial_directory(feedback_dir)
        return null
```

**Behavior**:
- Catch disk full errors
- Clean up partial directories
- Log error with disk space information
- Return null (feedback not saved)
- Suggest user free up space or change feedback directory

### Concurrent Feedback Collection

**Scenario**: Multiple feedback entries saved simultaneously (future multi-user scenario)

**Design Approach**:
- Use timestamp with microsecond precision for unique IDs
- Atomic directory creation (OS-level)
- No shared mutable state in FeedbackStorage

**Behavior**:
- Each feedback entry gets unique ID (timestamp-based)
- Directory creation is atomic (no race conditions)
- Safe for concurrent use without explicit locking

## Testing Strategy

### Dual Testing Approach

The feedback system requires both unit tests and property-based tests for comprehensive validation:

**Unit Tests**: Verify specific examples, edge cases, and error conditions
- Specific score parsing examples (T20, D16, bull, miss)
- Feedback workflow (prompt → parse → save)
- Directory organization (correct/ vs incorrect/)
- Analysis report generation
- Heatmap file creation
- CSV export format
- Error handling (invalid input, missing files, empty dataset)

**Property Tests**: Verify universal properties across all inputs
- Score parsing for all valid formats
- Accuracy calculations for any feedback dataset
- Feedback entry completeness
- Filename uniqueness
- Confusion matrix correctness
- Dataset export filtering and structure
- Dataset split ratios
- Color mapping for heatmaps

Both approaches are complementary and necessary for ensuring correctness.

### Property-Based Testing Configuration

**Library**: Use `hypothesis` for Python property-based testing

**Configuration**:
- Minimum 100 iterations per property test (due to randomization)
- Each property test references its design document property
- Tag format: `# Feature: step-7.5-feedback-system, Property N: [property text]`

**Example Property Test**:
```python
from hypothesis import given, strategies as st

@given(
    ring=st.sampled_from(["single", "double", "triple"]),
    sector=st.integers(min_value=1, max_value=20)
)
def test_score_parsing_correctness(ring, sector):
    """
    Feature: step-7.5-feedback-system, Property 1: Score Parsing Correctness
    
    For any valid score string, the parser should correctly extract
    ring type, sector number, and total score.
    """
    parser = ScoreParser()
    
    # Generate score string in various formats
    formats = [
        f"{ring[0].upper()}{sector}",  # T20, D16, S5
        f"{ring} {sector}",             # triple 20, double 16
    ]
    
    for score_string in formats:
        parsed = parser.parse_score(score_string)
        
        assert parsed is not None
        assert parsed.ring == ring
        assert parsed.sector == sector
        
        # Verify total score calculation
        multiplier = {"single": 1, "double": 2, "triple": 3}[ring]
        expected_total = sector * multiplier
        assert parsed.total == expected_total
```

### Unit Test Coverage

**Test Files**:
```
tests/
├── test_feedback_collector.py      # FeedbackCollector class tests
├── test_score_parser.py            # ScoreParser class tests
├── test_feedback_storage.py        # FeedbackStorage class tests
├── test_feedback_prompt.py         # FeedbackPrompt class tests (mocked input)
├── test_accuracy_analyzer.py       # AccuracyAnalyzer class tests
├── test_heatmap_generator.py       # HeatmapGenerator class tests
├── test_dataset_exporter.py        # DatasetExporter class tests
└── test_feedback_integration.py    # End-to-end integration tests
```

**Key Test Scenarios**:

1. **ScoreParser Tests**:
   - Parse "T20" → (triple, 20, 60)
   - Parse "D16" → (double, 16, 32)
   - Parse "25" → (single_bull, null, 25)
   - Parse "bull" → (bull, null, 50)
   - Parse "miss" → (miss, null, 0)
   - Parse invalid input → null
   - Case insensitivity ("t20" == "T20")

2. **FeedbackStorage Tests**:
   - Save feedback creates directory
   - Metadata JSON contains all fields
   - Images copied to feedback directory
   - Correct/incorrect organization
   - Unique feedback IDs
   - Load all feedback returns correct count

3. **AccuracyAnalyzer Tests**:
   - Overall accuracy: 8/10 correct → 80%
   - Per-sector accuracy grouping
   - Per-ring accuracy grouping
   - Confusion matrix dimensions
   - Top N failure modes sorted by frequency
   - Empty dataset handling

4. **HeatmapGenerator Tests**:
   - Heatmap image created
   - Color assignment (green/yellow/red)
   - Ring filtering (singles only, doubles only)
   - Grid resolution
   - File saved to correct path

5. **DatasetExporter Tests**:
   - Filter correct detections only
   - CSV has correct columns
   - One row per camera detection
   - Dataset split ratios (70/15/15)
   - README generation

6. **Integration Tests**:
   - Full feedback workflow (detect → prompt → save)
   - Analysis pipeline (load → analyze → report)
   - Export pipeline (load → filter → split → export)

### Test Data

**Synthetic Test Data**:
- Generated feedback entries with known scores
- Known correct/incorrect classifications
- Various score types (singles, doubles, triples, bulls, miss)
- Edge cases (empty dataset, single entry, all correct, all incorrect)

**Test Data Location**:
```
tests/data/
├── feedback/
│   ├── sample_correct.json      # Example correct detection
│   ├── sample_incorrect.json    # Example incorrect detection
│   └── sample_dataset.json      # Small dataset for testing
└── images/
    ├── cam0_test.jpg            # Test images
    ├── cam1_test.jpg
    └── cam2_test.jpg
```

## Performance Considerations

### Feedback Collection Latency

**Requirement**: Complete feedback collection in <5 seconds per throw

**Measured Performance** (estimated):
- Display score: ~0.01s (print to console)
- User input wait: 1-5s (human response time)
- Score parsing: ~0.001s (string operations)
- Save metadata JSON: ~0.01s (JSON serialization)
- Copy images: ~0.1-0.5s (3 cameras × 3 images = 9 files, ~100KB each)
- **Total: ~1-6s** ✓ (within 5s target)

**Bottleneck**: User response time (human factor, not optimizable)

### Storage Requirements

**Per-Throw Storage**:
- Metadata JSON: ~2KB
- Images (9 files): ~900KB (100KB per image × 9)
- **Total per throw: ~1MB**

**Storage Scaling**:
- 100 throws: ~100MB
- 1000 throws: ~1GB
- 10,000 throws: ~10GB

**Optimization**: Compress images (JPEG quality 85) to reduce storage by ~50%

### Analysis Performance

**Requirement**: Complete analysis in <10 seconds for 1000 throws

**Measured Performance** (estimated):
- Load feedback data: ~0.5-1s (1000 JSON files)
- Compute accuracy metrics: ~0.01s (simple arithmetic)
- Build confusion matrix: ~0.05s (dictionary operations)
- Identify failure modes: ~0.1s (sorting)
- Export report: ~0.01s (text formatting)
- **Total: ~0.7-1.2s** ✓ (well under 10s target)

**Bottleneck**: None - all operations are fast

### Heatmap Generation Performance

**Measured Performance** (estimated):
- Load feedback data: ~0.5-1s
- Compute grid accuracies: ~0.1-0.5s (depends on grid resolution)
- Render heatmap: ~0.5-2s (matplotlib/PIL operations)
- Save image: ~0.1s
- **Total: ~1-4s per heatmap** ✓

**Optimization**: Cache grid computations if generating multiple heatmaps

## Integration with Existing System

### Command-Line Interface

Add `--feedback-mode` flag to main.py:

```
main():
    parser = ArgumentParser()
    parser.add_argument('--feedback-mode', action='store_true',
                       help='Enable feedback collection mode')
    args = parser.parse_args()
    
    # Initialize feedback collector if enabled
    feedback_collector = None
    if args.feedback_mode:
        feedback_collector = FeedbackCollector(config)
        log_info("Feedback mode enabled")
```

### Main Loop Integration

Integrate feedback collection after score derivation:

```
main():
    # ... initialization ...
    
    while true:
        # ... existing motion detection and dart detection ...
        
        if motion_state == "dart_detected":
            # ... existing detection and fusion ...
            dart_hit_event = score_calculator.process_detections(detections)
            
            if dart_hit_event not null:
                # Display detected score
                log_info("Dart scored: " + dart_hit_event.score.total)
                
                # NEW: Collect feedback in feedback mode
                if feedback_collector not null:
                    feedback_id = feedback_collector.collect_feedback(
                        dart_hit_event, 
                        image_paths
                    )
                    
                    if feedback_id not null:
                        log_info("Feedback saved: " + feedback_id)
                    else:
                        log_info("Feedback skipped")
                
                # Continue with game logic...
            
            motion_state = "idle"
```

### Analysis Scripts

**Analyze Feedback**:
```bash
python scripts/analyze_feedback.py
```

**Generate Heatmaps**:
```bash
python scripts/generate_heatmaps.py
```

**Export Dataset**:
```bash
python scripts/export_dataset.py --output data/feedback/verified_dataset
```

### Logging Output Example

```
2024-01-15 14:32:18 INFO [main] Feedback mode enabled
2024-01-15 14:32:18 INFO [main] Dart scored: 60 (20 × 3)
2024-01-15 14:32:18 INFO [feedback_collector] Detected: T20 (60 points), Confidence: 0.82
2024-01-15 14:32:20 INFO [feedback_collector] User confirmed: correct
2024-01-15 14:32:20 INFO [feedback_storage] Saving feedback: 20240115_143218_T20
2024-01-15 14:32:20 INFO [feedback_storage] Feedback saved to: data/feedback/correct/20240115_143218_T20/
2024-01-15 14:32:20 INFO [main] Feedback saved: 20240115_143218_T20
```

## Summary

This design document specifies a complete human feedback and learning system that:

1. **Collects user feedback** non-intrusively during gameplay (<5s per throw)
2. **Parses score input** in natural language formats (T20, D16, bull, miss, etc.)
3. **Stores complete context** (metadata JSON + images from all cameras)
4. **Organizes feedback** by correctness (correct/ and incorrect/ subdirectories)
5. **Analyzes accuracy** (overall, per-sector, per-ring, confusion matrix, failure modes)
6. **Generates heatmaps** showing spatial accuracy patterns across the board
7. **Exports verified datasets** for machine learning training (train/val/test splits)
8. **Handles errors gracefully** with appropriate fallbacks and user guidance

The system enables continuous improvement by building a verified dataset of ground truth scores, identifying systematic errors, and providing data for future machine learning enhancements. All operations are performant and non-intrusive to gameplay.
