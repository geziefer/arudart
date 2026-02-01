# Step 10: POC Validation - Design Document

## Overview

This design document specifies the architecture for validating the complete ARU-DART system through structured testing, accuracy analysis, failure mode identification, and performance measurement. This is the final step in the POC phase, providing comprehensive validation data to prove system viability and identify areas for improvement.

The validation system consists of three main components: (1) validation session tools for running structured test sessions with ground truth logging, (2) analysis scripts for computing accuracy metrics and identifying failure patterns, and (3) report generation for creating comprehensive validation documentation.

**Key Design Principles**:
- Structured test sessions with manual ground truth logging
- Comprehensive accuracy metrics (exact match, sector, ring, per-region)
- Systematic failure mode analysis with annotated images
- Performance profiling (latency, CPU, memory)
- Actionable recommendations for Phase 2
- Reproducible validation methodology

## Architecture

### Module Structure

```
tools/validation/
├── __init__.py
├── validation_session.py       # ValidationSession class
├── ground_truth_logger.py      # GroundTruthLogger class
├── accuracy_analyzer.py        # AccuracyAnalyzer class
├── failure_analyzer.py         # FailureAnalyzer class
├── performance_profiler.py     # PerformanceProfiler class
└── report_generator.py         # ReportGenerator class

data/validation/
├── session_YYYYMMDD_HHMMSS/
│   ├── ground_truth.jsonl      # Manual ground truth log
│   ├── system_events.jsonl     # System-generated events
│   ├── performance.jsonl       # Performance metrics
│   └── images/                 # Annotated images for failures
└── reports/
    └── validation_report_YYYYMMDD.md

config.toml additions:
[validation]
session_duration_minutes = 60
target_throw_count = 100
performance_sample_interval_ms = 100


### Class Hierarchy

```
ValidationSession (orchestrator)
├── Uses GroundTruthLogger for manual logging
├── Uses PerformanceProfiler for metrics collection
├── Coordinates with main system for event capture
└── Manages session lifecycle

GroundTruthLogger
├── log_throw(intended_target, actual_result) → entry_id
├── get_all_entries() → list of ground truth entries
└── export_to_jsonl(path)

AccuracyAnalyzer
├── compute_exact_match_rate() → float
├── compute_sector_accuracy() → float
├── compute_ring_accuracy() → float
├── compute_per_region_accuracy() → dict
└── generate_confusion_matrix() → matrix

FailureAnalyzer
├── identify_failure_modes() → list of failure patterns
├── categorize_failures() → dict mapping category → failures
├── analyze_systematic_errors() → list of systematic patterns
└── generate_recommendations() → list of recommendations

PerformanceProfiler
├── start_profiling()
├── record_event_timing(event_type, duration_ms)
├── record_system_metrics(cpu_percent, memory_mb)
├── stop_profiling()
└── export_metrics() → dict

ReportGenerator
├── generate_validation_report(analysis_results) → markdown
├── create_accuracy_section() → markdown
├── create_failure_section() → markdown
├── create_performance_section() → markdown
└── create_recommendations_section() → markdown
```


### Data Flow

```
Validation Session Start
    ↓
[ValidationSession.start()]
    ↓
Initialize components:
    - GroundTruthLogger
    - PerformanceProfiler
    - System event capture
    ↓
Main Loop (for each throw):
    ↓
    1. User throws dart
    ↓
    2. System detects and scores
       [System emits DartHitEvent]
    ↓
    3. User logs ground truth
       [GroundTruthLogger.log_throw(intended, actual)]
    ↓
    4. Performance metrics recorded
       [PerformanceProfiler.record_event_timing()]
    ↓
    5. Continue until session complete
    ↓
[ValidationSession.end()]
    ↓
Export session data:
    - ground_truth.jsonl
    - system_events.jsonl
    - performance.jsonl
    ↓
Analysis Phase:
    ↓
[AccuracyAnalyzer.analyze(ground_truth, system_events)]
    ↓
Compute metrics:
    - Exact match rate
    - Sector accuracy
    - Ring accuracy
    - Per-region accuracy
    ↓
[FailureAnalyzer.analyze(mismatches, images)]
    ↓
Identify patterns:
    - Top 5 failure modes
    - Systematic vs random errors
    - Root causes
    ↓
[PerformanceProfiler.analyze(metrics)]
    ↓
Compute statistics:
    - Detection latency (p50, p95, p99)
    - Per-stage timing
    - CPU/memory usage
    ↓
[ReportGenerator.generate(all_results)]
    ↓
Create validation report:
    - Executive summary
    - Accuracy metrics
    - Failure analysis
    - Performance metrics
    - Recommendations
    ↓
Output: validation_report_YYYYMMDD.md
```


### Integration with Existing System

The validation system runs alongside the main system, capturing events and logging ground truth:

```
main():
    # Check if validation mode enabled
    if args.validation_mode:
        validation_session = ValidationSession(config)
        validation_session.start()
    
    # Main loop (existing)
    while true:
        # ... existing motion detection and scoring ...
        
        events = state_machine.process(motion_detected, motion_data, frames)
        
        for event in events:
            # Existing event handling
            handle_event(event)
            
            # NEW: Log to validation session
            if validation_session:
                validation_session.record_system_event(event)
        
        # NEW: Check for ground truth input
        if validation_session and validation_session.awaiting_ground_truth():
            ground_truth = validation_session.prompt_for_ground_truth()
            validation_session.log_ground_truth(ground_truth)
    
    # Session end
    if validation_session:
        validation_session.end()
        print("Validation session complete. Run analysis script to generate report.")
```

Separate analysis script:

```
analyze_validation_session.py:
    1. Load session data (ground_truth.jsonl, system_events.jsonl, performance.jsonl)
    2. Run AccuracyAnalyzer
    3. Run FailureAnalyzer
    4. Run PerformanceProfiler analysis
    5. Generate report with ReportGenerator
    6. Save report to data/validation/reports/
```


## Components and Interfaces

### 1. ValidationSession Class

**Purpose**: Orchestrate validation session lifecycle, coordinate ground truth logging, and capture system events.

**Interface**:
```
ValidationSession:
    State:
        session_id: string (timestamp-based)
        session_dir: path (data/validation/session_YYYYMMDD_HHMMSS/)
        start_time: timestamp
        throw_count: integer
        awaiting_ground_truth: boolean
        last_system_event: DartHitEvent or null
    
    Components:
        ground_truth_logger: GroundTruthLogger instance
        performance_profiler: PerformanceProfiler instance
        system_event_log: file handle for system_events.jsonl
    
    Methods:
        start()
            Algorithm:
                1. Create session directory
                2. Initialize ground_truth_logger
                3. Initialize performance_profiler
                4. Open system_events.jsonl for writing
                5. Log session start metadata
        
        record_system_event(event)
            Input: DartHitEvent, DartRemovedEvent, etc.
            Algorithm:
                1. Write event to system_events.jsonl
                2. If DartHitEvent:
                   a. Set awaiting_ground_truth = true
                   b. Store last_system_event = event
                3. Record event timing to performance_profiler
        
        prompt_for_ground_truth() → ground_truth_entry
            Algorithm:
                1. Display last_system_event score to user
                2. Prompt user for intended target
                3. Prompt user for actual result (if different)
                4. Return ground_truth_entry
        
        log_ground_truth(entry)
            Algorithm:
                1. Add system_event_id to entry
                2. Log to ground_truth_logger
                3. Set awaiting_ground_truth = false
        
        end()
            Algorithm:
                1. Stop performance_profiler
                2. Export all logs
                3. Close file handles
                4. Log session summary (throw count, duration)
        
        is_awaiting_ground_truth() → boolean
```


### 2. GroundTruthLogger Class

**Purpose**: Capture manual ground truth data during validation sessions with simple CLI prompts.

**Interface**:
```
GroundTruthLogger:
    State:
        entries: list of ground truth entries
        output_file: path to ground_truth.jsonl
    
    Methods:
        log_throw(intended_target, actual_result, system_event_id) → entry_id
            Input: 
                - intended_target: string (e.g., "T20", "D16", "Bull")
                - actual_result: string (e.g., "T20", "S5", "Miss")
                - system_event_id: string (links to system event)
            Output: Unique entry ID
            
            Algorithm:
                1. Create entry with timestamp
                2. Parse targets into structured format
                3. Assign unique entry_id
                4. Append to entries list
                5. Write to JSONL file
                6. Return entry_id
        
        get_all_entries() → list
            Return all logged entries
        
        export_to_jsonl(path)
            Write all entries to JSONL file (one JSON object per line)
```

**Ground Truth Entry Format**:
```
{
    "entry_id": "gt_001",
    "timestamp": "2024-01-15T14:32:18.123456Z",
    "system_event_id": "evt_20240115_143218_001",
    "intended_target": "T20",
    "actual_result": "T20",
    "match": true,
    "intended_parsed": {"ring": "triple", "sector": 20, "score": 60},
    "actual_parsed": {"ring": "triple", "sector": 20, "score": 60}
}
```


### 3. AccuracyAnalyzer Class

**Purpose**: Compute accuracy metrics by comparing system events against ground truth.

**Interface**:
```
AccuracyAnalyzer:
    Methods:
        analyze(ground_truth_entries, system_events) → analysis_results
            Input: Ground truth log and system event log
            Output: Dictionary with all accuracy metrics
            
            Algorithm:
                1. Match ground truth entries to system events by ID
                2. Compute exact match rate
                3. Compute sector accuracy
                4. Compute ring accuracy
                5. Compute per-region accuracy
                6. Generate confusion matrix
                7. Return all metrics
        
        compute_exact_match_rate(matches) → float
            Count where system_score == ground_truth_score
            Return percentage
        
        compute_sector_accuracy(matches) → float
            Count where system_sector == ground_truth_sector (any ring)
            Return percentage
        
        compute_ring_accuracy(matches) → float
            Count where system_ring == ground_truth_ring (any sector)
            Return percentage
        
        compute_per_region_accuracy(matches) → dict
            Group by region (singles, doubles, triples, bulls)
            Compute accuracy for each region
            Return dict: {"singles": 0.85, "doubles": 0.72, ...}
        
        generate_confusion_matrix(matches) → matrix
            Create matrix showing predicted vs actual scores
            Useful for identifying systematic errors
```


### 4. FailureAnalyzer Class

**Purpose**: Identify common failure patterns and root causes from mismatched detections.

**Interface**:
```
FailureAnalyzer:
    Methods:
        analyze(mismatches, image_paths) → failure_analysis
            Input: List of mismatched events with annotated images
            Output: Failure analysis with patterns and recommendations
            
            Algorithm:
                1. Categorize failures by type
                2. Identify top 5 failure modes
                3. Analyze systematic vs random errors
                4. Review annotated images for each failure
                5. Document root causes
                6. Generate recommendations
        
        categorize_failures(mismatches) → dict
            Categories:
                - "adjacent_sector": Off by 1 sector
                - "wrong_ring": Correct sector, wrong ring
                - "opposite_sector": Off by ~10 sectors (180° error)
                - "complete_miss": No detection when dart present
                - "false_positive": Detection when no dart
                - "other": Uncategorized errors
            
            Return dict mapping category → list of failures
        
        identify_top_failure_modes(categorized) → list
            Sort categories by frequency
            Return top 5 with counts and percentages
        
        analyze_systematic_errors(failures) → list
            Look for patterns:
                - Consistent offset in specific board region
                - Specific camera always failing
                - Specific ring type always wrong
                - Time-of-day correlation
            
            Return list of systematic patterns found
        
        generate_recommendations(patterns) → list
            Based on failure patterns, suggest fixes:
                - Calibration adjustments
                - Detection threshold tuning
                - Algorithm improvements
                - Hardware adjustments
```


### 5. PerformanceProfiler Class

**Purpose**: Measure system performance metrics including latency, CPU usage, and memory consumption.

**Interface**:
```
PerformanceProfiler:
    State:
        profiling_active: boolean
        event_timings: list of timing records
        system_metrics: list of CPU/memory samples
        start_time: timestamp
    
    Methods:
        start_profiling()
            Algorithm:
                1. Set profiling_active = true
                2. Start background thread for system metrics sampling
                3. Record start_time
        
        record_event_timing(event_type, stage_timings)
            Input:
                - event_type: string ("dart_hit", "dart_removed", etc.)
                - stage_timings: dict with per-stage durations
                  {"detection": 45ms, "fusion": 8ms, "scoring": 2ms}
            
            Algorithm:
                1. Calculate total latency
                2. Store timing record with timestamp
                3. Write to performance.jsonl
        
        record_system_metrics(cpu_percent, memory_mb)
            Called periodically (every 100ms) by background thread
            Store CPU and memory samples
        
        stop_profiling()
            Stop background thread
            Set profiling_active = false
        
        analyze_metrics() → performance_report
            Algorithm:
                1. Compute latency statistics (p50, p95, p99, max)
                2. Compute per-stage timing averages
                3. Compute CPU usage statistics
                4. Compute memory usage statistics
                5. Identify bottlenecks
                6. Return performance report dict
```


### 6. ReportGenerator Class

**Purpose**: Generate comprehensive validation report in Markdown format with all analysis results.

**Interface**:
```
ReportGenerator:
    Methods:
        generate_report(accuracy_results, failure_analysis, performance_report) → markdown
            Algorithm:
                1. Create executive summary
                2. Add accuracy metrics section
                3. Add failure analysis section
                4. Add performance metrics section
                5. Add known limitations section
                6. Add recommendations section
                7. Return complete markdown document
        
        create_executive_summary(results) → markdown
            High-level summary:
                - Total throws tested
                - Overall accuracy
                - Key findings
                - POC viability assessment
        
        create_accuracy_section(accuracy_results) → markdown
            Tables and charts:
                - Exact match rate
                - Sector accuracy
                - Ring accuracy
                - Per-region breakdown
                - Confusion matrix
        
        create_failure_section(failure_analysis) → markdown
            Failure mode analysis:
                - Top 5 failure modes with examples
                - Systematic error patterns
                - Annotated failure images
                - Root cause analysis
        
        create_performance_section(performance_report) → markdown
            Performance metrics:
                - Detection latency (p50, p95, p99)
                - Per-stage timing breakdown
                - CPU usage statistics
                - Memory usage statistics
                - Bottleneck identification
        
        create_recommendations_section(all_results) → markdown
            Prioritized recommendations:
                - Critical fixes for Phase 2
                - Calibration improvements
                - Algorithm enhancements
                - Hardware considerations
```


## Data Models

### Configuration Schema (config.toml additions)

```toml
# Validation session configuration
[validation]
session_duration_minutes = 60
target_throw_count = 100
performance_sample_interval_ms = 100
min_exact_match_rate = 0.60      # POC success threshold
min_sector_accuracy = 0.80
min_ring_accuracy = 0.85
max_detection_latency_ms = 500
```

### Ground Truth Entry Schema

```json
{
  "entry_id": "gt_001",
  "timestamp": "2024-01-15T14:32:18.123456Z",
  "system_event_id": "evt_20240115_143218_001",
  "intended_target": "T20",
  "actual_result": "T20",
  "match": true,
  "intended_parsed": {
    "ring": "triple",
    "sector": 20,
    "score": 60
  },
  "actual_parsed": {
    "ring": "triple",
    "sector": 20,
    "score": 60
  },
  "notes": "Clean hit, good detection"
}
```

### Performance Timing Record Schema

```json
{
  "timestamp": "2024-01-15T14:32:18.123456Z",
  "event_type": "dart_hit",
  "total_latency_ms": 55,
  "stage_timings": {
    "motion_detection_ms": 5,
    "dart_detection_ms": 42,
    "coordinate_mapping_ms": 3,
    "fusion_ms": 3,
    "scoring_ms": 2
  },
  "cameras_used": [0, 1, 2]
}
```

### System Metrics Sample Schema

```json
{
  "timestamp": "2024-01-15T14:32:18.123456Z",
  "cpu_percent": 45.2,
  "memory_mb": 512.8,
  "active_threads": 5
}
```


### Validation Report Structure

```markdown
# ARU-DART POC Validation Report
Date: YYYY-MM-DD
Session ID: session_YYYYMMDD_HHMMSS

## Executive Summary
- Total throws: 100
- Session duration: 45 minutes
- Overall exact match rate: 68%
- POC viability: PASS (exceeds 60% threshold)

## Accuracy Metrics

### Overall Accuracy
| Metric | Result | Target | Status |
|--------|--------|--------|--------|
| Exact Match | 68% | 60% | ✅ PASS |
| Sector Accuracy | 84% | 80% | ✅ PASS |
| Ring Accuracy | 89% | 85% | ✅ PASS |

### Per-Region Accuracy
| Region | Accuracy | Sample Size |
|--------|----------|-------------|
| Singles | 72% | 45 throws |
| Doubles | 65% | 20 throws |
| Triples | 58% | 25 throws |
| Bulls | 80% | 10 throws |

## Failure Analysis

### Top 5 Failure Modes
1. Adjacent sector error (12 occurrences, 38%)
2. Wrong ring, correct sector (8 occurrences, 25%)
3. Complete miss (5 occurrences, 16%)
4. Opposite sector (4 occurrences, 13%)
5. False positive (3 occurrences, 9%)

### Systematic Errors
- Sector 6 consistently detected as Sector 13 (camera blind spot)
- Triple ring often detected as single (calibration offset)
- Camera 1 has 15% lower detection rate

## Performance Metrics

### Detection Latency
- p50: 52ms
- p95: 98ms
- p99: 145ms
- Max: 203ms
- Average: 58ms

### Per-Stage Timing
- Motion detection: 5ms avg
- Dart detection: 42ms avg
- Coordinate mapping: 3ms avg
- Fusion: 3ms avg
- Scoring: 2ms avg

### System Resources
- CPU usage: 35-55% (avg 42%)
- Memory usage: 480-520MB (avg 498MB)
- No memory leaks detected

## Known Limitations
1. Camera blind spots at sector boundaries
2. Triple ring calibration needs refinement
3. Occasional false positives from board reflections
4. Performance degrades slightly after 30+ minutes

## Recommendations for Phase 2

### Critical (P0)
1. Improve calibration for triple ring detection
2. Address camera 1 blind spot (sector 6/13 boundary)
3. Implement false positive filtering

### High Priority (P1)
4. Optimize dart detection algorithm (reduce latency)
5. Add automatic calibration validation
6. Implement confidence thresholding

### Medium Priority (P2)
7. Add multi-dart tracking improvements
8. Enhance bounce-out detection
9. Implement adaptive thresholding per region
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After analyzing all acceptance criteria, I identified the following testable properties and eliminated redundancy:

**Redundancy Analysis**:
- AC-10.2.1, AC-10.2.2, AC-10.2.3, AC-10.2.4 (accuracy computations) → Can be combined into Property 1 (accuracy computation correctness)
- AC-10.5.1 through AC-10.5.5 (report sections) → Combined into Property 6 (report structure completeness)
- AC-10.4.1 and AC-10.4.2 (timing measurements) → Combined into Property 4 (timing measurement correctness)

**Properties to Test**:
1. Accuracy computation correctness (all metrics)
2. Ground truth logging round trip
3. Event recording completeness
4. Timing measurement correctness
5. Failure categorization correctness
6. Report structure completeness


### Property 1: Accuracy Computation Correctness

*For any* set of ground truth entries and corresponding system events, the computed accuracy metrics (exact match rate, sector accuracy, ring accuracy, per-region accuracy) should match manually calculated values within 0.01% tolerance.

**Validates: Requirements AC-10.2.1, AC-10.2.2, AC-10.2.3, AC-10.2.4**

**Test Strategy**: Generate random sets of ground truth and system events with known matches/mismatches. Manually compute expected accuracy metrics. Verify analyzer output matches expected values. Test edge cases (all matches, all mismatches, empty sets).

### Property 2: Ground Truth Logging Round Trip

*For any* valid ground truth entry (intended target, actual result), logging the entry then retrieving it should return an equivalent entry with all fields preserved.

**Validates: Requirements AC-10.1.2**

**Test Strategy**: Generate random ground truth entries with various target formats (T20, D16, Bull, S5, Miss). Log each entry, retrieve it, verify all fields match. Test target parsing correctness.

### Property 3: Event Recording Completeness

*For any* system event emitted during a validation session, the event should be recorded to the system_events.jsonl file with all required fields and correct timestamp ordering.

**Validates: Requirements AC-10.1.3**

**Test Strategy**: Generate random sequences of system events. Record them through ValidationSession. Verify all events appear in log file. Verify timestamp ordering is preserved. Verify no events are lost or duplicated.

### Property 4: Timing Measurement Correctness

*For any* recorded event timing with per-stage durations, the total latency should equal the sum of all stage timings within 1ms tolerance (accounting for rounding).

**Validates: Requirements AC-10.4.1, AC-10.4.2**

**Test Strategy**: Generate random timing records with various stage durations. Verify total_latency = sum(stage_timings). Test edge cases (zero durations, very large durations).

### Property 5: Failure Categorization Correctness

*For any* mismatch between system detection and ground truth, the failure should be categorized into exactly one category (adjacent_sector, wrong_ring, opposite_sector, complete_miss, false_positive, other) based on the error pattern.

**Validates: Requirements AC-10.3.1, AC-10.3.4**

**Test Strategy**: Generate mismatches with known error patterns. Verify correct categorization:
- System sector ± 1 from ground truth → adjacent_sector
- Same sector, different ring → wrong_ring
- Sector difference ~10 (180° error) → opposite_sector
- System detected nothing, ground truth has dart → complete_miss
- System detected dart, ground truth is miss → false_positive

### Property 6: Report Structure Completeness

*For any* generated validation report, the report should contain all required sections (executive summary, accuracy metrics, failure analysis, performance metrics, known limitations, recommendations) with non-empty content in each section.

**Validates: Requirements AC-10.5.1, AC-10.5.2, AC-10.5.3, AC-10.5.4, AC-10.5.5**

**Test Strategy**: Generate reports from various analysis results. Parse markdown structure. Verify all required section headers present. Verify each section has content (not just headers). Test with minimal and comprehensive data sets.


## Error Handling

### Missing Ground Truth Entry

**Scenario**: System event recorded but user forgets to log ground truth

**Handling**:
```
analyze(ground_truth_entries, system_events):
    matched_events = []
    unmatched_events = []
    
    for system_event in system_events:
        ground_truth = find_matching_entry(system_event.id)
        
        if ground_truth is null:
            log_warning("No ground truth for event: " + system_event.id)
            unmatched_events.append(system_event)
        else:
            matched_events.append((system_event, ground_truth))
    
    if count(unmatched_events) > 0:
        log_warning("Analysis incomplete: " + count(unmatched_events) + " events without ground truth")
        # Include in report as limitation
    
    # Continue analysis with matched events only
```

**Behavior**:
- Log warning for each unmatched event
- Exclude from accuracy calculations
- Report count of unmatched events in validation report
- Analysis proceeds with available matched data

### Invalid Target Format

**Scenario**: User enters ground truth in unexpected format (e.g., "triple 20" instead of "T20")

**Handling**:
```
parse_target(target_string):
    # Try standard formats first
    if matches_pattern(target_string, "T\d+"):
        return parse_triple(target_string)
    elif matches_pattern(target_string, "D\d+"):
        return parse_double(target_string)
    # ... other standard formats ...
    
    # Try fuzzy matching
    normalized = normalize_string(target_string)
    if normalized in known_aliases:
        return parse_target(known_aliases[normalized])
    
    # If all parsing fails
    log_error("Invalid target format: " + target_string)
    prompt_user_for_correction()
    return null
```

**Behavior**:
- Attempt multiple parsing strategies
- Support common aliases ("triple 20" → "T20", "bull" → "Bull")
- Prompt user for correction if parsing fails
- Log invalid entries for review

### Session Interrupted

**Scenario**: Validation session crashes or is interrupted mid-session

**Handling**:
```
ValidationSession:
    # Write to JSONL files incrementally (append mode)
    # Each event written immediately, not buffered
    
    end():
        if not clean_shutdown:
            log_warning("Session interrupted, partial data saved")
            mark_session_as_incomplete()
        
        # Close all file handles
        # Flush all buffers
```

**Behavior**:
- All data written incrementally (no data loss)
- Session marked as incomplete in metadata
- Analysis can still run on partial data
- Report includes disclaimer about incomplete session

### Performance Profiler Overhead

**Scenario**: Performance profiling itself impacts system performance

**Handling**:
```
PerformanceProfiler:
    # Use lightweight sampling
    # Background thread with low priority
    # Configurable sample interval (default 100ms)
    
    record_system_metrics():
        if time_since_last_sample < sample_interval:
            return  # Skip this sample
        
        # Quick snapshot (< 1ms overhead)
        cpu = get_cpu_percent()
        memory = get_memory_usage()
        
        # Async write to file (non-blocking)
        async_write(metrics_file, {cpu, memory, timestamp})
```

**Behavior**:
- Minimal overhead (< 1% CPU impact)
- Configurable sampling rate
- Non-blocking writes
- Can be disabled if needed

### Zero Throws in Category

**Scenario**: No throws in specific region (e.g., no triple attempts)

**Handling**:
```
compute_per_region_accuracy(matches):
    regions = {"singles": [], "doubles": [], "triples": [], "bulls": []}
    
    # Group matches by region
    for match in matches:
        region = determine_region(match.ground_truth)
        regions[region].append(match)
    
    # Compute accuracy for each region
    results = {}
    for region, region_matches in regions:
        if count(region_matches) == 0:
            results[region] = null  # Insufficient data
            log_info("No throws in region: " + region)
        else:
            results[region] = compute_accuracy(region_matches)
    
    return results
```

**Behavior**:
- Mark region as "insufficient data" (null)
- Log informational message
- Report shows "N/A" for regions with no data
- Does not fail analysis

### Corrupted Session Data

**Scenario**: JSONL file contains malformed JSON lines

**Handling**:
```
load_session_data(jsonl_path):
    valid_entries = []
    corrupted_lines = []
    
    for line_number, line in enumerate(file):
        try:
            entry = parse_json(line)
            validate_schema(entry)
            valid_entries.append(entry)
        except ParseError as e:
            log_error("Corrupted line " + line_number + ": " + e)
            corrupted_lines.append((line_number, line))
    
    if count(corrupted_lines) > 0:
        log_warning("Skipped " + count(corrupted_lines) + " corrupted lines")
        # Save corrupted lines to separate file for debugging
        save_corrupted_lines(corrupted_lines)
    
    return valid_entries
```

**Behavior**:
- Skip corrupted lines
- Log each corruption with line number
- Save corrupted data for debugging
- Continue analysis with valid data
- Report includes corruption count


## Testing Strategy

### Dual Testing Approach

The validation system requires both unit tests and property-based tests for comprehensive validation:

**Unit Tests**: Verify specific examples, edge cases, and error conditions
- Specific accuracy calculations with known inputs
- Ground truth parsing for various formats
- Report generation with sample data
- Error handling scenarios
- File I/O operations

**Property Tests**: Verify universal properties across all inputs
- Accuracy computation correctness for random data sets
- Ground truth logging round trip
- Event recording completeness
- Timing measurement correctness
- Failure categorization for all error patterns
- Report structure completeness

Both approaches are complementary and necessary for ensuring correctness.

### Property-Based Testing Configuration

**Library**: Use `hypothesis` for Python property-based testing

**Configuration**:
- Minimum 100 iterations per property test (due to randomization)
- Each property test references its design document property
- Tag format: `# Feature: step-10-poc-validation, Property N: [property text]`

**Example Property Test**:
```python
from hypothesis import given, strategies as st

@given(
    ground_truth=st.lists(st.builds(GroundTruthEntry), min_size=10, max_size=100),
    system_events=st.lists(st.builds(DartHitEvent), min_size=10, max_size=100)
)
def test_accuracy_computation_correctness(ground_truth, system_events):
    """
    Feature: step-10-poc-validation, Property 1: Accuracy Computation Correctness
    
    For any set of ground truth entries and system events, computed accuracy
    metrics should match manually calculated values.
    """
    analyzer = AccuracyAnalyzer()
    
    # Compute using analyzer
    results = analyzer.analyze(ground_truth, system_events)
    
    # Manually compute expected values
    expected_exact_match = manual_compute_exact_match(ground_truth, system_events)
    expected_sector_accuracy = manual_compute_sector_accuracy(ground_truth, system_events)
    
    # Verify within tolerance
    assert abs(results['exact_match_rate'] - expected_exact_match) < 0.0001
    assert abs(results['sector_accuracy'] - expected_sector_accuracy) < 0.0001
```

### Unit Testing Patterns

**Accuracy Analyzer Tests**:
```python
def test_exact_match_all_correct():
    """All system events match ground truth exactly"""
    ground_truth = [create_entry("T20", "T20"), create_entry("D16", "D16")]
    system_events = [create_event(60), create_event(32)]
    
    analyzer = AccuracyAnalyzer()
    results = analyzer.analyze(ground_truth, system_events)
    
    assert results['exact_match_rate'] == 1.0

def test_exact_match_all_wrong():
    """No system events match ground truth"""
    ground_truth = [create_entry("T20", "T20"), create_entry("D16", "D16")]
    system_events = [create_event(5), create_event(10)]
    
    analyzer = AccuracyAnalyzer()
    results = analyzer.analyze(ground_truth, system_events)
    
    assert results['exact_match_rate'] == 0.0

def test_sector_accuracy_correct_sector_wrong_ring():
    """Correct sector but wrong ring should count for sector accuracy"""
    ground_truth = [create_entry("T20", "T20")]  # Triple 20
    system_events = [create_event(20)]  # Single 20
    
    analyzer = AccuracyAnalyzer()
    results = analyzer.analyze(ground_truth, system_events)
    
    assert results['exact_match_rate'] == 0.0
    assert results['sector_accuracy'] == 1.0
```

**Failure Analyzer Tests**:
```python
def test_categorize_adjacent_sector():
    """Off by 1 sector should be categorized as adjacent_sector"""
    mismatch = create_mismatch(
        ground_truth={"sector": 20, "ring": "triple"},
        system={"sector": 1, "ring": "triple"}
    )
    
    analyzer = FailureAnalyzer()
    category = analyzer.categorize_failure(mismatch)
    
    assert category == "adjacent_sector"

def test_categorize_wrong_ring():
    """Same sector, different ring should be categorized as wrong_ring"""
    mismatch = create_mismatch(
        ground_truth={"sector": 20, "ring": "triple"},
        system={"sector": 20, "ring": "single"}
    )
    
    analyzer = FailureAnalyzer()
    category = analyzer.categorize_failure(mismatch)
    
    assert category == "wrong_ring"
```

### Integration Testing

**End-to-End Validation Session**:
```python
def test_validation_session_end_to_end():
    """Complete validation session workflow"""
    session = ValidationSession(config)
    session.start()
    
    # Simulate throws
    for i in range(10):
        # System detects dart
        event = create_dart_hit_event(score=60)
        session.record_system_event(event)
        
        # User logs ground truth
        ground_truth = create_ground_truth_entry("T20", "T20")
        session.log_ground_truth(ground_truth)
    
    session.end()
    
    # Verify session data saved
    assert os.path.exists(session.session_dir / "ground_truth.jsonl")
    assert os.path.exists(session.session_dir / "system_events.jsonl")
    assert os.path.exists(session.session_dir / "performance.jsonl")
    
    # Verify data integrity
    ground_truth_entries = load_jsonl(session.session_dir / "ground_truth.jsonl")
    assert len(ground_truth_entries) == 10
```

### Manual Testing Checklist

Before running full validation session:

1. **Verify ground truth logging**:
   - Test various target formats (T20, D16, Bull, S5, Miss)
   - Verify parsing handles common variations
   - Check JSONL file format

2. **Verify event recording**:
   - Throw test darts
   - Verify all events captured
   - Check timestamp ordering

3. **Verify performance profiling**:
   - Check CPU/memory sampling works
   - Verify minimal overhead
   - Check metrics file format

4. **Run analysis on test data**:
   - Create small test session (10-20 throws)
   - Run analysis script
   - Verify report generation
   - Check all sections present

5. **Test error handling**:
   - Skip ground truth entry (verify warning)
   - Enter invalid format (verify correction prompt)
   - Interrupt session (verify partial data saved)
