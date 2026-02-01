# Implementation Plan: Step 7.5 Human Feedback & Learning System

## Overview

Implement a feedback collection system that allows users to confirm or correct detected dart scores during gameplay. The system stores complete detection context (images, coordinates, metadata) and provides analysis tools to compute accuracy metrics, generate heatmaps, and export verified datasets for machine learning training.

## Tasks

- [ ] 1. Implement score parsing and validation
  - [ ] 1.1 Create ScoreParser class with parse_score() method
    - Support all score formats: singles (20, S20), doubles (D20), triples (T20), bulls (50, DB, bull, 25, SB), miss (0, miss)
    - Return ParsedScore with ring, sector, and total
    - Handle case-insensitive input and whitespace
    - _Requirements: Score Input Format, AC-7.5.1.4_
  
  - [ ] 1.2 Write property test for score parsing
    - **Property 1: Score Parsing Correctness**
    - **Validates: Requirements Score Input Format, AC-7.5.1.4**
  
  - [ ] 1.3 Write unit tests for score parser
    - Test specific examples: T20, D16, 25, bull, miss
    - Test invalid inputs return null
    - Test case insensitivity
    - _Requirements: Score Input Format_

- [ ] 2. Implement feedback collection workflow
  - [ ] 2.1 Create FeedbackPrompt class for user interaction
    - Implement prompt_confirmation() with timeout
    - Implement prompt_score_input() with validation
    - Handle user responses: 'y', 'n', 'c', 's'
    - _Requirements: AC-7.5.1.2, AC-7.5.1.3, AC-7.5.1.4, AC-7.5.1.6_
  
  - [ ] 2.2 Create FeedbackCollector class
    - Implement collect_feedback() orchestration method
    - Integrate FeedbackPrompt, ScoreParser, and FeedbackStorage
    - Display detected score with confidence
    - Determine correctness (detected == actual)
    - _Requirements: AC-7.5.1.1, AC-7.5.1.2, AC-7.5.1.5_
  
  - [ ] 2.3 Write unit tests for feedback workflow
    - Test confirmation flow ('y' response)
    - Test correction flow ('n' response)
    - Test skip flow ('s' response)
    - Test timeout handling
    - _Requirements: AC-7.5.1.3, AC-7.5.1.6_

- [ ] 3. Implement feedback data storage
  - [ ] 3.1 Create FeedbackStorage class
    - Implement save_feedback() with directory creation
    - Generate unique feedback IDs (timestamp-based)
    - Organize into correct/ and incorrect/ subdirectories
    - Copy images to feedback directory
    - Save metadata JSON with complete context
    - _Requirements: AC-7.5.2.1, AC-7.5.2.2, AC-7.5.2.3, AC-7.5.2.4, AC-7.5.2.5_
  
  - [ ] 3.2 Implement load_all_feedback() method
    - Scan correct/ and incorrect/ directories
    - Load all metadata.json files
    - Return list of FeedbackData objects
    - _Requirements: AC-7.5.2.1, AC-7.5.2.3_
  
  - [ ] 3.3 Write property test for feedback entry completeness
    - **Property 3: Feedback Entry Completeness**
    - **Validates: Requirements AC-7.5.2.2, AC-7.5.2.4**
  
  - [ ] 3.4 Write property test for filename uniqueness
    - **Property 4: Filename Uniqueness**
    - **Validates: Requirements AC-7.5.2.5**
  
  - [ ] 3.5 Write unit tests for feedback storage
    - Test directory creation
    - Test metadata JSON structure
    - Test image copying
    - Test correct/incorrect organization
    - Test error handling (missing images, disk full)
    - _Requirements: AC-7.5.2.1, AC-7.5.2.2, AC-7.5.2.3_

- [ ] 4. Checkpoint - Test feedback collection end-to-end
  - Ensure feedback collection workflow works with real DartHitEvent data
  - Verify feedback stored correctly with all images and metadata
  - Ask the user if questions arise

- [ ] 5. Implement accuracy analysis
  - [ ] 5.1 Create AccuracyAnalyzer class
    - Implement compute_overall_accuracy()
    - Implement compute_per_sector_accuracy()
    - Implement compute_per_ring_accuracy()
    - Implement generate_confusion_matrix()
    - Implement identify_failure_modes(top_n)
    - _Requirements: AC-7.5.3.1, AC-7.5.3.2, AC-7.5.3.3, AC-7.5.3.4, AC-7.5.3.5_
  
  - [ ] 5.2 Implement export_report() method
    - Format analysis results as text report
    - Include all metrics and failure modes
    - Save to data/feedback/analysis_report.txt
    - _Requirements: AC-7.5.3.6_
  
  - [ ] 5.3 Write property test for accuracy computation
    - **Property 2: Accuracy Computation Correctness**
    - **Validates: Requirements AC-7.5.3.1, AC-7.5.3.2, AC-7.5.3.3**
  
  - [ ] 5.4 Write property test for confusion matrix
    - **Property 5: Confusion Matrix Correctness**
    - **Validates: Requirements AC-7.5.3.4**
  
  - [ ] 5.5 Write unit tests for accuracy analyzer
    - Test overall accuracy calculation
    - Test per-sector grouping and accuracy
    - Test per-ring grouping and accuracy
    - Test failure mode identification
    - Test empty dataset handling
    - _Requirements: AC-7.5.3.1, AC-7.5.3.2, AC-7.5.3.3, AC-7.5.3.5_

- [ ] 6. Implement heatmap generation
  - [ ] 6.1 Create HeatmapGenerator class
    - Implement generate_heatmap() with grid-based accuracy computation
    - Implement assign_color() with threshold-based color mapping
    - Support ring filtering (singles, doubles, triples, or all)
    - Overlay on dartboard background image
    - _Requirements: AC-7.5.4.1, AC-7.5.4.2, AC-7.5.4.3, AC-7.5.4.4_
  
  - [ ] 6.2 Implement save_heatmap() method
    - Save heatmap images to data/feedback/
    - Generate separate heatmaps for each ring type
    - _Requirements: AC-7.5.4.4, AC-7.5.4.5_
  
  - [ ] 6.3 Write property test for color mapping
    - **Property 8: Color Mapping for Heatmaps**
    - **Validates: Requirements AC-7.5.4.2**
  
  - [ ] 6.4 Write unit tests for heatmap generator
    - Test heatmap image creation
    - Test color assignment (green/yellow/red)
    - Test ring filtering
    - Test file output
    - _Requirements: AC-7.5.4.1, AC-7.5.4.5_

- [ ] 7. Implement dataset export
  - [ ] 7.1 Create DatasetExporter class
    - Implement filter_correct_detections()
    - Implement split_dataset() with configurable ratios
    - Implement export_csv() with correct column structure
    - Implement generate_readme() with dataset statistics
    - _Requirements: AC-7.5.5.1, AC-7.5.5.2, AC-7.5.5.4, AC-7.5.5.5_
  
  - [ ] 7.2 Write property test for dataset export
    - **Property 6: Dataset Export Correctness**
    - **Validates: Requirements AC-7.5.5.1, AC-7.5.5.2**
  
  - [ ] 7.3 Write property test for dataset split ratios
    - **Property 7: Dataset Split Ratios**
    - **Validates: Requirements AC-7.5.5.4**
  
  - [ ] 7.4 Write unit tests for dataset exporter
    - Test correct detection filtering
    - Test CSV structure and columns
    - Test dataset splitting
    - Test README generation
    - _Requirements: AC-7.5.5.1, AC-7.5.5.2, AC-7.5.5.4, AC-7.5.5.5_

- [ ] 8. Create analysis and export scripts
  - [ ] 8.1 Create scripts/analyze_feedback.py CLI script
    - Load all feedback data
    - Run AccuracyAnalyzer
    - Export analysis report
    - _Requirements: AC-7.5.3.6_
  
  - [ ] 8.2 Create scripts/generate_heatmaps.py CLI script
    - Load all feedback data
    - Generate heatmaps (overall + per-ring)
    - Save heatmap images
    - _Requirements: AC-7.5.4.5_
  
  - [ ] 8.3 Create scripts/export_dataset.py CLI script
    - Load all feedback data
    - Filter and split dataset
    - Export CSV files and README
    - _Requirements: AC-7.5.5.1, AC-7.5.5.5_

- [ ] 9. Integrate with main detection loop
  - [ ] 9.1 Add --feedback-mode command-line flag to main.py
    - Parse argument and initialize FeedbackCollector
    - _Requirements: AC-7.5.1.1_
  
  - [ ] 9.2 Integrate feedback collection after score derivation
    - Call feedback_collector.collect_feedback() after DartHitEvent creation
    - Pass dart_hit_event and image_paths
    - Log feedback results
    - _Requirements: AC-7.5.1.1, AC-7.5.1.2_
  
  - [ ] 9.3 Write integration tests
    - Test full feedback workflow with mocked user input
    - Test feedback mode flag activation
    - Test feedback storage integration
    - _Requirements: AC-7.5.1.1, AC-7.5.1.5_

- [ ] 10. Final checkpoint - End-to-end validation
  - Test feedback collection in real gameplay scenario
  - Run analysis script on collected feedback
  - Generate heatmaps and verify output
  - Export dataset and verify CSV structure
  - Ensure all tests pass
  - Ask the user if questions arise

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- Use `hypothesis` library for property-based testing (minimum 100 iterations per test)
- All feedback data stored in `data/feedback/` directory
- Analysis scripts can be run independently after feedback collection
