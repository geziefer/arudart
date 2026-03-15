# Step 6: Coordinate Mapping - Design Document

## Overview

This design document specifies the architecture for transforming camera pixel coordinates to board-plane coordinates in millimeters using **manual control point calibration**. The system uses user-clicked points at 17 known wire-wire intersection positions to compute a homography matrix for each camera, similar to professional systems like Autodarts.

Each of the 3 cameras has its own homography matrix computed from 17 manually clicked control points (bull center + 8 sector boundaries x 2 rings). The system projects the complete dartboard geometry (spiderweb overlay) through the homography for visual validation. After finishing each camera, the spiderweb overlay is automatically displayed for review and saved as a reference image.

**Key Design Principles**:
- **Manual control points as primary calibration method** (accurate, simple, proven)
- Per-camera calibration to handle perspective distortion
- Visual feedback via spiderweb overlay projection
- Interactive refinement with point adjustment
- Automatic feature detection as optional enhancement (future)
- Thread-safe coordinate transformation for multi-camera operation

**Design Rationale**:
After analyzing commercial systems (Autodarts) and testing automatic feature detection, we determined that manual control point calibration is:
1. **More accurate**: Human clicking ±2-3px vs automatic detection ±10-20px
2. **More reliable**: Works from any camera angle, no detection failures
3. **Faster to implement**: Simpler algorithm, fewer edge cases
4. **Easier to validate**: Visual spiderweb overlay provides immediate feedback
5. **Industry standard**: Used by professional camera calibration systems

Automatic feature detection (FeatureDetector, FeatureMatcher) is preserved as an optional enhancement for convenience, but not required for core functionality.

## Architecture

### Module Structure

```
calibration/
├── calibrate_manual.py            # Manual control point calibration script (PRIMARY)
├── calibrate_intrinsic.py         # Intrinsic calibration script (chessboard)
├── verify_calibration.py          # Verification script with test points
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
├── board_geometry.py              # BoardGeometry class (dartboard dimensions & projection)
├── manual_calibrator.py           # ManualCalibrator class (control point UI)
├── homography_calculator.py       # HomographyCalculator class
├── calibration_manager.py         # CalibrationManager class (continuous calibration)
├── feature_detector.py            # FeatureDetector class (OPTIONAL - automatic detection)
└── feature_matcher.py             # FeatureMatcher class (OPTIONAL - automatic detection)
```

### Component Relationships

```
CalibrationManager (orchestrates calibration lifecycle)
├── manages state: ready, calibrating, error
├── triggers manual calibration on startup
├── runs lightweight validation between throws
└── triggers recalibration on drift detection

ManualCalibrator (interactive control point selection)
├── displays board image with control point labels and zoom overlay
├── captures user clicks at 17 known wire-wire intersections
├── validates point placement with preliminary homography
├── supports abort (ESC) to exit entire application
├── recomputes homography only when points change (_points_changed flag)
├── auto-displays spiderweb overlay after calibration for review
├── generates spiderweb overlay image with error stats for saving
└── returns list of (pixel, board) point pairs

BoardGeometry (dartboard dimensions and projection)
├── stores Winmau Blade 6 dimensions
├── defines 17 control points: bull + 8 sector boundaries x 2 rings (iT + oD)
├── computes board coordinates for any sector/ring combination
├── computes sector boundary angles between adjacent sectors
├── projects board coordinates to pixels via homography
└── generates spiderweb overlay with sector boundary lines (not sector centers)

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
Camera Frame (800x600 BGR)
    |
[User clicks 17 wire-wire intersection control points in ManualCalibrator UI]
  - Zoom overlay for precision clicking
  - Abort via ESC exits entire application
  - Preliminary homography recomputed only when points change
    |
Control Point Pairs (17 total):
  - Bull center: (pixel) -> (0, 0)
  - 8 inner triple ring intersections at sector boundaries
  - 8 outer double ring intersections at sector boundaries
  - Symmetric layout: 2 boundaries per cardinal direction (N/S/E/W)
  - North: 20/1, 5/20 | South: 19/3, 17/3 | East: 6/13, 10/6 | West: 8/11, 11/14
    |
[HomographyCalculator.compute()]
    |
Homography Matrix H (3x3)
    | (saved to JSON, committed to git)
[Auto-display spiderweb overlay for review, save image]
    |
[CoordinateMapper.map_to_board()]
    |
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
    
    def detect_sector_boundaries(self, image: np.ndarray,
                                 bull_center: tuple[float, float]) -> list[tuple]
    
    def find_boundary_intersections(self, ring_edges: dict, 
                                    sector_boundaries: list) -> list[BoundaryIntersection]
```

**Algorithm - Bull Center Detection** (100% SUCCESS RATE):
```
detect_bull_center(image):
    # Strategy 1: Geometric center from line intersections (MOST RELIABLE)
    1. Apply Canny edge detection
    2. Detect lines using HoughLinesP (sector boundaries)
    3. Compute intersection points of lines
    4. Filter intersections near image center (within 150px)
    5. Find median of intersection cluster (robust to outliers)
    6. VALIDATE: Check for BOTH red AND green colors (≥3% each in 25px radius)
    7. If validated, return geometric center
    
    # Strategy 2: Hough circles with STRICT validation
    1. Apply Gaussian blur to reduce noise
    2. Detect circles using HoughCircles (radius 8-35px)
    3. Sort circles by distance from image center
    4. For each circle (closest first):
       a. VALIDATE: Check for BOTH red AND green colors
       b. If validated, return circle center
    
    # Strategy 3: Color-based detection (LAST RESORT)
    1. Create HSV masks for red and green
    2. Combine with AND operation (bull has BOTH colors)
    3. Find contours in combined mask
    4. Filter by size (small) and position (near center)
    5. Select smallest contour closest to center
    6. Return contour centroid
    
    # KEY INSIGHT: Bull MUST have BOTH red (double bull) AND green (single bull)
    # This strict validation eliminates false positives from triple/double ring segments
    # which only have ONE color (either red OR green, never both)
    
    # VALIDATION RESULTS:
    # - Tested on 60 real images (20 per camera, all 3 cameras)
    # - 100% detection accuracy across all camera angles
    # - cam0 (upper right): Always correct via geometric center
    # - cam1 (lower right): Usually geometric center, sometimes Hough circles
    # - cam2 (left, angled): Mix of geometric center and Hough circles
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

**Algorithm - Sector Boundary Detection** (ADAPTIVE THRESHOLD):
```
detect_sector_boundaries(image, bull_center):
    1. Convert to grayscale (more reliable than pure color segmentation)
    2. Apply Canny edge detection (thresholds: 50, 150)
    3. Create annular mask for singles region (between triple and double rings)
       - Outer radius: ~270px (double ring area)
       - Inner radius: ~140px (exclude triple ring)
    4. Extract edge points within mask
    5. Compute angle from bull center for each edge point (0° = up, clockwise)
    6. Create angular histogram (360 bins, 1° per bin)
    7. Smooth histogram with moving average (window size 5)
    8. ADAPTIVE THRESHOLD: Try progressively lower percentiles until ≥8 peaks found
       - Try: 75%, 70%, 65%, 60%, 55%, 50% percentiles
       - This handles varying camera perspectives (especially angled cam2)
    9. Find peaks in histogram (local maxima above threshold)
    10. For each peak:
        a. Cluster nearby transition points (±5° tolerance)
        b. Compute mean angle for boundary
        c. Estimate sector number from boundary angle
        d. Compute confidence from peak height and point count
    11. Return list of SectorBoundary objects
    
    # VALIDATION RESULTS:
    # - cam0: 12 boundaries detected ✅
    # - cam1: 9 boundaries detected ✅
    # - cam2: 8 boundaries detected ✅ (was 0 before adaptive threshold)
```

**Algorithm - Boundary-Ring Intersection Finding**:
```
find_boundary_intersections(ring_edges, sector_boundaries):
    intersections = []
    for boundary in sector_boundaries:
        for ring_type in ['double_ring', 'triple_ring']:
            # Find where sector boundary crosses ring
            # Boundary is defined by angle from bull center
            intersection = angle_ellipse_intersection(
                boundary.angle, 
                bull_center, 
                ring_edges[ring_type]
            )
            if intersection:
                # Sector is known from boundary identification
                sector = boundary.sector
                intersections.append(BoundaryIntersection(
                    pixel=intersection,
                    ring_type=ring_type,
                    sector=sector,
                    confidence=boundary.confidence
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
    
    def identify_sector_20(self, sector_boundaries: list, 
                           image_orientation: str) -> SectorBoundary | None
    
    def assign_boundary_sectors(self, sector_boundaries: list, 
                                sector_20_boundary: SectorBoundary) -> list[SectorBoundary]
```

**Algorithm - Feature Matching**:
```
match(detection_result):
    point_pairs = []
    
    # 1. Bull center → (0, 0)
    if detection_result.bull_center:
        point_pairs.append((detection_result.bull_center, (0, 0)))
    
    # 2. Identify sector 20 (top of board) from color boundaries
    sector_20_boundary = identify_sector_20(detection_result.sector_boundaries)
    
    # 3. Sector boundaries already have sector assignments from color detection
    # Each boundary knows its sector number from the alternating black/white pattern
    
    # 4. For each boundary intersection, compute board coordinates
    for intersection in detection_result.boundary_intersections:
        sector = intersection.sector
        angle = sector_to_angle(sector)  # 20 at 0°, clockwise
        radius = 170 if intersection.ring_type == 'double_ring' else 107
        
        # Board coordinates
        x = radius * cos(angle)
        y = radius * sin(angle)
        
        # Weight by confidence (color boundaries are more reliable than wires)
        point_pairs.append((intersection.pixel, (x, y), intersection.confidence))
    
    # 5. Add ring edge points (sampled along ellipse)
    for ring_type, radius in [('double_ring', 170), ('triple_ring', 107)]:
        for pixel_point in detection_result.ring_edges[ring_type]:
            # Estimate angle from bull center
            angle = atan2(pixel_point[1] - bull_v, pixel_point[0] - bull_u)
            x = radius * cos(angle)
            y = radius * sin(angle)
            point_pairs.append((pixel_point, (x, y), 1.0))
    
    return point_pairs
```

**Algorithm - Sector 20 Identification**:
```
identify_sector_20(sector_boundaries, image_orientation='top'):
    # Sector 20 is at top of board (12 o'clock)
    # Find boundary closest to vertical (pointing up from bull)
    # The boundary to the LEFT of sector 20 (between 5 and 20) should point up
    
    best_boundary = None
    best_score = -inf
    
    for boundary in sector_boundaries:
        # Boundary angle relative to vertical
        angle_from_vertical = abs(boundary.angle - 90°)  # 90° = pointing up
        
        # Score: prefer boundaries pointing up, weighted by confidence
        score = -angle_from_vertical * boundary.confidence
        
        if score > best_score:
            best_score = score
            best_boundary = boundary
    
    # Once sector 20 boundary is found, assign sector numbers to all boundaries
    # based on angular offset (18° per sector, clockwise)
    return best_boundary
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
    sector_boundaries: list[SectorBoundary]
    boundary_intersections: list[BoundaryIntersection]
    detection_time_ms: float
    
@dataclass
class SectorBoundary:
    angle: float  # degrees from vertical (0° = sector 20 at top)
    sector: int  # sector number (1-20)
    edge_points: list[tuple[float, float]]  # color transition points
    confidence: float

@dataclass
class BoundaryIntersection:
    pixel: tuple[float, float]
    ring_type: str  # 'double_ring' or 'triple_ring'
    sector: int  # sector number (1-20)
    confidence: float
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

# HSV color ranges for dartboard (Winmau Blade 6)
[calibration.feature_detection.colors]
# Black singles: low saturation, low value
black_singles_h = [0, 180]
black_singles_s = [0, 50]
black_singles_v = [0, 80]

# White/cream singles: low saturation, high value
white_singles_h = [0, 180]
white_singles_s = [0, 50]
white_singles_v = [150, 255]

# Red rings (double bull, red segments): hue ~0° or ~180°
red_ring_h = [0, 10, 170, 180]  # wraps around
red_ring_s = [100, 255]
red_ring_v = [100, 255]

# Green rings (single bull, green segments): hue ~120°
green_ring_h = [40, 80]
green_ring_s = [100, 255]
green_ring_v = [100, 255]

# Color transition detection
min_boundary_edge_points = 10
boundary_clustering_angle_deg = 2.0

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
    "sector_boundaries": 12,
    "boundary_intersections": 18
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
