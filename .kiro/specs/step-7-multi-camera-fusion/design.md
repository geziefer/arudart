# Step 7: Multi-Camera Fusion and Score Derivation - Design Document

## Overview

This design document specifies the architecture for combining dart tip detections from multiple cameras into a single fused position in board coordinates, then deriving the dart score (sector and ring). This is the core scoring logic that transforms raw detections into game-relevant information.

The fusion system takes per-camera detections (with board coordinates from Step 6) and produces a single `DartHitEvent` containing the fused position, polar coordinates, sector/ring determination, and final score. The system handles 0-3 camera detections per throw with outlier rejection and confidence-weighted averaging.

**Key Design Principles**:
- Confidence-weighted fusion for multi-camera detections
- Outlier rejection to handle erroneous detections
- Standard dartboard geometry (Winmau Blade 6 specifications)
- Configurable sector offset for camera mounting rotation
- Complete event data for downstream systems (logging, API, UI)
- Real-time performance (<10ms fusion + scoring)

## Architecture

### Module Structure

```
src/fusion/
├── __init__.py
├── coordinate_fusion.py        # CoordinateFusion class
├── polar_converter.py          # PolarConverter class
├── ring_detector.py            # RingDetector class
├── sector_detector.py          # SectorDetector class
├── score_calculator.py         # ScoreCalculator class
└── dart_hit_event.py           # DartHitEvent dataclass

config.toml additions:
[fusion]
outlier_threshold_mm = 50.0
min_confidence = 0.3

[board]
radius_mm = 170.0
bull_radius_mm = 6.35
single_bull_radius_mm = 15.9
triple_inner_mm = 99.0
triple_outer_mm = 107.0
double_inner_mm = 162.0
double_outer_mm = 170.0

[board.sectors]
# Sector layout: 20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5
sector_order = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
sector_width_deg = 18.0
wire_gap_deg = 2.0
sector_offset_deg = 0.0  # Adjust based on camera mounting
```

### Class Hierarchy

```
DartHitEvent (dataclass)
└── Complete event data structure

CoordinateFusion
├── fuse_detections() → (x, y, confidence, cameras_used)
├── reject_outliers()
└── compute_weighted_average()

PolarConverter
├── cartesian_to_polar() → (r, θ)
└── polar_to_cartesian() → (x, y)

RingDetector
└── determine_ring() → (ring_name, multiplier, base_score)

SectorDetector
└── determine_sector() → sector_number

ScoreCalculator
├── calculate_score() → Score
└── create_dart_hit_event() → DartHitEvent
```


### Data Flow

```
Per-Camera Detections (from Step 5 + Step 6)
    ↓
[{camera_id: 0, pixel: (u, v), board: (x, y), confidence: 0.85}, ...]
    ↓
[CoordinateFusion.fuse_detections()]
    ↓
1. Filter by minimum confidence
2. Reject outliers (>50mm from median)
3. Compute weighted average by confidence
    ↓
Fused Board Coordinates (x, y) + confidence + cameras_used
    ↓
[PolarConverter.cartesian_to_polar()]
    ↓
Polar Coordinates (r, θ)
    ↓
[RingDetector.determine_ring(r)]
    ↓
Ring (bull/single_bull/triple/double/single/out_of_bounds)
    ↓
[SectorDetector.determine_sector(θ)]
    ↓
Sector Number (1-20)
    ↓
[ScoreCalculator.calculate_score()]
    ↓
Score (base, multiplier, total)
    ↓
[ScoreCalculator.create_dart_hit_event()]
    ↓
DartHitEvent (complete event with all data)
```

### Integration with Existing System

The fusion system integrates after coordinate mapping in the main detection loop:

```python
# In main.py (after dart detection and coordinate mapping)
if motion_state == "dart_detected":
    detections = []
    
    # Collect detections from all cameras
    for camera_id in camera_ids:
        tip_x_px, tip_y_px, confidence, debug_info = dart_detectors[camera_id].detect(...)
        
        if tip_x_px is not None and coordinate_mapper.is_calibrated(camera_id):
            board_x, board_y = coordinate_mapper.map_to_board(camera_id, tip_x_px, tip_y_px)
            
            if board_x is not None:
                detections.append({
                    'camera_id': camera_id,
                    'pixel': (tip_x_px, tip_y_px),
                    'board': (board_x, board_y),
                    'confidence': confidence
                })
    
    # NEW: Fuse detections and derive score
    if detections:
        dart_hit_event = score_calculator.process_detections(detections)
        
        if dart_hit_event is not None:
            logger.info(f"Dart scored: {dart_hit_event.score.total} "
                       f"({dart_hit_event.score.base} × {dart_hit_event.score.multiplier})")
            logger.info(f"Position: ({dart_hit_event.board_x:.1f}, {dart_hit_event.board_y:.1f}) mm, "
                       f"r={dart_hit_event.radius:.1f} mm, θ={dart_hit_event.angle_deg:.1f}°")
            logger.info(f"Cameras used: {dart_hit_event.cameras_used}")
            
            # Save event to JSON
            event_path = f"data/throws/event_{timestamp}.json"
            with open(event_path, 'w') as f:
                json.dump(dart_hit_event.to_dict(), f, indent=2)
        else:
            logger.warning("No valid detections after fusion")
    else:
        logger.warning("No detections from any camera")
```

## Components and Interfaces

### 1. DartHitEvent Dataclass

**Purpose**: Complete data structure for a dart throw event with all detection, fusion, and scoring information.

**Data Structure**:
```
Score:
    base: integer (1-20 for sectors, 50 for bull, 25 for single bull, 0 for miss)
    multiplier: integer (0, 1, 2, or 3)
    total: integer (final score)
    ring: string ("bull", "single_bull", "triple", "double", "single", "out_of_bounds")
    sector: optional integer (1-20, or null for bulls/miss)

CameraDetection:
    camera_id: integer
    pixel_x, pixel_y: float (pixel coordinates)
    board_x, board_y: float (board coordinates in mm)
    confidence: float [0, 1]

DartHitEvent:
    timestamp: string (ISO 8601 format)
    board_x, board_y: float (fused board coordinates in mm)
    radius: float (distance from center in mm)
    angle_rad: float (angle in radians [0, 2π))
    angle_deg: float (angle in degrees [0, 360))
    score: Score object
    fusion_confidence: float (combined confidence)
    cameras_used: list of integers (camera IDs)
    num_cameras: integer (count of cameras used)
    detections: list of CameraDetection objects
    image_paths: dictionary mapping camera_id → image path
    
Methods:
    to_dict() → dictionary (JSON-serializable)
    from_dict(dictionary) → DartHitEvent (deserialize)
```


### 2. CoordinateFusion Class

**Purpose**: Combine multiple camera detections into a single fused board coordinate using confidence-weighted averaging and outlier rejection.

**Interface**:
```
CoordinateFusion:
    Configuration:
        outlier_threshold_mm: float (default 50.0)
        min_confidence: float (default 0.3)
    
    Methods:
        fuse_detections(detections) → (fused_x, fused_y, confidence, cameras_used) or null
            Input: list of detections with {camera_id, board: (x, y), confidence}
            Output: fused coordinates, combined confidence, list of camera IDs used
            
            Algorithm:
                1. Filter detections by minimum confidence threshold
                2. If no valid detections: return null
                3. If single detection: return it directly
                4. If multiple detections:
                   a. Compute median position
                   b. Reject outliers (distance > threshold from median)
                   c. Compute confidence-weighted average of inliers
                   d. Combine confidences (average of inlier confidences)
                   e. Return fused position and metadata
        
        reject_outliers(detections) → list of inlier detections
            - Compute median position from all detections
            - For each detection, compute distance from median
            - Keep detections within outlier_threshold_mm
            - Special case: if ≤2 detections, keep all (no outlier rejection)
        
        compute_weighted_average(detections) → (weighted_x, weighted_y)
            - Sum of (coordinate × confidence) / sum of confidences
            - Applied separately to X and Y coordinates
```

### 3. PolarConverter Class

**Purpose**: Convert between Cartesian (x, y) and polar (r, θ) coordinate systems.

**Interface**:
```
PolarConverter:
    Methods:
        cartesian_to_polar(x, y) → (r, theta)
            Input: Cartesian coordinates (x, y) in mm
            Output: Polar coordinates (r, theta)
                r: radius in mm (distance from origin)
                theta: angle in radians [0, 2π), counter-clockwise from +X axis
            
            Algorithm:
                r = sqrt(x² + y²)
                if r == 0:
                    theta = 0  (arbitrary for origin)
                else:
                    theta = atan2(y, x)
                    if theta < 0:
                        theta = theta + 2π  (normalize to [0, 2π))
        
        polar_to_cartesian(r, theta) → (x, y)
            Input: Polar coordinates (r, theta)
            Output: Cartesian coordinates (x, y) in mm
            
            Algorithm:
                x = r × cos(theta)
                y = r × sin(theta)
        
        radians_to_degrees(theta_rad) → theta_deg
        degrees_to_radians(theta_deg) → theta_rad
```


### 4. RingDetector Class

**Purpose**: Determine which ring (bull, single bull, triple, double, single, or out of bounds) the dart hit based on radius.

**Interface**:
```
RingDetector:
    Configuration:
        bull_radius: 6.35 mm
        single_bull_radius: 15.9 mm
        triple_inner: 99.0 mm
        triple_outer: 107.0 mm
        double_inner: 162.0 mm
        double_outer: 170.0 mm
    
    Methods:
        determine_ring(radius) → (ring_name, multiplier, base_score)
            Input: radius in mm (distance from board center)
            Output: ring classification, score multiplier, base score
            
            Ring boundaries (Winmau Blade 6 specifications):
                if radius < 6.35:
                    → ("bull", 0, 50)
                elif radius < 15.9:
                    → ("single_bull", 0, 25)
                elif 99 ≤ radius < 107:
                    → ("triple", 3, 0)  # base score from sector
                elif 162 ≤ radius < 170:
                    → ("double", 2, 0)  # base score from sector
                elif radius ≥ 170:
                    → ("out_of_bounds", 0, 0)
                else:
                    → ("single", 1, 0)  # base score from sector
```


### 5. SectorDetector Class

**Purpose**: Determine which sector (1-20) the dart hit based on angle.

**Interface**:
```
SectorDetector:
    Configuration:
        sector_order: [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
        sector_width_deg: 18.0
        wire_gap_deg: 2.0
        sector_offset_deg: 0.0 (configurable for camera mounting)
    
    Methods:
        determine_sector(theta_rad) → sector_number or null
            Input: angle in radians [0, 2π), counter-clockwise from +X axis
            Output: sector number (1-20) or null if on wire
            
            Algorithm:
                1. Convert angle to degrees
                2. Apply sector_offset_deg (camera mounting rotation)
                3. Rotate coordinate system so sector 20 is at 0°
                   (standard dartboard has sector 20 at top = 90° in Cartesian)
                4. Determine wedge index (0-19) from angle
                5. Check if within sector or on wire (last 2° of wedge)
                6. If on wire: assign to next sector (or return null)
                7. Map wedge index to sector number using sector_order
            
            Coordinate system:
                θ=0° is +X axis (3 o'clock)
                θ=90° is +Y axis (12 o'clock, where sector 20 is centered)
                Angles increase counter-clockwise
```


### 6. ScoreCalculator Class

**Purpose**: Orchestrate the complete fusion and scoring pipeline, creating the final DartHitEvent.

**Interface**:
```
ScoreCalculator:
    Components:
        coordinate_fusion: CoordinateFusion instance
        polar_converter: PolarConverter instance
        ring_detector: RingDetector instance
        sector_detector: SectorDetector instance
    
    Methods:
        process_detections(detections, image_paths) → DartHitEvent or null
            Input: 
                - detections: list of {camera_id, pixel: (u, v), board: (x, y), confidence}
                - image_paths: optional dict mapping camera_id → image path
            Output: Complete DartHitEvent or null if fusion fails
            
            Pipeline:
                1. Fuse coordinates → (x, y, confidence, cameras_used)
                2. Convert to polar → (r, θ)
                3. Determine ring → (ring_name, multiplier, base_score)
                4. Determine sector → sector_number (if not bull/miss)
                5. Calculate final score
                6. Create DartHitEvent with all data
        
        calculate_score(ring_name, multiplier, base_score, sector) → Score
            Score calculation rules:
                if ring_name == "bull":
                    → Score(base=50, multiplier=0, total=50, ring="bull", sector=null)
                elif ring_name == "single_bull":
                    → Score(base=25, multiplier=0, total=25, ring="single_bull", sector=null)
                elif ring_name == "out_of_bounds":
                    → Score(base=0, multiplier=0, total=0, ring="out_of_bounds", sector=null)
                else:
                    total = sector × multiplier
                    → Score(base=sector, multiplier=multiplier, total=total, ring=ring_name, sector=sector)
        
        create_event(...) → DartHitEvent
            Assembles all data into DartHitEvent structure:
                - Generate ISO 8601 timestamp
                - Convert detections to CameraDetection objects
                - Populate all fields (coordinates, score, fusion metadata)
```



## Data Models

### Configuration Schema (config.toml additions)

```toml
# Multi-camera fusion configuration
[fusion]
outlier_threshold_mm = 50.0  # Reject detections >50mm from median
min_confidence = 0.3         # Minimum confidence to consider detection

# Dartboard dimensions (Winmau Blade 6 specifications)
[board]
radius_mm = 170.0            # Outer edge of double ring
bull_radius_mm = 6.35        # Double bull radius
single_bull_radius_mm = 15.9 # Single bull outer radius
triple_inner_mm = 99.0       # Triple ring inner radius
triple_outer_mm = 107.0      # Triple ring outer radius
double_inner_mm = 162.0      # Double ring inner radius
double_outer_mm = 170.0      # Double ring outer radius

# Sector configuration
[board.sectors]
# Standard dartboard layout (clockwise from top)
sector_order = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
sector_width_deg = 18.0      # Active scoring area per sector
wire_gap_deg = 2.0           # Wire width (non-scoring)
sector_offset_deg = 0.0      # Rotation offset (adjust for camera mounting)
```

### DartHitEvent JSON Format

**Example event JSON**:
```json
{
  "timestamp": "2024-01-15T14:32:18.123456Z",
  "board_coordinates": {
    "x_mm": 2.3,
    "y_mm": 98.7
  },
  "polar_coordinates": {
    "radius_mm": 98.7,
    "angle_rad": 1.547,
    "angle_deg": 88.6
  },
  "score": {
    "base": 20,
    "multiplier": 3,
    "total": 60,
    "ring": "triple",
    "sector": 20
  },
  "fusion": {
    "confidence": 0.82,
    "cameras_used": [0, 1, 2],
    "num_cameras": 3
  },
  "detections": [
    {
      "camera_id": 0,
      "pixel": {"x": 412.3, "y": 287.5},
      "board": {"x": 1.8, "y": 99.2},
      "confidence": 0.85
    },
    {
      "camera_id": 1,
      "pixel": {"x": 398.7, "y": 301.2},
      "board": {"x": 2.5, "y": 98.5},
      "confidence": 0.78
    },
    {
      "camera_id": 2,
      "pixel": {"x": 425.1, "y": 295.8},
      "board": {"x": 2.6, "y": 98.4},
      "confidence": 0.83
    }
  ],
  "image_paths": {
    "0": "data/throws/cam0_annotated_20240115_143218.jpg",
    "1": "data/throws/cam1_annotated_20240115_143218.jpg",
    "2": "data/throws/cam2_annotated_20240115_143218.jpg"
  }
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After analyzing all acceptance criteria, I identified the following testable properties and eliminated redundancy:

**Redundancy Analysis**:
- AC-7.3.1 through AC-7.3.6 (ring determination for different radii) → Combined into Property 1 (comprehensive ring determination)
- AC-7.5.4, AC-7.5.5, AC-7.6.2-7.6.6 (data structure completeness) → Combined into Property 8 (event structure completeness)
- AC-7.2.1, AC-7.2.2, AC-7.2.3 (individual polar conversions) → Subsumed by Property 2 (round trip property)
- AC-7.4.1 and AC-7.4.2 (sector mapping) → Combined into Property 4 (sector determination correctness)

**Properties to Test**:
1. Ring determination correctness (all radius ranges)
2. Polar coordinate round trip
3. Weighted average fusion correctness
4. Sector determination correctness
5. Outlier rejection correctness
6. Score calculation correctness
7. Event JSON serialization round trip
8. Event structure completeness

### Property 1: Ring Determination Correctness

*For any* radius value, the ring detector should correctly classify it into exactly one ring category (bull, single_bull, triple, double, single, or out_of_bounds) according to the specified boundaries, and assign the correct multiplier and base score.

**Validates: Requirements AC-7.3.1, AC-7.3.2, AC-7.3.3, AC-7.3.4, AC-7.3.5, AC-7.3.6**

**Test Strategy**: Generate random radii across all ranges (0-200mm) and verify:
- r < 6.35mm → ("bull", 0, 50)
- 6.35mm ≤ r < 15.9mm → ("single_bull", 0, 25)
- 99mm ≤ r < 107mm → ("triple", 3, 0)
- 162mm ≤ r < 170mm → ("double", 2, 0)
- Other valid ranges → ("single", 1, 0)
- r ≥ 170mm → ("out_of_bounds", 0, 0)

### Property 2: Polar Coordinate Round Trip

*For any* valid board coordinate (x, y) within reasonable bounds (-200mm to +200mm), converting to polar coordinates then back to Cartesian should return approximately the same point: `polar_to_cartesian(cartesian_to_polar(x, y)) ≈ (x, y)` within 0.01mm tolerance.

**Validates: Requirements AC-7.2.1, AC-7.2.2, AC-7.2.3, AC-7.2.5**

**Test Strategy**: Generate random (x, y) coordinates, apply round trip transformation, verify error < 0.01mm. This validates both conversion directions and angle normalization.

### Property 3: Weighted Average Fusion Correctness

*For any* set of 2+ valid detections with positive confidences, the fused coordinate should be the confidence-weighted average of the input coordinates, and the combined confidence should be the average of individual confidences.

**Validates: Requirements AC-7.1.3, AC-7.1.5**

**Test Strategy**: Generate random detection sets with varying positions and confidences, compute expected weighted average manually, verify fusion output matches within 0.01mm tolerance.

### Property 4: Sector Determination Correctness

*For any* angle θ in the range [0, 2π), the sector detector should map it to exactly one sector number (1-20) according to the standard dartboard layout, with sector 20 centered at the top (90° in Cartesian coordinates).

**Validates: Requirements AC-7.4.1, AC-7.4.2, AC-7.4.3, AC-7.4.4**

**Test Strategy**: Generate random angles, verify sector mapping follows the standard layout. Test specific angles (e.g., 90° → sector 20, 81° → sector 1). Verify angle wraparound (359° and 1° map to adjacent sectors).

### Property 5: Outlier Rejection Correctness

*For any* set of 3+ detections where one or more are >50mm from the median position, the outlier rejection algorithm should discard exactly those detections that exceed the threshold, and retain all inliers.

**Validates: Requirements AC-7.1.4**

**Test Strategy**: Generate detection sets with known outliers (e.g., 2 detections at (0, 100) and 1 at (0, 200)). Verify outliers are correctly identified and removed. Test edge cases (all outliers, no outliers, exactly at threshold).

### Property 6: Score Calculation Correctness

*For any* valid ring and sector combination, the total score should equal sector_number × multiplier for regular rings, or the fixed score (50/25/0) for bulls and misses.

**Validates: Requirements AC-7.5.1, AC-7.5.2, AC-7.5.3**

**Test Strategy**: Generate random sector/ring combinations, verify score calculation:
- Bull → total = 50
- Single bull → total = 25
- Triple 20 → total = 60 (20 × 3)
- Double 18 → total = 36 (18 × 2)
- Single 5 → total = 5 (5 × 1)
- Out of bounds → total = 0

### Property 7: Event JSON Serialization Round Trip

*For any* valid DartHitEvent, serializing to JSON then deserializing should produce an equivalent event with all fields matching within floating-point tolerance.

**Validates: Requirements AC-7.6.7**

**Test Strategy**: Generate random DartHitEvent objects, serialize with `to_dict()`, deserialize with `from_dict()`, verify all fields match. This validates JSON serialization correctness.

### Property 8: Event Structure Completeness

*For any* DartHitEvent created from valid detections, the event should contain all required fields: timestamp (ISO 8601), board coordinates (x, y), polar coordinates (r, θ), score (base, multiplier, total, ring, sector), fusion metadata (confidence, cameras_used, num_cameras), and per-camera detections.

**Validates: Requirements AC-7.5.4, AC-7.5.5, AC-7.6.1, AC-7.6.2, AC-7.6.3, AC-7.6.4, AC-7.6.5, AC-7.6.6**

**Test Strategy**: Generate random detection sets, create events, verify all required fields are present and have valid values (non-None, correct types, reasonable ranges).



## Error Handling

### No Valid Detections

**Scenario**: All cameras fail to detect dart, or all detections below confidence threshold

**Handling**:
```
process_detections(detections):
    fusion_result = coordinate_fusion.fuse_detections(detections)
    
    if fusion_result is null:
        log_warning("No valid detections after fusion")
        return null
    
    # Continue processing...
```

**Behavior**:
- Return null from process_detections()
- Log warning with reason (no detections, low confidence, all outliers)
- Main loop logs "No detections from any camera"
- No event saved to disk

### Single Camera Detection

**Scenario**: Only one camera detects dart (other cameras miss or low confidence)

**Handling**:
```
fuse_detections(detections):
    valid_detections = filter(detections, confidence >= min_confidence)
    
    if count(valid_detections) == 1:
        detection = valid_detections[0]
        log_info("Single camera detection: camera " + detection.camera_id)
        return (detection.board_x, detection.board_y, detection.confidence, [detection.camera_id])
    
    # Continue with multi-camera fusion...
```

**Behavior**:
- Use single detection directly (no averaging)
- Log as single-camera detection
- Mark with lower confidence (inherent from single camera)
- Event created normally with num_cameras=1

### All Detections Are Outliers

**Scenario**: Multi-camera detections disagree significantly (all >50mm from median)

**Handling**:
```
reject_outliers(detections):
    median_position = compute_median(detections)
    inliers = []
    
    for each detection in detections:
        distance = euclidean_distance(detection.position, median_position)
        if distance <= outlier_threshold_mm:
            inliers.append(detection)
        else:
            log_warning("Rejecting outlier from camera " + detection.camera_id + 
                       ": distance " + distance + " mm from median")
    
    if count(inliers) == 0:
        log_warning("All detections rejected as outliers")
        log_warning("Median position: " + median_position)
        for each detection in detections:
            log_warning("  Camera " + detection.camera_id + ": " + 
                       detection.position + ", distance " + distance)
    
    return inliers
```

**Behavior**:
- Return empty inlier list
- fuse_detections() returns null
- Log warning with all detection positions and distances
- No event created
- Indicates potential calibration issue or multiple darts

### Dart on Wire (Sector Boundary)

**Scenario**: Dart lands on wire between sectors

**Handling**:
```
determine_sector(theta_rad):
    theta_deg = radians_to_degrees(theta_rad)
    theta_deg = apply_offset_and_rotation(theta_deg)
    
    wedge_index = floor(theta_deg / wedge_width_deg)
    position_in_wedge = theta_deg mod wedge_width_deg
    
    # Check if on wire (last 2° of wedge)
    if position_in_wedge >= sector_width_deg:
        log_debug("Dart on wire at angle " + theta_deg)
        # Assign to next sector (entering wedge)
        wedge_index = (wedge_index + 1) mod 20
    
    sector = sector_order[wedge_index]
    return sector
```

**Behavior**:
- Assign to adjacent sector (next in clockwise direction)
- Log debug message
- Event created normally
- Alternative: Could return null and treat as miss (configurable)

### Out of Bounds Detection

**Scenario**: Dart lands outside scoring area (r ≥ 170mm)

**Handling**:
```
determine_ring(radius):
    if radius >= double_outer_radius:
        return ("out_of_bounds", 0, 0)
    
    # ... other rings ...
```

**Behavior**:
- Ring = "out_of_bounds"
- Score = 0
- Sector = null
- Event created normally
- Log as miss

### Invalid Polar Conversion (Origin)

**Scenario**: Dart detected at exact board center (0, 0)

**Handling**:
```
cartesian_to_polar(x, y):
    r = sqrt(x² + y²)
    
    if r == 0:
        theta = 0  # Arbitrary angle for origin
    else:
        theta = atan2(y, x)
        if theta < 0:
            theta = theta + 2π
    
    return (r, theta)
```

**Behavior**:
- Set θ = 0 (arbitrary, doesn't matter for r=0)
- Ring detector will classify as bull (r < 6.35mm)
- Score = 50
- Event created normally

### Confidence Below Threshold

**Scenario**: Detection confidence < 0.3 (configurable minimum)

**Handling**:
```
fuse_detections(detections):
    valid_detections = filter(detections, confidence >= min_confidence)
    
    if count(valid_detections) == 0:
        log_warning("No detections meet minimum confidence threshold")
        return null
    
    # Continue with valid detections...
```

**Behavior**:
- Filter out low-confidence detections
- Log warning if all detections filtered
- Return null if no valid detections remain
- Prevents unreliable detections from affecting score

### Thread Safety

**Scenario**: Multiple threads calling fusion/scoring simultaneously (future API)

**Design Approach**:
- All fusion/scoring classes are stateless (no mutable shared state)
- Only store immutable configuration values
- All operations work on local variables passed as parameters
- Thread-safe by design without explicit locking

**Behavior**:
- Safe for concurrent use without locks
- Each call operates on independent data
- No race conditions or shared mutable state

## Testing Strategy

### Dual Testing Approach

The fusion and scoring system requires both unit tests and property-based tests for comprehensive validation:

**Unit Tests**: Verify specific examples, edge cases, and error conditions
- Specific fusion scenarios (single camera, multi-camera, outliers)
- Known control points (T20, D20, bull) with expected scores
- Error handling (no detections, all outliers, low confidence)
- Integration with coordinate mapping
- JSON serialization/deserialization

**Property Tests**: Verify universal properties across all inputs
- Mathematical properties (polar conversion, weighted average)
- Ring/sector determination for all possible coordinates
- Score calculation for all ring/sector combinations
- Event structure completeness
- Comprehensive input coverage through randomization

Both approaches are complementary and necessary for ensuring correctness.

### Property-Based Testing Configuration

**Library**: Use `hypothesis` for Python property-based testing

**Installation**:
```bash
pip install hypothesis
```

**Configuration**:
- Minimum 100 iterations per property test (due to randomization)
- Each property test references its design document property
- Tag format: `# Feature: step-7-multi-camera-fusion, Property N: [property text]`

**Example Property Test**:
```python
from hypothesis import given, strategies as st
import numpy as np

@given(
    radius=st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False)
)
def test_ring_determination_correctness(radius):
    """
    Feature: step-7-multi-camera-fusion, Property 1: Ring Determination Correctness
    
    For any radius value, the ring detector should correctly classify it into
    exactly one ring category according to specified boundaries.
    """
    ring_detector = RingDetector(config)
    ring_name, multiplier, base_score = ring_detector.determine_ring(radius)
    
    # Verify correct classification
    if radius < 6.35:
        assert ring_name == "bull"
        assert multiplier == 0
        assert base_score == 50
    elif radius < 15.9:
        assert ring_name == "single_bull"
        assert multiplier == 0
        assert base_score == 25
    elif 99 <= radius < 107:
        assert ring_name == "triple"
        assert multiplier == 3
        assert base_score == 0
    elif 162 <= radius < 170:
        assert ring_name == "double"
        assert multiplier == 2
        assert base_score == 0
    elif radius >= 170:
        assert ring_name == "out_of_bounds"
        assert multiplier == 0
        assert base_score == 0
    else:
        assert ring_name == "single"
        assert multiplier == 1
        assert base_score == 0


@given(
    x=st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False),
    y=st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False)
)
def test_polar_coordinate_round_trip(x, y):
    """
    Feature: step-7-multi-camera-fusion, Property 2: Polar Coordinate Round Trip
    
    For any board coordinate (x, y), converting to polar then back to Cartesian
    should return approximately the same point.
    """
    converter = PolarConverter(config)
    
    # Forward: Cartesian → Polar
    r, theta = converter.cartesian_to_polar(x, y)
    
    # Inverse: Polar → Cartesian
    x_back, y_back = converter.polar_to_cartesian(r, theta)
    
    # Verify round trip within tolerance
    assert abs(x_back - x) < 0.01, f"X error: {abs(x_back - x):.6f} mm"
    assert abs(y_back - y) < 0.01, f"Y error: {abs(y_back - y):.6f} mm"
```

### Unit Test Coverage

**Test Files**:
```
tests/
├── test_coordinate_fusion.py      # CoordinateFusion class tests
├── test_polar_converter.py        # PolarConverter class tests
├── test_ring_detector.py          # RingDetector class tests
├── test_sector_detector.py        # SectorDetector class tests
├── test_score_calculator.py       # ScoreCalculator class tests
├── test_dart_hit_event.py         # DartHitEvent dataclass tests
└── test_fusion_integration.py     # End-to-end integration tests
```

**Key Test Scenarios**:

1. **CoordinateFusion Tests**:
   - Single camera detection (use directly)
   - Two camera fusion (weighted average)
   - Three camera fusion (weighted average)
   - Outlier rejection (discard >50mm from median)
   - All outliers (return None)
   - Low confidence filtering
   - Empty detection list

2. **PolarConverter Tests**:
   - Origin (0, 0) → (0, 0)
   - Positive X axis (100, 0) → (100, 0°)
   - Positive Y axis (0, 100) → (100, 90°)
   - Negative coordinates
   - Angle normalization [0, 2π)
   - Round trip accuracy

3. **RingDetector Tests**:
   - Bull (r=3mm) → ("bull", 0, 50)
   - Single bull (r=10mm) → ("single_bull", 0, 25)
   - Triple (r=103mm) → ("triple", 3, 0)
   - Double (r=166mm) → ("double", 2, 0)
   - Single (r=50mm) → ("single", 1, 0)
   - Out of bounds (r=180mm) → ("out_of_bounds", 0, 0)
   - Boundary cases (exactly at thresholds)

4. **SectorDetector Tests**:
   - Sector 20 at top (θ=90°)
   - All 20 sectors
   - Sector boundaries
   - Wire detection
   - Angle wraparound (359° → 0°)
   - Sector offset application

5. **ScoreCalculator Tests**:
   - T20 (triple 20) → 60
   - D20 (double 20) → 40
   - S20 (single 20) → 20
   - Bull → 50
   - Single bull → 25
   - Out of bounds → 0
   - Complete event creation

6. **DartHitEvent Tests**:
   - JSON serialization round trip
   - All fields populated
   - Timestamp format (ISO 8601)
   - from_dict() / to_dict() consistency

7. **Integration Tests**:
   - Full pipeline (detections → event)
   - Multi-camera fusion with real-like data
   - Known control points (T20, D20, bull)
   - Error handling (no detections, outliers)

### Test Data

**Synthetic Test Data**:
- Generated detection sets with known positions and confidences
- Known control points (T20, D20, bull, etc.) with expected scores
- Edge cases (origin, boundaries, outliers)

**Real Test Data** (from Step 6 verification):
- Control point images with ground truth board coordinates
- Multi-camera detections from actual throws
- Outlier scenarios from failed detections

**Test Data Location**:
```
tests/data/
├── fusion/
│   ├── single_camera.json       # Single camera detection examples
│   ├── multi_camera.json        # Multi-camera fusion examples
│   ├── outliers.json            # Outlier rejection examples
│   └── control_points.json      # Known scores (T20, D20, bull, etc.)
└── events/
    ├── example_t20.json         # Example T20 event
    ├── example_bull.json        # Example bull event
    └── example_miss.json        # Example miss event
```



## Performance Considerations

### Fusion Latency Target

**Requirement**: Complete fusion and scoring in <10ms for real-time operation

**Measured Performance** (estimated):
- Coordinate fusion: ~0.1-0.5ms (simple arithmetic)
- Polar conversion: ~0.01ms (sqrt + atan2)
- Ring detection: ~0.01ms (range checks)
- Sector detection: ~0.05ms (angle calculation)
- Score calculation: ~0.01ms (multiplication)
- Event creation: ~0.1ms (object construction)
- **Total: ~0.3-0.7ms** ✓ (well under 10ms target)

**Bottleneck**: None - all operations are simple arithmetic

### Memory Footprint

**Per-Event Memory**:
- DartHitEvent object: ~500 bytes (Python object overhead + fields)
- Per-camera detections (3 cameras): ~300 bytes
- Image paths (3 strings): ~200 bytes
- **Total per event: ~1KB**

**Memory Usage**:
- 1000 events in memory: ~1MB
- Negligible compared to image data (1.44MB per frame × 3 cameras)

**No optimization needed** - memory usage is minimal

### JSON Serialization Performance

**Target**: Serialize event to JSON in <1ms

**Measured Performance** (estimated):
- `to_dict()`: ~0.1ms (field access)
- `json.dumps()`: ~0.2-0.5ms (serialization)
- File write: ~1-5ms (I/O dependent)
- **Total: ~1-6ms** ✓

**Optimization**: Use `json.dumps()` without indentation for faster serialization (if needed)

### Batch Processing

**Current Design**: Process one throw at a time (real-time)

**Future Optimization** (if needed):
- Batch process multiple throws for offline analysis
- Vectorize fusion calculations using NumPy
- Parallel processing for multiple events

**Not needed for current requirements** - single-throw processing is fast enough

## Integration with Existing System

### Main Loop Integration

The fusion system integrates after coordinate mapping in the main detection loop:

```
main():
    # Initialize components
    score_calculator = ScoreCalculator(config)
    coordinate_mapper = CoordinateMapper(config)
    # ... other components ...
    
    # Main loop
    while true:
        # ... existing motion detection ...
        
        if motion_state == "dart_detected":
            detections = []
            image_paths = {}
            
            # Collect detections from all cameras
            for each camera_id:
                pre_frame = get_pre_impact_frame(camera_id)
                post_frame = get_post_impact_frame(camera_id)
                
                # Detect dart tip in pixels
                tip_x_px, tip_y_px, confidence = detect_dart(pre_frame, post_frame)
                
                if tip detected and camera_is_calibrated(camera_id):
                    # Transform to board coordinates (Step 6)
                    board_x, board_y = coordinate_mapper.map_to_board(camera_id, tip_x_px, tip_y_px)
                    
                    if board coordinates valid:
                        detections.append({
                            camera_id: camera_id,
                            pixel: (tip_x_px, tip_y_px),
                            board: (board_x, board_y),
                            confidence: confidence
                        })
                    
                    # Save annotated image
                    save_annotated_image(camera_id, post_frame, timestamp)
                    image_paths[camera_id] = image_path
            
            # NEW: Fuse detections and derive score
            if detections not empty:
                dart_hit_event = score_calculator.process_detections(detections, image_paths)
                
                if dart_hit_event not null:
                    # Log score
                    log_info("Dart scored: " + event.score.total + 
                            " (" + event.score.base + " × " + event.score.multiplier + ")")
                    log_info("Ring: " + event.score.ring + ", Sector: " + event.score.sector)
                    log_info("Position: (" + event.board_x + ", " + event.board_y + ") mm, " +
                            "r=" + event.radius + " mm, θ=" + event.angle_deg + "°")
                    log_info("Cameras used: " + event.cameras_used + " (" + event.num_cameras + "/3)")
                    log_info("Confidence: " + event.fusion_confidence)
                    
                    # Save event to JSON
                    save_event_json(event, timestamp)
                else:
                    log_warning("No valid detections after fusion")
            else:
                log_warning("No detections from any camera")
            
            # Reset state
            motion_state = "idle"
```

### Configuration File Updates

Add fusion and board configuration to `config.toml`:

```toml
# NEW: Multi-camera fusion configuration
[fusion]
outlier_threshold_mm = 50.0
min_confidence = 0.3

# NEW: Dartboard dimensions
[board]
radius_mm = 170.0
bull_radius_mm = 6.35
single_bull_radius_mm = 15.9
triple_inner_mm = 99.0
triple_outer_mm = 107.0
double_inner_mm = 162.0
double_outer_mm = 170.0

[board.sectors]
sector_order = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
sector_width_deg = 18.0
wire_gap_deg = 2.0
sector_offset_deg = 0.0
```

### Logging Output Example

```
2024-01-15 14:32:18 INFO [main] Motion detected
2024-01-15 14:32:18 INFO [main] Dart detected - running detection
2024-01-15 14:32:18 INFO [dart_detector] Camera 0: tip detected at (412.3, 287.5) px, confidence 0.85
2024-01-15 14:32:18 INFO [coordinate_mapper] Camera 0: pixel=(412.3, 287.5) → board=(1.8, 99.2) mm
2024-01-15 14:32:18 INFO [dart_detector] Camera 1: tip detected at (398.7, 301.2) px, confidence 0.78
2024-01-15 14:32:18 INFO [coordinate_mapper] Camera 1: pixel=(398.7, 301.2) → board=(2.5, 98.5) mm
2024-01-15 14:32:18 INFO [dart_detector] Camera 2: tip detected at (425.1, 295.8) px, confidence 0.83
2024-01-15 14:32:18 INFO [coordinate_mapper] Camera 2: pixel=(425.1, 295.8) → board=(2.6, 98.4) mm
2024-01-15 14:32:18 INFO [coordinate_fusion] Multi-camera fusion: 3 cameras
2024-01-15 14:32:18 INFO [coordinate_fusion] Fused position: (2.3, 98.7) mm, confidence: 0.82, cameras: [0, 1, 2]
2024-01-15 14:32:18 INFO [main] Dart scored: 60 (20 × 3)
2024-01-15 14:32:18 INFO [main] Ring: triple, Sector: 20
2024-01-15 14:32:18 INFO [main] Position: (2.3, 98.7) mm, r=98.7 mm, θ=88.6°
2024-01-15 14:32:18 INFO [main] Cameras used: [0, 1, 2] (3/3)
2024-01-15 14:32:18 INFO [main] Confidence: 0.82
2024-01-15 14:32:18 INFO [main] Event saved: data/throws/event_20240115_143218.json
```

## Development and Debugging Tools

### Fusion Visualization

**Purpose**: Visualize multi-camera detections and fusion result on board diagram

**Features**:
- Draw dartboard rings and sector lines
- Show per-camera detections (different colors)
- Show fused position (large marker)
- Annotate with score information

**Algorithm**:
```
visualize_fusion(dart_hit_event, output_path):
    create_figure(10x10)
    
    # Draw dartboard rings
    for each ring (170mm, 162mm, 107mm, 99mm, 15.9mm, 6.35mm):
        draw_circle(center=(0,0), radius=ring, color=ring_color)
    
    # Draw sector lines (every 18°)
    for i in 0 to 19:
        angle = 90° - i × 18°  # Start at top, go clockwise
        draw_line(from=(0,0), to=(170mm × cos(angle), 170mm × sin(angle)))
    
    # Draw per-camera detections
    for each detection in event.detections:
        color = camera_colors[detection.camera_id]
        plot_point(detection.board_x, detection.board_y, color=color, size=8)
    
    # Draw fused position
    plot_point(event.board_x, event.board_y, color=red, marker=star, size=20)
    
    # Annotate score
    text_annotation(event.board_x + 10, event.board_y + 10,
                   text=event.score.total + "\n" + event.score.ring)
    
    save_figure(output_path)
```

### Diagnostic Logging

**Purpose**: Detailed logging for fusion troubleshooting

**Log Levels**:
- INFO: Fusion results, scores, camera usage
- WARNING: Outliers rejected, low confidence, no detections
- DEBUG: Detailed fusion calculations, intermediate values

**Example Debug Output**:
```
2024-01-15 14:32:18 DEBUG [coordinate_fusion] Input detections:
2024-01-15 14:32:18 DEBUG [coordinate_fusion]   Camera 0: (1.8, 99.2) mm, confidence 0.85
2024-01-15 14:32:18 DEBUG [coordinate_fusion]   Camera 1: (2.5, 98.5) mm, confidence 0.78
2024-01-15 14:32:18 DEBUG [coordinate_fusion]   Camera 2: (2.6, 98.4) mm, confidence 0.83
2024-01-15 14:32:18 DEBUG [coordinate_fusion] Median position: (2.5, 98.5) mm
2024-01-15 14:32:18 DEBUG [coordinate_fusion] Distances from median:
2024-01-15 14:32:18 DEBUG [coordinate_fusion]   Camera 0: 0.8 mm (inlier)
2024-01-15 14:32:18 DEBUG [coordinate_fusion]   Camera 1: 0.0 mm (inlier)
2024-01-15 14:32:18 DEBUG [coordinate_fusion]   Camera 2: 0.1 mm (inlier)
2024-01-15 14:32:18 DEBUG [coordinate_fusion] Weighted average: (2.3, 98.7) mm
2024-01-15 14:32:18 DEBUG [polar_converter] Cartesian (2.3, 98.7) → Polar (98.7, 1.547 rad)
2024-01-15 14:32:18 DEBUG [ring_detector] Radius 98.7 mm → single ring (multiplier 1)
2024-01-15 14:32:18 DEBUG [sector_detector] Angle 88.6° → sector 20
2024-01-15 14:32:18 DEBUG [score_calculator] Score: 20 × 1 = 20
```

### Event Replay Tool

**Purpose**: Replay saved events for testing and debugging

**Usage**:
```bash
python tools/replay_event.py data/throws/event_20240115_143218.json
```

**Features**:
- Load event from JSON
- Display all event data
- Show fusion visualization
- Recompute score (verify consistency)
- Compare with expected score (if ground truth available)

## Summary

This design document specifies a complete multi-camera fusion and scoring system that:

1. **Combines multi-camera detections** using confidence-weighted averaging and outlier rejection
2. **Converts to polar coordinates** for ring and sector determination
3. **Determines ring and sector** based on standard dartboard geometry
4. **Calculates final score** with proper multipliers
5. **Creates complete DartHitEvent** with all detection, fusion, and scoring information
6. **Handles errors gracefully** with appropriate fallbacks and logging
7. **Performs efficiently** with <1ms fusion and scoring time
8. **Integrates seamlessly** with existing detection and coordinate mapping systems

The system enables complete dart scoring from raw camera detections to game-relevant scores, ready for downstream systems (logging, API, UI) in Step 8-10.

