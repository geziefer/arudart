# Step 6: Coordinate Mapping - Design Document

## Overview

This design document specifies the architecture for transforming camera pixel coordinates to board-plane coordinates in millimeters using spiderweb-based calibration. The system uses the dartboard's natural wire structure—bull center, ring edges, and radial wires—as calibration reference points, eliminating the need for external ARUCO markers.

Each of the 3 cameras has its own homography matrix computed from features visible in that camera's perspective. The bull center serves as a common anchor point (0, 0), while wire intersections in each camera's "good view" region provide additional correspondence points for robust homography computation.

**Key Design Principles**:
- Per-camera calibration to handle perspective distortion
- Focus on reliably detectable features (bull, near-sector wires)
- Continuous calibration with lightweight validation between throws
- Graceful degradation when features are not detected
- Thread-safe coordinate transformation for multi-camera operation

## Architecture

### Module Structure

```
calibration/
├── calibrate_intrinsic.py         # Intrinsic calibration script (chessboard)
├── calibrate_spiderweb.py         # Spiderweb-based extrinsic calibration script
├── verify_calibration.py          # Verification script with control points
├── intrinsic_cam0.json            # Camera matrix & distortion (cam0)
├── intrinsic_cam1.json            # Camera matrix & distortion (cam1)
├── intrinsic_cam2.json            # Camera matrix & distortion (cam2)
├── homography_cam0.json           # Homography matrix (cam0)
├── homography_cam1.json           # Homography matrix (cam1)
└── homography_cam2.json           # Homography matrix (cam2)

src/calibration/
├── __init__.py
├── coordinate_mapper.py           # CoordinateMapper class (main interface)
├── intrinsic_calibrator.py        # IntrinsicCalibrator class (chessboard)
├── feature_detector.py            # FeatureDetector class (spiderweb detection)
├── feature_matcher.py             # FeatureMatcher class (feature-to-board mapping)
├── homography_calculator.py       # HomographyCalculator class
└── calibration_manager.py         # CalibrationManager class (continuous calibration)
```

### Component Relationships

```
CalibrationManager (orchestrates calibration lifecycle)
├── manages state: ready, calibrating, error
├── triggers full calibration on startup
├── runs lightweight validation between throws
└── triggers recalibration on drift detection

FeatureDetector (detects board features in camera image)
├── detects bull center using Hough circles
├── detects ring edges using edge detection + ellipse fitting
├── detects radial wires using Hough lines
└── extracts wire-ring intersections

FeatureMatcher (maps detected features to board coordinates)
├── assigns bull center to (0, 0)
├── assigns ring edge points to known radii
├── assigns wire intersections to known angles
└── uses RANSAC to reject outliers

HomographyCalculator (computes transformation matrix)
├── takes matched point pairs (pixel, board)
├── computes homography using cv2.findHomography
├── validates reprojection error
└── saves to JSON

CoordinateMapper (transforms coordinates)
├── loads intrinsic and homography from JSON
├── undistorts pixels using camera matrix
├── applies homography to get board coordinates
└── thread-safe for concurrent access
```

### Data Flow

```
Camera Frame (800×600 BGR)
    ↓
[FeatureDetector.detect()]
    ↓
Detected Features:
  - bull_center: (u, v) pixel
  - ring_edges: list of (u, v) points on double/triple rings
  - wire_intersections: list of (u, v, ring_type, sector_estimate)
    ↓
[FeatureMatcher.match()]
    ↓
Matched Point Pairs:
  - [(pixel_1, board_1), (pixel_2, board_2), ...]
  - Each pair: ((u, v), (x_mm, y_mm))
    ↓
[HomographyCalculator.compute()]
    ↓
Homography Matrix H (3×3)
    ↓ (saved to JSON)
[CoordinateMapper.map_to_board()]
    ↓
1. Undistort pixel (u, v) using camera matrix K and distortion D
2. Apply homography H to get board coordinates (x, y)
    ↓
Board Coordinates (x, y) in millimeters
```

## Components and Interfaces

### 1. FeatureDetector Class

**Purpose**: Detect dartboard features (bull, rings, radial wires) in a camera image.

**Interface**:
```python
class FeatureDetector:
    def __init__(self, config: dict)
    
    def detect(self, image: np.ndarray) -> FeatureDetectionResult
    
    def detect_bull_center(self, image: np.ndarray) -> tuple[float, float] | None
    
    def detect_ring_edges(self, image: np.ndarray, 
                          bull_center: tuple[float, float]) -> dict[str, list[tuple]]
    
    def detect_radial_wires(self, image: np.ndarray,
                            bull_center: tuple[float, float]) -> list[tuple]
    
    def find_wire_intersections(self, ring_edges: dict, 
                                radial_wires: list) -> list[WireIntersection]
```

**Algorithm - Bull Center Detection**:
```
detect_bull_center(image):
    1. Convert to grayscale
    2. Apply Gaussian blur (kernel=5)
    3. Use HoughCircles to find circles with radius 10-30 pixels
       (bull appears as small dark circle)
    4. If multiple circles found, select by:
       - Closest to image center (bull should be roughly centered)
       - Highest accumulator value (strongest circle)
    5. Refine center using contour moments or template matching
    6. Return (u, v) or None if not found
```

**Algorithm - Ring Edge Detection**:
```
detect_ring_edges(image, bull_center):
    1. Convert to grayscale
    2. Apply Canny edge detection (thresholds: 50, 150)
    3. For each ring (double at ~170mm, triple at ~107mm):
       a. Estimate expected radius in pixels based on bull size
       b. Create annular mask around expected radius (±20 pixels)
       c. Extract edge points within mask
       d. Fit ellipse to edge points using cv2.fitEllipse
       e. Sample points along fitted ellipse
    4. Return dict with 'double_ring' and 'triple_ring' point lists
```

**Algorithm - Radial Wire Detection**:
```
detect_radial_wires(image, bull_center):
    1. Convert to grayscale
    2. Apply Canny edge detection
    3. Use HoughLinesP to detect line segments
    4. Filter lines that:
       - Pass near bull center (within 20 pixels)
       - Have length > 50 pixels
       - Are roughly radial (angle from bull matches line angle)
    5. Cluster lines by angle (18° sectors)
    6. For each cluster, select strongest line
    7. Return list of (rho, theta, endpoint1, endpoint2)
```

**Algorithm - Wire Intersection Finding**:
```
find_wire_intersections(ring_edges, radial_wires):
    intersections = []
    for wire in radial_wires:
        for ring_type in ['double_ring', 'triple_ring']:
            # Find where wire crosses ring
            intersection = line_ellipse_intersection(wire, ring_edges[ring_type])
            if intersection:
                # Estimate sector based on wire angle
                sector = estimate_sector_from_angle(wire.angle)
                intersections.append(WireIntersection(
                    pixel=intersection,
                    ring_type=ring_type,
                    sector_estimate=sector
                ))
    return intersections
```

### 2. FeatureMatcher Class

**Purpose**: Map detected features to known board coordinates.

**Interface**:
```python
class FeatureMatcher:
    def __init__(self, config: dict)
    
    def match(self, detection_result: FeatureDetectionResult) -> list[PointPair]
    
    def identify_sector_20(self, radial_wires: list, 
                           image_orientation: str) -> int | None
    
    def assign_wire_sectors(self, radial_wires: list, 
                            sector_20_index: int) -> dict[int, int]
```

**Algorithm - Feature Matching**:
```
match(detection_result):
    point_pairs = []
    
    # 1. Bull center → (0, 0)
    if detection_result.bull_center:
        point_pairs.append((detection_result.bull_center, (0, 0)))
    
    # 2. Identify sector 20 (top of board)
    sector_20_wire = identify_sector_20(detection_result.radial_wires)
    
    # 3. Assign sectors to detected wires
    wire_sectors = assign_wire_sectors(detection_result.radial_wires, sector_20_wire)
    
    # 4. For each wire intersection, compute board coordinates
    for intersection in detection_result.wire_intersections:
        wire_idx = intersection.wire_index
        if wire_idx in wire_sectors:
            sector = wire_sectors[wire_idx]
            angle = sector_to_angle(sector)  # 20 at 0°, clockwise
            radius = 170 if intersection.ring_type == 'double_ring' else 107
            
            # Board coordinates
            x = radius * cos(angle)
            y = radius * sin(angle)
            
            point_pairs.append((intersection.pixel, (x, y)))
    
    # 5. Add ring edge points (sampled along ellipse)
    for ring_type, radius in [('double_ring', 170), ('triple_ring', 107)]:
        for pixel_point in detection_result.ring_edges[ring_type]:
            # Estimate angle from bull center
            angle = atan2(pixel_point[1] - bull_v, pixel_point[0] - bull_u)
            x = radius * cos(angle)
            y = radius * sin(angle)
            point_pairs.append((pixel_point, (x, y)))
    
    return point_pairs
```

**Algorithm - Sector 20 Identification**:
```
identify_sector_20(radial_wires, image_orientation='top'):
    # Sector 20 is at top of board (12 o'clock)
    # Find wire closest to vertical (pointing up from bull)
    
    best_wire = None
    best_score = -inf
    
    for i, wire in enumerate(radial_wires):
        # Wire angle relative to vertical
        angle_from_vertical = abs(wire.angle - 90°)  # 90° = pointing up
        
        # Score: prefer wires pointing up
        score = -angle_from_vertical
        
        if score > best_score:
            best_score = score
            best_wire = i
    
    return best_wire
```

### 3. HomographyCalculator Class

**Purpose**: Compute homography matrix from matched point pairs.

**Interface**:
```python
class HomographyCalculator:
    def __init__(self, config: dict)
    
    def compute(self, point_pairs: list[PointPair]) -> tuple[np.ndarray, dict] | None
    
    def verify(self, homography: np.ndarray, 
               point_pairs: list[PointPair]) -> float
    
    def save(self, camera_id: int, homography: np.ndarray, 
             metadata: dict, output_dir: str)
    
    def load(self, camera_id: int, calibration_dir: str) -> np.ndarray | None
```

**Algorithm - Homography Computation**:
```
compute(point_pairs):
    if len(point_pairs) < 4:
        return None  # Need at least 4 points
    
    # Separate into image and board point arrays
    image_points = np.array([p[0] for p in point_pairs])
    board_points = np.array([p[1] for p in point_pairs])
    
    # Compute homography with RANSAC
    H, mask = cv2.findHomography(
        image_points, 
        board_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=5.0,  # 5 pixel threshold
        confidence=0.999
    )
    
    if H is None:
        return None
    
    # Verify homography quality
    error = verify(H, point_pairs)
    if error > 5.0:  # 5mm average error threshold
        log.warning(f"High reprojection error: {error:.2f}mm")
    
    metadata = {
        'num_points': len(point_pairs),
        'num_inliers': np.sum(mask),
        'reprojection_error_mm': error,
        'timestamp': datetime.now().isoformat()
    }
    
    return (H, metadata)
```

### 4. CoordinateMapper Class

**Purpose**: Main interface for coordinate transformation. Thread-safe.

**Interface**:
```python
class CoordinateMapper:
    def __init__(self, config: dict, calibration_dir: str = "calibration")
    
    def map_to_board(self, camera_id: int, u: float, v: float) -> tuple[float, float] | None
    
    def map_to_image(self, camera_id: int, x: float, y: float) -> tuple[float, float] | None
    
    def is_calibrated(self, camera_id: int) -> bool
    
    def reload_calibration(self, camera_id: int | None = None)
```

**Algorithm - Coordinate Transformation**:
```
map_to_board(camera_id, u, v):
    with self._lock:
        if camera_id not in self._homographies:
            return None
        K = self._camera_matrices[camera_id]
        D = self._distortion_coeffs[camera_id]
        H = self._homographies[camera_id]
    
    # 1. Undistort pixel
    point = np.array([[[u, v]]], dtype=np.float32)
    undistorted = cv2.undistortPoints(point, K, D, P=K)
    u_undist, v_undist = undistorted[0, 0]
    
    # 2. Apply homography
    point_h = np.array([[u_undist, v_undist, 1.0]])
    result = H @ point_h.T
    x = result[0, 0] / result[2, 0]
    y = result[1, 0] / result[2, 0]
    
    # 3. Bounds check
    radius = sqrt(x*x + y*y)
    if radius > 200:  # Outside board
        return None
    
    return (x, y)
```

### 5. CalibrationManager Class

**Purpose**: Orchestrate calibration lifecycle with continuous validation.

**Interface**:
```python
class CalibrationManager:
    def __init__(self, config: dict, 
                 feature_detector: FeatureDetector,
                 feature_matcher: FeatureMatcher,
                 homography_calculator: HomographyCalculator,
                 coordinate_mapper: CoordinateMapper)
    
    def get_status(self) -> CalibrationStatus
    
    def run_full_calibration(self, camera_id: int, image: np.ndarray) -> bool
    
    def run_lightweight_validation(self, camera_id: int, image: np.ndarray) -> float
    
    def check_and_recalibrate(self, camera_id: int, image: np.ndarray) -> bool
```

**State Machine**:
```
States: ready, calibrating, error

Transitions:
  ready → calibrating: on startup or drift detected
  calibrating → ready: calibration successful
  calibrating → error: calibration failed 3 times
  error → calibrating: manual retry triggered
```

**Algorithm - Lightweight Validation**:
```
run_lightweight_validation(camera_id, image):
    # Quick check: detect bull center only
    bull_center = feature_detector.detect_bull_center(image)
    
    if bull_center is None:
        return inf  # Can't validate
    
    # Transform bull center to board coordinates
    board_x, board_y = coordinate_mapper.map_to_board(camera_id, *bull_center)
    
    # Bull should map to (0, 0)
    drift = sqrt(board_x**2 + board_y**2)
    
    return drift  # mm
```

**Algorithm - Check and Recalibrate**:
```
check_and_recalibrate(camera_id, image):
    drift = run_lightweight_validation(camera_id, image)
    
    if drift > DRIFT_THRESHOLD_MM:  # 3mm
        log.info(f"Drift detected: {drift:.1f}mm, triggering recalibration")
        self._state = 'calibrating'
        success = run_full_calibration(camera_id, image)
        self._state = 'ready' if success else 'error'
        return success
    
    return True  # No recalibration needed
```

## Data Models

### FeatureDetectionResult

```python
@dataclass
class FeatureDetectionResult:
    bull_center: tuple[float, float] | None
    ring_edges: dict[str, list[tuple[float, float]]]  # 'double_ring', 'triple_ring'
    radial_wires: list[RadialWire]
    wire_intersections: list[WireIntersection]
    detection_time_ms: float
    
@dataclass
class RadialWire:
    angle: float  # degrees from vertical
    endpoints: tuple[tuple[float, float], tuple[float, float]]
    confidence: float

@dataclass
class WireIntersection:
    pixel: tuple[float, float]
    ring_type: str  # 'double_ring' or 'triple_ring'
    wire_index: int
    sector_estimate: int | None
```

### CalibrationStatus

```python
@dataclass
class CalibrationStatus:
    state: str  # 'ready', 'calibrating', 'error'
    last_calibration: datetime | None
    last_validation: datetime | None
    drift_mm: float | None
    cameras_calibrated: list[int]
    error_message: str | None
```

### Configuration Schema (config.toml additions)

```toml
[calibration]
calibration_dir = "calibration"
drift_threshold_mm = 3.0
max_calibration_failures = 3

[calibration.feature_detection]
bull_min_radius_px = 10
bull_max_radius_px = 30
canny_threshold_low = 50
canny_threshold_high = 150
hough_line_threshold = 50
min_wire_length_px = 50

[calibration.homography]
ransac_threshold_px = 5.0
ransac_confidence = 0.999
max_reprojection_error_mm = 5.0

[calibration.chessboard]
inner_corners = [9, 6]
square_size_mm = 25.0
```

### Calibration File Formats

**intrinsic_cam{N}.json**:
```json
{
  "camera_id": 0,
  "camera_matrix": [[fx, 0, cx], [0, fy, cy], [0, 0, 1]],
  "distortion_coeffs": [k1, k2, p1, p2, k3],
  "reprojection_error": 0.42,
  "image_size": [800, 600],
  "calibration_date": "2024-01-15T10:30:00"
}
```

**homography_cam{N}.json**:
```json
{
  "camera_id": 0,
  "homography": [[h11, h12, h13], [h21, h22, h23], [h31, h32, h33]],
  "num_points": 12,
  "num_inliers": 10,
  "reprojection_error_mm": 3.2,
  "features_detected": {
    "bull_center": true,
    "double_ring_points": 8,
    "triple_ring_points": 6,
    "wire_intersections": 5
  },
  "calibration_date": "2024-01-15T10:35:00"
}
```



## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Based on the prework analysis, the following properties have been consolidated to eliminate redundancy:

### Property 1: Bull Center Maps to Origin

*For any* detected bull center pixel coordinate (u, v), when matched by the Feature_Matcher, the resulting board coordinate should be (0, 0).

**Validates: Requirements 2.1**

### Property 2: Ring Points Map to Correct Radius

*For any* point detected on the double ring edge, the matched board coordinate should have radius 170mm (±1mm). *For any* point detected on the triple ring edge, the matched board coordinate should have radius 107mm (±1mm).

**Validates: Requirements 2.2, 2.3**

### Property 3: Homography Round-Trip Consistency

*For any* board coordinate (x, y) within board bounds (radius ≤ 170mm), transforming to image coordinates then back to board coordinates should return approximately the same point: `map_to_board(camera_id, *map_to_image(camera_id, x, y)) ≈ (x, y)` within 1mm tolerance.

**Validates: Requirements 4.4, 4.7**

### Property 4: Calibration Serialization Round-Trip

*For any* valid calibration data (camera matrix, distortion coefficients, or homography matrix), saving to JSON then loading should produce numerically equivalent matrices within floating-point tolerance of 1e-6.

**Validates: Requirements 3.5, 7.4**

### Property 5: Bounds Checking Returns None for Out-of-Bounds

*For any* pixel coordinate that maps to a board position with radius > 200mm, the `map_to_board()` function should return None.

**Validates: Requirements 4.6**

### Property 6: Drift Detection Triggers Recalibration

*For any* lightweight validation result where drift exceeds 3mm, the CalibrationManager should transition to "calibrating" state and trigger full recalibration.

**Validates: Requirements 5.3**

### Property 7: State Machine Transitions Are Valid

*For any* sequence of calibration events, the CalibrationManager state should only transition through valid paths: ready → calibrating → ready, ready → calibrating → error, error → calibrating → ready. After 3 consecutive calibration failures, state should be "error".

**Validates: Requirements 6.1, 6.6**

### Property 8: Thread Safety Under Concurrent Access

*For any* concurrent calls to `map_to_board()` from multiple threads, all calls should complete without data corruption or race conditions, and each call should return consistent results.

**Validates: Requirements 4.8**

### Property 9: Reprojection Error Thresholds Met

*For any* valid intrinsic calibration, reprojection error should be < 0.5 pixels. *For any* valid homography calibration, average reprojection error should be < 5mm.

**Validates: Requirements 3.3, 7.3**

## Error Handling

### Feature Detection Failures

**Scenario**: Bull center not detected in image

**Handling**:
```
detect(image):
    bull_center = detect_bull_center(image)
    if bull_center is None:
        log.warning("Bull center not detected - check lighting and camera position")
        return FeatureDetectionResult(
            bull_center=None,
            error="BULL_NOT_DETECTED"
        )
```

**Behavior**:
- Log warning with diagnostic guidance
- Return result with error flag
- CalibrationManager handles by retrying or entering error state

### Insufficient Features for Homography

**Scenario**: Fewer than 4 point pairs matched

**Handling**:
```
compute(point_pairs):
    if len(point_pairs) < 4:
        log.error(f"Insufficient points for homography: {len(point_pairs)} < 4")
        return None
```

**Behavior**:
- Log error with point count
- Return None (calibration failed)
- CalibrationManager increments failure counter

### Degenerate Homography

**Scenario**: Homography matrix is singular or near-singular

**Handling**:
```
compute(point_pairs):
    H, mask = cv2.findHomography(...)
    
    if H is None:
        log.error("Homography computation returned None")
        return None
    
    det = np.linalg.det(H)
    if abs(det) < 1e-6:
        log.error(f"Degenerate homography: det={det}")
        return None
```

**Behavior**:
- Check determinant for singularity
- Log error with diagnostic info
- Return None if degenerate

### Missing Calibration Files

**Scenario**: JSON calibration files not found at startup

**Handling**:
```
__init__(config, calibration_dir):
    for camera_id in [0, 1, 2]:
        try:
            self._load_intrinsic(camera_id)
            self._load_homography(camera_id)
        except FileNotFoundError:
            log.warning(f"Calibration not found for camera {camera_id}")
            # Camera will not be available for mapping
```

**Behavior**:
- Log warning per camera
- Continue without that camera
- `is_calibrated(camera_id)` returns False

### Calibration Drift Detected

**Scenario**: Lightweight validation shows drift > 3mm

**Handling**:
```
check_and_recalibrate(camera_id, image):
    drift = run_lightweight_validation(camera_id, image)
    
    if drift > self.drift_threshold:
        log.info(f"Drift detected: {drift:.1f}mm > {self.drift_threshold}mm")
        self._state = 'calibrating'
        success = run_full_calibration(camera_id, image)
        
        if success:
            self._state = 'ready'
            log.info("Recalibration successful")
        else:
            self._failure_count += 1
            if self._failure_count >= 3:
                self._state = 'error'
                log.error("Calibration failed 3 times - manual intervention required")
```

**Behavior**:
- Log drift amount
- Trigger recalibration
- Track consecutive failures
- Enter error state after 3 failures

## Testing Strategy

### Dual Testing Approach

The coordinate mapping system requires both unit tests and property-based tests:

**Unit Tests**: Verify specific examples, edge cases, and error conditions
- Known calibration scenarios with expected outputs
- Error handling for missing files, invalid data
- Edge cases: empty images, degenerate configurations

**Property-Based Tests**: Verify universal properties across generated inputs
- Round-trip transformations
- Serialization consistency
- Thread safety under load
- State machine transitions

### Property-Based Testing Configuration

- **Library**: Hypothesis (Python)
- **Iterations**: Minimum 100 per property test
- **Tag format**: `# Feature: step-6-coordinate-mapping, Property N: {property_text}`

### Test Categories

**1. Feature Detection Tests**
- Synthetic dartboard images with known geometry
- Varying lighting conditions (brightness, contrast)
- Partial occlusion scenarios
- Edge cases: no board, rotated board

**2. Feature Matching Tests**
- Known point correspondences
- Outlier rejection with RANSAC
- Sector identification accuracy

**3. Homography Tests**
- Round-trip transformation accuracy
- Serialization round-trip
- Degenerate configuration handling

**4. Coordinate Mapper Tests**
- Known transformation results
- Bounds checking
- Thread safety with concurrent access
- Missing calibration handling

**5. Calibration Manager Tests**
- State machine transitions
- Drift detection and recalibration
- Failure counting and error state

### Integration Tests

- Full calibration workflow: detect → match → compute → save → load → transform
- Multi-camera calibration consistency
- Continuous calibration during simulated play session
