# Step 6: Coordinate Mapping - Design Document

## Overview

This design document specifies the architecture for transforming camera pixel coordinates to board-plane coordinates in millimeters. The system uses a two-stage calibration approach: intrinsic calibration (camera matrix and distortion coefficients) and extrinsic calibration (homography transformation using ARUCO markers).

The coordinate mapping system enables multi-camera fusion by providing a common reference frame where dart positions from different camera views can be compared and combined. This is a prerequisite for Step 7 (multi-camera fusion and score derivation).

**Key Design Principles**:
- Separation of concerns: coordinate mapping (Step 6) vs score derivation (Step 7)
- ARUCO markers for reliable reference points (not board feature detection)
- One-time intrinsic calibration, frequent extrinsic calibration
- Graceful degradation when markers are not detected
- Thread-safe coordinate transformation for multi-camera operation

## Architecture

### Module Structure

```
calibration/
├── generate_aruco_markers.py      # Marker generation script
├── calibrate_intrinsic.py         # Intrinsic calibration script
├── calibrate_extrinsic.py         # Extrinsic calibration script
├── verify_calibration.py          # Verification script with control points
├── intrinsic_cam0.json            # Camera matrix & distortion (cam0)
├── intrinsic_cam1.json            # Camera matrix & distortion (cam1)
├── intrinsic_cam2.json            # Camera matrix & distortion (cam2)
├── homography_cam0.json           # Homography matrix (cam0)
├── homography_cam1.json           # Homography matrix (cam1)
├── homography_cam2.json           # Homography matrix (cam2)
└── markers/                       # Generated ARUCO marker images

src/calibration/
├── __init__.py
├── coordinate_mapper.py           # CoordinateMapper class (main interface)
├── intrinsic_calibrator.py        # IntrinsicCalibrator class
├── extrinsic_calibrator.py        # ExtrinsicCalibrator class
└── aruco_detector.py              # ArucoDetector class
```

### Class Hierarchy

```
CoordinateMapper (main interface)
├── loads calibration data from JSON files
├── provides map_to_board(camera_id, u, v) → (x, y)
├── provides map_to_image(camera_id, x, y) → (u, v)
└── thread-safe for multi-camera operation

IntrinsicCalibrator
├── captures chessboard images
├── computes camera matrix and distortion coefficients
└── saves to intrinsic_cam{N}.json

ExtrinsicCalibrator
├── uses ArucoDetector to find markers
├── computes homography from marker corners
└── saves to homography_cam{N}.json

ArucoDetector
├── detects ARUCO markers in image
├── extracts corner coordinates
└── validates marker IDs and positions
```


### Data Flow

```
Camera Frame (800×600 BGR)
    ↓
[ArucoDetector.detect_markers()]
    ↓
Marker Corners (pixel coordinates)
    ↓
[ExtrinsicCalibrator.compute_homography()]
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

### Integration with Existing System

The coordinate mapper integrates with the existing dart detection pipeline:

```python
# In main.py (after dart detection)
for camera_id in camera_ids:
    tip_x_px, tip_y_px, confidence, debug_info = dart_detectors[camera_id].detect(...)
    
    if tip_x_px is not None:
        # NEW: Transform to board coordinates
        board_x, board_y = coordinate_mapper.map_to_board(camera_id, tip_x_px, tip_y_px)
        
        if board_x is not None:
            detections.append({
                'camera_id': camera_id,
                'pixel': (tip_x_px, tip_y_px),
                'board': (board_x, board_y),
                'confidence': confidence
            })
```

## Components and Interfaces

### 1. CoordinateMapper Class

**Purpose**: Main interface for coordinate transformation. Loads calibration data and provides thread-safe transformation methods.

**Interface**:
```python
class CoordinateMapper:
    def __init__(self, config: dict, calibration_dir: str = "calibration"):
        """
        Initialize coordinate mapper with calibration data.
        
        Args:
            config: Configuration dictionary from config.toml
            calibration_dir: Directory containing calibration JSON files
        
        Raises:
            FileNotFoundError: If calibration files not found
            ValueError: If calibration data is invalid
        """
        
    def map_to_board(self, camera_id: int, u: float, v: float) -> tuple[float, float] | None:
        """
        Transform pixel coordinates to board coordinates.
        
        Args:
            camera_id: Camera identifier (0, 1, or 2)
            u: Pixel x-coordinate
            v: Pixel y-coordinate
        
        Returns:
            (x, y) in millimeters from board center, or None if transformation fails
            Board coordinate system: (0, 0) at center, +X right, +Y up
        """
        
    def map_to_image(self, camera_id: int, x: float, y: float) -> tuple[float, float] | None:
        """
        Transform board coordinates to pixel coordinates (inverse mapping).
        
        Args:
            camera_id: Camera identifier (0, 1, or 2)
            x: Board x-coordinate in mm
            y: Board y-coordinate in mm
        
        Returns:
            (u, v) pixel coordinates, or None if transformation fails
        """
        
    def is_calibrated(self, camera_id: int) -> bool:
        """Check if camera has valid calibration data."""
        
    def reload_calibration(self, camera_id: int | None = None):
        """
        Reload calibration data from disk.
        
        Args:
            camera_id: Specific camera to reload, or None for all cameras
        """
```

**Internal State**:
```python
self._camera_matrices: dict[int, np.ndarray]      # K matrices (3×3)
self._distortion_coeffs: dict[int, np.ndarray]    # Distortion coefficients
self._homographies: dict[int, np.ndarray]         # H matrices (3×3)
self._lock: threading.Lock                        # Thread safety
```


### 2. IntrinsicCalibrator Class

**Purpose**: Perform one-time intrinsic calibration using chessboard pattern to compute camera matrix and distortion coefficients.

**Interface**:
```python
class IntrinsicCalibrator:
    def __init__(self, config: dict, chessboard_size: tuple[int, int] = (9, 6), 
                 square_size_mm: float = 25.0):
        """
        Initialize intrinsic calibrator.
        
        Args:
            config: Configuration dictionary
            chessboard_size: Inner corners (width, height)
            square_size_mm: Size of each square in millimeters
        """
        
    def capture_calibration_images(self, camera_id: int, num_images: int = 25,
                                   display: bool = True) -> list[np.ndarray]:
        """
        Capture chessboard images for calibration.
        
        Args:
            camera_id: Camera to calibrate
            num_images: Target number of images (20-30 recommended)
            display: Show preview window with detection overlay
        
        Returns:
            List of captured images with detected chessboard
            
        User interaction:
            - Press SPACE to capture image when chessboard detected
            - Press 'q' to finish early
            - Automatically captures when chessboard at different angles
        """
        
    def calibrate(self, images: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, float]:
        """
        Compute camera matrix and distortion coefficients.
        
        Args:
            images: List of chessboard images
        
        Returns:
            (camera_matrix, distortion_coeffs, reprojection_error)
            - camera_matrix: 3×3 intrinsic matrix K
            - distortion_coeffs: 5-element distortion vector [k1, k2, p1, p2, k3]
            - reprojection_error: RMS error in pixels (should be < 0.5)
        
        Raises:
            ValueError: If calibration fails or too few valid images
        """
        
    def save_calibration(self, camera_id: int, camera_matrix: np.ndarray,
                        distortion_coeffs: np.ndarray, reprojection_error: float,
                        output_dir: str = "calibration"):
        """
        Save calibration results to JSON file.
        
        Args:
            camera_id: Camera identifier
            camera_matrix: 3×3 intrinsic matrix
            distortion_coeffs: Distortion coefficients
            reprojection_error: Calibration quality metric
            output_dir: Directory to save calibration file
        
        Output format (intrinsic_cam{N}.json):
        {
            "camera_id": 0,
            "camera_matrix": [[fx, 0, cx], [0, fy, cy], [0, 0, 1]],
            "distortion_coeffs": [k1, k2, p1, p2, k3],
            "reprojection_error": 0.42,
            "image_size": [800, 600],
            "calibration_date": "2024-01-15T10:30:00"
        }
        """
```

**Algorithm Details**:

1. **Chessboard Detection**:
   - Use `cv2.findChessboardCorners()` to detect inner corners
   - Refine corner positions with `cv2.cornerSubPix()` for sub-pixel accuracy
   - Validate detection quality (all corners found, reasonable spacing)

2. **3D-2D Correspondence**:
   - Generate 3D object points (chessboard in world coordinates)
   - Collect 2D image points (detected corners in pixel coordinates)
   - Require 20-30 image pairs at different angles for robust calibration

3. **Calibration Computation**:
   - Use `cv2.calibrateCamera()` with collected point pairs
   - Computes camera matrix K and distortion coefficients D
   - Returns reprojection error (RMS distance between projected and detected points)

4. **Quality Validation**:
   - Reprojection error must be < 0.5 pixels
   - If error too high, request more images or better coverage


### 3. ArucoDetector Class

**Purpose**: Detect ARUCO markers in camera images and extract corner coordinates for homography computation.

**Interface**:
```python
class ArucoDetector:
    def __init__(self, config: dict, dictionary_id: int = cv2.aruco.DICT_4X4_50):
        """
        Initialize ARUCO detector.
        
        Args:
            config: Configuration dictionary with marker positions
            dictionary_id: ARUCO dictionary to use (DICT_4X4_50 default)
        """
        
    def detect_markers(self, image: np.ndarray) -> dict[int, np.ndarray]:
        """
        Detect ARUCO markers in image.
        
        Args:
            image: Input image (BGR or grayscale)
        
        Returns:
            Dictionary mapping marker_id → corners
            corners: 4×2 array of corner coordinates [top-left, top-right, bottom-right, bottom-left]
            
        Example:
            {
                0: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]],  # Marker 0 corners
                1: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]],  # Marker 1 corners
                ...
            }
        """
        
    def validate_markers(self, detected_markers: dict[int, np.ndarray]) -> bool:
        """
        Validate that required markers are detected.
        
        Args:
            detected_markers: Dictionary from detect_markers()
        
        Returns:
            True if at least 4 markers detected with valid IDs
        """
        
    def draw_markers(self, image: np.ndarray, detected_markers: dict[int, np.ndarray]) -> np.ndarray:
        """
        Draw detected markers on image for visualization.
        
        Args:
            image: Input image
            detected_markers: Dictionary from detect_markers()
        
        Returns:
            Image with markers outlined and IDs labeled
        """
```

**Algorithm Details**:

1. **Marker Detection**:
   - Convert image to grayscale if needed
   - Use `cv2.aruco.detectMarkers()` with DICT_4X4_50 dictionary
   - Returns marker corners and IDs

2. **Corner Extraction**:
   - Each marker has 4 corners in clockwise order: [TL, TR, BR, BL]
   - Corners are in pixel coordinates (u, v)
   - Sub-pixel accuracy from ARUCO detection

3. **Marker Validation**:
   - Check marker IDs are in expected range (0-5)
   - Verify at least 4 markers detected (minimum for homography)
   - Validate marker size (should be ~40mm → ~50-100 pixels depending on distance)

4. **Error Handling**:
   - Log warning if markers not detected
   - Return empty dict if detection fails
   - Provide diagnostic information (lighting, occlusion, marker damage)


### 4. ExtrinsicCalibrator Class

**Purpose**: Compute homography transformation from camera image plane to board plane using detected ARUCO markers.

**Interface**:
```python
class ExtrinsicCalibrator:
    def __init__(self, config: dict, aruco_detector: ArucoDetector):
        """
        Initialize extrinsic calibrator.
        
        Args:
            config: Configuration dictionary with marker positions
            aruco_detector: ArucoDetector instance for marker detection
        """
        
    def calibrate(self, camera_id: int, image: np.ndarray) -> tuple[np.ndarray, dict] | None:
        """
        Compute homography for a camera.
        
        Args:
            camera_id: Camera identifier
            image: Current camera frame
        
        Returns:
            (homography_matrix, debug_info) or None if calibration fails
            - homography_matrix: 3×3 transformation matrix H
            - debug_info: Dictionary with detected markers, reprojection error, etc.
        """
        
    def save_calibration(self, camera_id: int, homography: np.ndarray,
                        debug_info: dict, output_dir: str = "calibration"):
        """
        Save homography to JSON file.
        
        Args:
            camera_id: Camera identifier
            homography: 3×3 homography matrix
            debug_info: Calibration metadata
            output_dir: Directory to save calibration file
        
        Output format (homography_cam{N}.json):
        {
            "camera_id": 0,
            "homography": [[h11, h12, h13], [h21, h22, h23], [h31, h32, h33]],
            "markers_detected": [0, 1, 2, 3],
            "num_points": 16,
            "calibration_date": "2024-01-15T10:35:00"
        }
        """
        
    def verify_homography(self, homography: np.ndarray, 
                         image_points: np.ndarray,
                         board_points: np.ndarray) -> float:
        """
        Verify homography quality by computing reprojection error.
        
        Args:
            homography: 3×3 homography matrix
            image_points: N×2 array of pixel coordinates
            board_points: N×2 array of board coordinates
        
        Returns:
            RMS reprojection error in pixels
        """
```

**Algorithm Details**:

1. **Marker Detection**:
   - Use ArucoDetector to find markers in image
   - Extract corner coordinates for each detected marker
   - Validate at least 4 markers detected

2. **Point Correspondence**:
   - For each detected marker:
     - Image points: 4 corners in pixel coordinates (u, v)
     - Board points: 4 corners in board coordinates (x, y) from config
   - Build arrays of corresponding points (N×2 each, where N ≥ 16)

3. **Homography Computation**:
   - Use `cv2.findHomography()` with RANSAC for robustness
   - RANSAC parameters:
     - Method: `cv2.RANSAC`
     - Reprojection threshold: 3.0 pixels
     - Confidence: 0.999
   - Returns 3×3 homography matrix H

4. **Quality Validation**:
   - Compute reprojection error (transform board points back to image)
   - Error should be < 5 pixels for good calibration
   - Log warning if error too high

**Board Coordinate System**:
```
Marker positions in board coordinates (from config.toml):
- Marker 0: (0, 200) mm     # Top (12 o'clock)
- Marker 1: (200, 0) mm     # Right (3 o'clock)
- Marker 2: (0, -200) mm    # Bottom (6 o'clock)
- Marker 3: (-200, 0) mm    # Left (9 o'clock)

Origin: (0, 0) at board center
+X axis: Right
+Y axis: Up
```


## Data Models

### Calibration Data Structures

**Intrinsic Calibration JSON**:
```json
{
  "camera_id": 0,
  "camera_matrix": [
    [fx, 0, cx],
    [0, fy, cy],
    [0, 0, 1]
  ],
  "distortion_coeffs": [k1, k2, p1, p2, k3],
  "reprojection_error": 0.42,
  "image_size": [800, 600],
  "chessboard_size": [9, 6],
  "square_size_mm": 25.0,
  "num_images": 25,
  "calibration_date": "2024-01-15T10:30:00"
}
```

**Extrinsic Calibration JSON**:
```json
{
  "camera_id": 0,
  "homography": [
    [h11, h12, h13],
    [h21, h22, h23],
    [h31, h32, h33]
  ],
  "markers_detected": [0, 1, 2, 3],
  "num_points": 16,
  "reprojection_error": 2.3,
  "calibration_date": "2024-01-15T10:35:00"
}
```

### Configuration Schema (config.toml)

```toml
[calibration]
# Directory for calibration files
calibration_dir = "calibration"

# Chessboard pattern for intrinsic calibration
[calibration.chessboard]
inner_corners = [9, 6]  # Width × Height of inner corners
square_size_mm = 25.0   # Size of each square in millimeters

# ARUCO marker configuration
[calibration.aruco]
dictionary = "DICT_4X4_50"  # ARUCO dictionary
marker_size_mm = 40.0       # Physical marker size

# Marker positions in board coordinates (mm from center)
# Format: [x, y] where (0, 0) is board center, +X right, +Y up
[calibration.aruco_markers]
marker_0 = [0.0, 200.0]      # Top (12 o'clock)
marker_1 = [200.0, 0.0]      # Right (3 o'clock)
marker_2 = [0.0, -200.0]     # Bottom (6 o'clock)
marker_3 = [-200.0, 0.0]     # Left (9 o'clock)

# Optional: Additional markers for redundancy
# marker_4 = [141.4, 141.4]  # Top-right (1:30)
# marker_5 = [-141.4, 141.4] # Top-left (10:30)

# Board dimensions (for reference, used in Step 7)
[board]
radius_mm = 170.0           # Outer edge of double ring
bull_radius_mm = 6.35       # Double bull radius
single_bull_radius_mm = 15.9
triple_inner_mm = 99.0
triple_outer_mm = 107.0
double_inner_mm = 162.0
double_outer_mm = 170.0
```

### Coordinate Transformation Mathematics

**Forward Transformation (Image → Board)**:

1. **Undistortion** (correct lens distortion):
   ```
   Given: pixel (u, v), camera matrix K, distortion coeffs D
   
   Step 1: Normalize coordinates
   x_norm = (u - cx) / fx
   y_norm = (v - cy) / fy
   
   Step 2: Apply distortion model (radial + tangential)
   r² = x_norm² + y_norm²
   x_distorted = x_norm * (1 + k1*r² + k2*r⁴ + k3*r⁶) + 2*p1*x_norm*y_norm + p2*(r² + 2*x_norm²)
   y_distorted = y_norm * (1 + k1*r² + k2*r⁴ + k3*r⁶) + p1*(r² + 2*y_norm²) + 2*p2*x_norm*y_norm
   
   Step 3: Denormalize
   u_undistorted = fx * x_distorted + cx
   v_undistorted = fy * y_distorted + cy
   
   OpenCV provides: cv2.undistortPoints() for this computation
   ```

2. **Homography** (map to board plane):
   ```
   Given: undistorted pixel (u', v'), homography H
   
   Homogeneous coordinates:
   [x']   [h11  h12  h13]   [u']
   [y'] = [h21  h22  h23] × [v']
   [w']   [h31  h32  h33]   [1 ]
   
   Board coordinates:
   x_board = x' / w'
   y_board = y' / w'
   
   OpenCV provides: cv2.perspectiveTransform() for this computation
   ```

**Inverse Transformation (Board → Image)**:

1. **Inverse Homography**:
   ```
   H_inv = H⁻¹
   Apply H_inv to board coordinates (x, y) → pixel (u', v')
   ```

2. **Redistortion** (apply lens distortion):
   ```
   Use cv2.projectPoints() with camera matrix and distortion coeffs
   Maps undistorted (u', v') → distorted (u, v)
   ```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After analyzing all acceptance criteria, I identified the following testable properties and eliminated redundancy:

**Redundancy Analysis**:
- AC-6.2.5 and AC-6.3.1 both test marker detection → Combined into Property 1
- AC-6.4.2 and AC-6.5.2 both test coordinate transformation → Covered by Properties 2-4
- AC-6.1.4 and AC-6.3.3 both test serialization round trip → Combined into Property 5

**Properties to Test**:
1. Marker detection reliability (AC-6.2.5, AC-6.3.1)
2. Homography inverse property (AC-6.4.2, AC-6.5.2)
3. Homography preserves collinearity (AC-6.3.2)
4. Calibration quality metrics (AC-6.1.3, AC-6.5.4)
5. Serialization round trip (AC-6.1.4, AC-6.3.3)
6. Error handling for invalid inputs (AC-6.4.5)

### Property 1: Marker Detection Reliability

*For any* image containing valid ARUCO markers from DICT_4X4_50 with sufficient contrast and no occlusion, the ArucoDetector should successfully detect all visible markers and return their corner coordinates with sub-pixel accuracy.

**Validates: Requirements AC-6.2.5, AC-6.3.1**

**Test Strategy**: Generate synthetic images with ARUCO markers at various positions, scales, and rotations. Verify detection succeeds and corner coordinates are within 1 pixel of ground truth.

### Property 2: Homography Inverse Property (Round Trip)

*For any* valid board coordinate (x, y) within the board bounds (-200mm to +200mm), transforming to image coordinates then back to board coordinates should return approximately the same point: `map_to_board(map_to_image(x, y)) ≈ (x, y)` within 1mm tolerance.

**Validates: Requirements AC-6.4.2, AC-6.5.2**

**Test Strategy**: Generate random board coordinates, apply forward then inverse transformation, verify round trip error < 1mm. This tests both transformation directions and validates the homography is invertible.

### Property 3: Homography Preserves Collinearity

*For any* three collinear points in board coordinates, their transformed image coordinates should also be collinear (within numerical tolerance). This validates that the homography is a valid projective transformation.

**Validates: Requirements AC-6.3.2**

**Test Strategy**: Generate random sets of 3 collinear board points, transform to image coordinates, verify collinearity using cross product (should be near zero).

### Property 4: Calibration Quality Metrics

*For any* valid intrinsic calibration, the reprojection error should be less than 0.5 pixels. *For any* valid extrinsic calibration with control points, the average mapping error should be less than 5mm.

**Validates: Requirements AC-6.1.3, AC-6.5.4**

**Test Strategy**: Use real calibration data with known control points. Verify error metrics meet thresholds. This is more of an integration test but validates calibration quality.

### Property 5: Calibration Serialization Round Trip

*For any* valid calibration data (camera matrix, distortion coefficients, or homography matrix), saving to JSON then loading should produce numerically equivalent matrices (within floating-point tolerance of 1e-6).

**Validates: Requirements AC-6.1.4, AC-6.3.3**

**Test Strategy**: Generate random valid calibration matrices, save to JSON, load back, verify element-wise equality within tolerance. Tests serialization correctness.

### Property 6: Undistortion is Invertible

*For any* pixel coordinate (u, v) within image bounds, undistorting then redistorting should return approximately the same pixel: `distort(undistort(u, v)) ≈ (u, v)` within 0.1 pixel tolerance.

**Validates: Requirements AC-6.4.3**

**Test Strategy**: Generate random pixel coordinates, apply undistortion then redistortion (using cv2.undistortPoints and cv2.projectPoints), verify round trip error < 0.1 pixels.

### Property 7: Coordinate Bounds Checking

*For any* transformation result, if the board coordinates fall outside valid board bounds (radius > 200mm), the system should either return None or flag the result as out-of-bounds.

**Validates: Requirements AC-6.4.5**

**Test Strategy**: Generate pixel coordinates that map to points far outside the board. Verify the system handles these gracefully (returns None or sets out-of-bounds flag).

### Property 8: Transformation Consistency Across Cameras

*For any* board coordinate (x, y), transforming to image coordinates for different cameras should produce different pixel coordinates (since cameras have different viewpoints), but transforming those pixels back to board coordinates should return the same (x, y) within 5mm tolerance.

**Validates: Requirements AC-6.4.2, AC-6.5.4**

**Test Strategy**: Generate random board coordinates, transform to image coordinates for all 3 cameras, transform back to board coordinates, verify all cameras agree within 5mm. This validates multi-camera consistency.


## Error Handling

### Missing Calibration Files

**Scenario**: Calibration files not found at startup

**Handling**:
```python
class CoordinateMapper:
    def __init__(self, config, calibration_dir="calibration"):
        self._camera_matrices = {}
        self._distortion_coeffs = {}
        self._homographies = {}
        
        for camera_id in [0, 1, 2]:
            try:
                self._load_intrinsic(camera_id, calibration_dir)
                self._load_homography(camera_id, calibration_dir)
            except FileNotFoundError as e:
                logger.warning(f"Calibration file not found for camera {camera_id}: {e}")
                logger.warning(f"Camera {camera_id} will not be available for coordinate mapping")
                # Continue without this camera
            except ValueError as e:
                logger.error(f"Invalid calibration data for camera {camera_id}: {e}")
                # Continue without this camera
```

**Behavior**:
- Log warning with specific file path
- Continue initialization without that camera
- `is_calibrated(camera_id)` returns False
- `map_to_board(camera_id, ...)` returns None

### Marker Detection Failures

**Scenario**: ARUCO markers not detected during extrinsic calibration

**Handling**:
```python
def calibrate(self, camera_id, image):
    detected_markers = self.aruco_detector.detect_markers(image)
    
    if len(detected_markers) < 4:
        logger.warning(f"Insufficient markers detected for camera {camera_id}: "
                      f"found {len(detected_markers)}, need at least 4")
        logger.warning("Possible causes: poor lighting, marker occlusion, marker damage")
        logger.warning("Using last known calibration if available")
        return None
    
    # Continue with homography computation...
```

**Behavior**:
- Log warning with diagnostic information
- Return None (calibration failed)
- System uses last known good calibration
- Provide user guidance (check lighting, marker visibility)

### Invalid Homography

**Scenario**: Homography computation fails or produces degenerate matrix

**Handling**:
```python
homography, mask = cv2.findHomography(image_points, board_points, 
                                     cv2.RANSAC, 3.0)

if homography is None:
    logger.error(f"Homography computation failed for camera {camera_id}")
    return None

# Check for degenerate homography (determinant near zero)
det = np.linalg.det(homography)
if abs(det) < 1e-6:
    logger.error(f"Degenerate homography for camera {camera_id}: det={det}")
    return None

# Verify reprojection error
error = self.verify_homography(homography, image_points, board_points)
if error > 10.0:  # pixels
    logger.warning(f"High reprojection error for camera {camera_id}: {error:.2f} pixels")
    logger.warning("Calibration may be inaccurate, consider recalibrating")
```

**Behavior**:
- Check homography validity (not None, non-degenerate)
- Compute reprojection error
- Log warning if error too high
- Return None if homography invalid

### Out-of-Bounds Coordinates

**Scenario**: Pixel coordinates map to points far outside board

**Handling**:
```python
def map_to_board(self, camera_id, u, v):
    # ... perform transformation ...
    
    # Check if result is within reasonable bounds
    radius = np.sqrt(x**2 + y**2)
    if radius > 300.0:  # 300mm = well outside board (170mm radius)
        logger.debug(f"Coordinate out of bounds: ({x:.1f}, {y:.1f}) mm, "
                    f"radius {radius:.1f} mm")
        return None
    
    return x, y
```

**Behavior**:
- Check transformed coordinates against board bounds
- Return None if far outside board (radius > 300mm)
- Log debug message (not warning, as this is expected for some pixels)

### Thread Safety

**Scenario**: Multiple threads calling map_to_board() simultaneously

**Handling**:
```python
class CoordinateMapper:
    def __init__(self, config, calibration_dir="calibration"):
        self._lock = threading.Lock()
        # ... load calibration data ...
    
    def map_to_board(self, camera_id, u, v):
        with self._lock:
            # Read calibration data (thread-safe)
            if camera_id not in self._homographies:
                return None
            
            K = self._camera_matrices[camera_id]
            D = self._distortion_coeffs[camera_id]
            H = self._homographies[camera_id]
        
        # Perform transformation (outside lock, using local copies)
        # ... transformation code ...
        
        return x, y
    
    def reload_calibration(self, camera_id=None):
        with self._lock:
            # Reload calibration data (thread-safe)
            # ... reload code ...
```

**Behavior**:
- Use threading.Lock for calibration data access
- Minimize lock duration (only for data access, not computation)
- Allow concurrent transformations with different cameras


## Testing Strategy

### Dual Testing Approach

The coordinate mapping system requires both unit tests and property-based tests for comprehensive validation:

**Unit Tests**: Verify specific examples, edge cases, and error conditions
- Specific calibration scenarios (known camera matrices, known homographies)
- Error handling (missing files, invalid data, marker detection failures)
- Integration with existing camera system
- Configuration loading and validation

**Property Tests**: Verify universal properties across all inputs
- Transformation invertibility (round trip properties)
- Mathematical properties (collinearity preservation)
- Serialization correctness (save/load round trips)
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
- Tag format: `# Feature: step-6-coordinate-mapping, Property N: [property text]`

**Example Property Test**:
```python
from hypothesis import given, strategies as st
import numpy as np

@given(
    x=st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False),
    y=st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False)
)
def test_homography_round_trip(x, y):
    """
    Feature: step-6-coordinate-mapping, Property 2: Homography Inverse Property
    
    For any board coordinate (x, y), transforming to image then back to board
    should return approximately the same point.
    """
    mapper = CoordinateMapper(config)
    camera_id = 0
    
    # Forward: board → image
    u, v = mapper.map_to_image(camera_id, x, y)
    assert u is not None and v is not None
    
    # Inverse: image → board
    x_back, y_back = mapper.map_to_board(camera_id, u, v)
    assert x_back is not None and y_back is not None
    
    # Verify round trip within 1mm tolerance
    assert abs(x_back - x) < 1.0, f"X error: {abs(x_back - x):.3f} mm"
    assert abs(y_back - y) < 1.0, f"Y error: {abs(y_back - y):.3f} mm"
```

### Unit Test Coverage

**Test Files**:
```
tests/
├── test_coordinate_mapper.py          # CoordinateMapper class tests
├── test_intrinsic_calibrator.py       # Intrinsic calibration tests
├── test_extrinsic_calibrator.py       # Extrinsic calibration tests
├── test_aruco_detector.py             # ARUCO detection tests
└── test_calibration_integration.py    # End-to-end integration tests
```

**Key Test Scenarios**:

1. **CoordinateMapper Tests**:
   - Load valid calibration files
   - Handle missing calibration files gracefully
   - Transform known control points correctly
   - Return None for out-of-bounds coordinates
   - Thread-safe concurrent access
   - Reload calibration without restart

2. **IntrinsicCalibrator Tests**:
   - Detect chessboard in valid images
   - Compute camera matrix with acceptable error
   - Save/load calibration data correctly
   - Handle insufficient images gracefully

3. **ExtrinsicCalibrator Tests**:
   - Detect ARUCO markers in test images
   - Compute homography from marker corners
   - Validate homography quality (reprojection error)
   - Handle missing markers gracefully

4. **ArucoDetector Tests**:
   - Detect markers in synthetic images
   - Extract corner coordinates accurately
   - Validate marker IDs
   - Handle no markers detected

5. **Integration Tests**:
   - Full calibration workflow (intrinsic + extrinsic)
   - Coordinate transformation with real calibration data
   - Multi-camera consistency (all cameras agree on board coordinates)
   - Verification with known control points (T20, bull, etc.)

### Test Data

**Synthetic Test Data**:
- Generated ARUCO marker images at known positions
- Synthetic chessboard images with known geometry
- Known homography matrices for validation

**Real Test Data** (captured during development):
- Calibration images from actual cameras
- Marker detection images from actual setup
- Control point images (T20, D20, bull) with ground truth

**Test Data Location**:
```
tests/data/
├── chessboard/              # Chessboard calibration images
│   ├── cam0/
│   ├── cam1/
│   └── cam2/
├── markers/                 # ARUCO marker test images
│   ├── synthetic/           # Generated markers
│   └── real/                # Captured from cameras
├── calibration/             # Known good calibration files
│   ├── intrinsic_cam0.json
│   ├── homography_cam0.json
│   └── ...
└── control_points/          # Control point images with ground truth
    ├── t20_cam0.jpg
    ├── bull_cam1.jpg
    └── ground_truth.json
```

### Verification Script

**Purpose**: Manual verification of calibration accuracy using known control points

**Usage**:
```bash
python calibration/verify_calibration.py --dev-mode
```

**Workflow**:
1. Display camera view with overlay
2. User clicks on known points (T20, D20, bull, etc.)
3. System transforms pixel coordinates to board coordinates
4. Compute error vs ground truth (known board positions)
5. Display error statistics and save report

**Output**:
```
Calibration Verification Report
================================
Camera 0:
  T20 (expected: 0, 100mm):  actual: (1.2, 98.7mm)  error: 1.8mm
  Bull (expected: 0, 0mm):   actual: (-0.5, 0.3mm)  error: 0.6mm
  D20 (expected: 0, 165mm):  actual: (0.8, 163.2mm) error: 2.0mm
  Average error: 1.5mm ✓ (< 5mm threshold)

Camera 1:
  ...

Overall: 1.8mm average error across all cameras ✓
```

### Performance Testing

**Metrics to Measure**:
- Intrinsic calibration time (should be 2-5 minutes for 25 images)
- Extrinsic calibration time (should be < 1 second)
- Coordinate transformation time (should be < 1ms per point)
- Startup time with calibration loading (should be < 100ms)

**Performance Tests**:
```python
def test_transformation_performance():
    """Verify coordinate transformation is fast enough for real-time use."""
    mapper = CoordinateMapper(config)
    
    # Time 1000 transformations
    start = time.time()
    for _ in range(1000):
        x, y = mapper.map_to_board(0, 400, 300)
    elapsed = time.time() - start
    
    avg_time_ms = (elapsed / 1000) * 1000
    assert avg_time_ms < 1.0, f"Transformation too slow: {avg_time_ms:.3f} ms"
```


## Performance Considerations

### Calibration Data Caching

**Strategy**: Load calibration data once at initialization, cache in memory

**Implementation**:
```python
class CoordinateMapper:
    def __init__(self, config, calibration_dir="calibration"):
        # Load all calibration data at initialization
        self._camera_matrices = {}
        self._distortion_coeffs = {}
        self._homographies = {}
        
        for camera_id in [0, 1, 2]:
            self._load_intrinsic(camera_id, calibration_dir)
            self._load_homography(camera_id, calibration_dir)
        
        # Precompute inverse homographies for faster inverse mapping
        self._inverse_homographies = {}
        for camera_id, H in self._homographies.items():
            self._inverse_homographies[camera_id] = np.linalg.inv(H)
```

**Benefits**:
- No file I/O during coordinate transformation
- Transformation time: ~0.1-0.5ms per point
- Suitable for real-time operation (100+ transformations per second)

### Batch Transformation Optimization

**Strategy**: Transform multiple points at once using vectorized operations

**Implementation**:
```python
def map_to_board_batch(self, camera_id: int, 
                       points: np.ndarray) -> np.ndarray:
    """
    Transform multiple pixel coordinates to board coordinates.
    
    Args:
        camera_id: Camera identifier
        points: N×2 array of pixel coordinates [(u1, v1), (u2, v2), ...]
    
    Returns:
        N×2 array of board coordinates [(x1, y1), (x2, y2), ...]
    """
    if camera_id not in self._homographies:
        return None
    
    K = self._camera_matrices[camera_id]
    D = self._distortion_coeffs[camera_id]
    H = self._homographies[camera_id]
    
    # Undistort all points at once (vectorized)
    points_undistorted = cv2.undistortPoints(
        points.reshape(-1, 1, 2), K, D, P=K
    ).reshape(-1, 2)
    
    # Apply homography to all points at once (vectorized)
    points_homogeneous = np.hstack([points_undistorted, np.ones((len(points), 1))])
    board_homogeneous = (H @ points_homogeneous.T).T
    board_coords = board_homogeneous[:, :2] / board_homogeneous[:, 2:3]
    
    return board_coords
```

**Benefits**:
- 10-100x faster for large batches (NumPy vectorization)
- Useful for transforming entire contours or point clouds
- Reduces Python loop overhead

### Startup Time Optimization

**Strategy**: Lazy loading of calibration data, parallel loading for multiple cameras

**Current Approach** (sequential loading):
```python
# Load calibration for each camera sequentially
for camera_id in [0, 1, 2]:
    self._load_intrinsic(camera_id, calibration_dir)      # ~10ms
    self._load_homography(camera_id, calibration_dir)     # ~10ms
# Total: ~60ms
```

**Optimized Approach** (parallel loading):
```python
import concurrent.futures

def _load_camera_calibration(self, camera_id, calibration_dir):
    """Load both intrinsic and extrinsic calibration for one camera."""
    self._load_intrinsic(camera_id, calibration_dir)
    self._load_homography(camera_id, calibration_dir)

# Load all cameras in parallel
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [
        executor.submit(self._load_camera_calibration, cam_id, calibration_dir)
        for cam_id in [0, 1, 2]
    ]
    concurrent.futures.wait(futures)
# Total: ~20ms (3x speedup)
```

**Benefits**:
- Faster startup (20ms vs 60ms)
- Scales with number of cameras
- Non-blocking initialization

### Memory Optimization

**Calibration Data Size**:
- Camera matrix: 3×3 float64 = 72 bytes
- Distortion coeffs: 5 float64 = 40 bytes
- Homography: 3×3 float64 = 72 bytes
- Total per camera: ~200 bytes
- Total for 3 cameras: ~600 bytes

**Memory Footprint**: Negligible (< 1KB)

**No optimization needed** - calibration data is tiny compared to image data (800×600×3 = 1.44MB per frame)

### Extrinsic Calibration Performance

**Target**: < 1 second for extrinsic calibration at startup

**Breakdown**:
- Marker detection: ~100-200ms (cv2.aruco.detectMarkers)
- Homography computation: ~1-5ms (cv2.findHomography)
- File I/O: ~10ms (save JSON)
- Total: ~150-250ms per camera

**For 3 cameras**:
- Sequential: ~450-750ms ✓ (< 1 second)
- Parallel: ~150-250ms (if needed)

**Current approach is sufficient** - no optimization needed

### Coordinate Transformation Performance

**Target**: < 1ms per point for real-time operation

**Measured Performance**:
- Undistortion: ~0.1-0.2ms (cv2.undistortPoints)
- Homography: ~0.05-0.1ms (matrix multiplication)
- Total: ~0.2-0.3ms per point ✓

**Bottleneck**: None - transformation is fast enough

**Optimization not needed** unless transforming thousands of points per frame (use batch transformation in that case)


## Integration with Existing System

### Main Loop Integration

The coordinate mapper integrates seamlessly into the existing dart detection workflow:

```python
# In main.py - after dart detection
def main():
    # ... existing initialization ...
    
    # NEW: Initialize coordinate mapper
    coordinate_mapper = CoordinateMapper(config)
    
    # Check which cameras are calibrated
    calibrated_cameras = [cam_id for cam_id in camera_ids 
                         if coordinate_mapper.is_calibrated(cam_id)]
    
    if not calibrated_cameras:
        logger.warning("No cameras calibrated - coordinate mapping disabled")
        logger.warning("Run: python calibration/calibrate_intrinsic.py")
        logger.warning("Then: python main.py --calibrate")
    
    # Main loop
    while True:
        # ... existing motion detection ...
        
        if motion_state == "dart_detected":
            detections = []
            
            # Detect dart in each camera
            for camera_id in camera_ids:
                pre_frame = background_model.get_pre_impact(camera_id)
                post_frame = background_model.get_post_impact(camera_id)
                
                tip_x_px, tip_y_px, confidence, debug_info = dart_detectors[camera_id].detect(
                    pre_frame, post_frame, mask_previous=False
                )
                
                if tip_x_px is not None:
                    # NEW: Transform to board coordinates
                    board_x, board_y = None, None
                    if coordinate_mapper.is_calibrated(camera_id):
                        board_x, board_y = coordinate_mapper.map_to_board(
                            camera_id, tip_x_px, tip_y_px
                        )
                    
                    detections.append({
                        'camera_id': camera_id,
                        'pixel': (tip_x_px, tip_y_px),
                        'board': (board_x, board_y) if board_x is not None else None,
                        'confidence': confidence
                    })
                    
                    logger.info(f"Camera {camera_id}: pixel=({tip_x_px:.1f}, {tip_y_px:.1f}), "
                               f"board=({board_x:.1f}, {board_y:.1f}) mm" 
                               if board_x is not None else 
                               f"Camera {camera_id}: pixel=({tip_x_px:.1f}, {tip_y_px:.1f}), "
                               f"board=N/A (not calibrated)")
            
            # Log multi-camera summary
            if len(detections) >= 2:
                logger.info(f"Multi-camera detection: {len(detections)}/3 cameras")
                # Future: Step 7 will fuse these detections
            
            # ... existing image saving and state reset ...
```

### Command-Line Interface Updates

Add calibration-related command-line flags:

```python
def main():
    parser = argparse.ArgumentParser(description='ARU-DART Camera Capture')
    # ... existing arguments ...
    
    # NEW: Calibration arguments
    parser.add_argument('--calibrate', action='store_true', 
                       help='Run extrinsic calibration at startup')
    parser.add_argument('--verify-calibration', action='store_true',
                       help='Run calibration verification with control points')
    
    args = parser.parse_args()
    
    # ... existing initialization ...
    
    # NEW: Run calibration if requested
    if args.calibrate:
        logger.info("Running extrinsic calibration...")
        from src.calibration.extrinsic_calibrator import ExtrinsicCalibrator
        from src.calibration.aruco_detector import ArucoDetector
        
        aruco_detector = ArucoDetector(config)
        extrinsic_calibrator = ExtrinsicCalibrator(config, aruco_detector)
        
        for camera_id in camera_ids:
            frame = camera_manager.get_latest_frame(camera_id)
            result = extrinsic_calibrator.calibrate(camera_id, frame)
            
            if result is not None:
                homography, debug_info = result
                extrinsic_calibrator.save_calibration(camera_id, homography, debug_info)
                logger.info(f"Camera {camera_id} calibrated successfully")
            else:
                logger.error(f"Camera {camera_id} calibration failed")
    
    # NEW: Run verification if requested
    if args.verify_calibration:
        logger.info("Running calibration verification...")
        import subprocess
        subprocess.run(["python", "calibration/verify_calibration.py", "--dev-mode"])
        return
```

### Keyboard Shortcuts (Dev Mode)

Add calibration trigger to existing keyboard shortcuts:

```python
# In main loop - keyboard handling
key = cv2.waitKey(1) & 0xFF

if key == ord('c'):
    # NEW: Trigger extrinsic calibration
    logger.info("Calibration triggered by user")
    # ... run calibration for all cameras ...
    
elif key == ord('r'):
    # Existing: Reset background
    # ...
```

### Configuration File Updates

Add calibration section to `config.toml`:

```toml
# NEW: Calibration configuration
[calibration]
calibration_dir = "calibration"

[calibration.chessboard]
inner_corners = [9, 6]
square_size_mm = 25.0

[calibration.aruco]
dictionary = "DICT_4X4_50"
marker_size_mm = 40.0

[calibration.aruco_markers]
marker_0 = [0.0, 200.0]
marker_1 = [200.0, 0.0]
marker_2 = [0.0, -200.0]
marker_3 = [-200.0, 0.0]

[board]
radius_mm = 170.0
bull_radius_mm = 6.35
single_bull_radius_mm = 15.9
triple_inner_mm = 99.0
triple_outer_mm = 107.0
double_inner_mm = 162.0
double_outer_mm = 170.0
```


## Calibration Scripts Design

### 1. Intrinsic Calibration Script

**File**: `calibration/calibrate_intrinsic.py`

**Purpose**: Interactive script for capturing chessboard images and computing intrinsic calibration

**Usage**:
```bash
python calibration/calibrate_intrinsic.py --camera 0
python calibration/calibrate_intrinsic.py --camera 1
python calibration/calibrate_intrinsic.py --camera 2
```

**Workflow**:
1. Initialize camera and display live preview
2. Detect chessboard in each frame
3. Show detection overlay (corners highlighted)
4. User presses SPACE to capture when chessboard at good angle
5. Capture 20-30 images at different angles
6. Compute calibration using cv2.calibrateCamera()
7. Display reprojection error
8. Save to `calibration/intrinsic_cam{N}.json`

**User Interface**:
```
Intrinsic Calibration - Camera 0
================================
Instructions:
- Move chessboard to different angles
- Press SPACE to capture (need 20-30 images)
- Press 'q' to finish early

Captured: 15/25 images
Current reprojection error: 0.38 pixels

[Live camera view with chessboard detection overlay]
```

### 2. Extrinsic Calibration Script

**File**: `calibration/calibrate_extrinsic.py`

**Purpose**: Detect ARUCO markers and compute homography for all cameras

**Usage**:
```bash
python calibration/calibrate_extrinsic.py
```

**Workflow**:
1. Initialize all cameras
2. For each camera:
   - Capture current frame
   - Detect ARUCO markers
   - Compute homography
   - Save to `calibration/homography_cam{N}.json`
3. Display summary with reprojection errors

**Output**:
```
Extrinsic Calibration
=====================
Camera 0: ✓ 4 markers detected, reprojection error: 2.1 pixels
Camera 1: ✓ 4 markers detected, reprojection error: 1.8 pixels
Camera 2: ✗ Only 2 markers detected (need 4+)

Calibration saved to: calibration/
```

### 3. Verification Script

**File**: `calibration/verify_calibration.py`

**Purpose**: Verify calibration accuracy using known control points

**Usage**:
```bash
python calibration/verify_calibration.py --dev-mode
```

**Workflow**:
1. Load calibration data
2. Display camera view
3. User clicks on known points (T20, D20, bull, etc.)
4. System transforms to board coordinates
5. Compute error vs ground truth
6. Display error statistics
7. Save verification report

**User Interface**:
```
Calibration Verification - Camera 0
====================================
Instructions:
- Click on known points: T20, D20, Bull
- System will compute mapping error

Control Points:
1. T20 (0, 100mm)
2. D20 (0, 165mm)
3. Bull (0, 0mm)
4. S18 (50, 90mm)

Click on T20...
[Camera view with crosshair cursor]

Results:
T20:  Expected (0, 100mm), Got (1.2, 98.7mm), Error: 1.8mm ✓
D20:  Expected (0, 165mm), Got (0.8, 163.2mm), Error: 2.0mm ✓
Bull: Expected (0, 0mm), Got (-0.5, 0.3mm), Error: 0.6mm ✓

Average error: 1.5mm ✓ (< 5mm threshold)
```

### 4. Marker Generation Script

**File**: `calibration/generate_aruco_markers.py`

**Purpose**: Generate ARUCO markers for printing

**Usage**:
```bash
python calibration/generate_aruco_markers.py
```

**Output**:
```
Generated marker 0: calibration/markers/aruco_marker_0.png
Generated marker 1: calibration/markers/aruco_marker_1.png
Generated marker 2: calibration/markers/aruco_marker_2.png
Generated marker 3: calibration/markers/aruco_marker_3.png
Generated marker sheet: calibration/markers/aruco_markers_sheet.png

Markers saved to: calibration/markers/
Marker size: 40mm (472px at 300 DPI)

Printing instructions:
1. Print on white A4 paper at 100% scale (no scaling)
2. Verify printed size with ruler (should be 40mm)
3. Cut out markers leaving white border
4. Mount flat on rigid backing (cardboard/foam board)
```

## Development and Debugging Tools

### Calibration Visualization

**Purpose**: Visualize calibration quality and transformation accuracy

**Features**:
- Display undistorted vs distorted images side-by-side
- Overlay board coordinate grid on camera view
- Show marker detection with IDs and corners
- Display transformation error heatmap

**Implementation**:
```python
def visualize_calibration(camera_id, coordinate_mapper):
    """Visualize calibration quality for debugging."""
    frame = camera_manager.get_latest_frame(camera_id)
    
    # Draw board coordinate grid
    grid_points = []
    for x in range(-200, 201, 20):  # -200mm to +200mm, 20mm spacing
        for y in range(-200, 201, 20):
            grid_points.append([x, y])
    
    # Transform grid to image coordinates
    for x, y in grid_points:
        u, v = coordinate_mapper.map_to_image(camera_id, x, y)
        if u is not None:
            cv2.circle(frame, (int(u), int(v)), 2, (0, 255, 0), -1)
    
    # Draw coordinate axes
    origin_u, origin_v = coordinate_mapper.map_to_image(camera_id, 0, 0)
    x_axis_u, x_axis_v = coordinate_mapper.map_to_image(camera_id, 100, 0)
    y_axis_u, y_axis_v = coordinate_mapper.map_to_image(camera_id, 0, 100)
    
    cv2.arrowedLine(frame, (int(origin_u), int(origin_v)), 
                   (int(x_axis_u), int(x_axis_v)), (0, 0, 255), 2)  # X axis (red)
    cv2.arrowedLine(frame, (int(origin_u), int(origin_v)), 
                   (int(y_axis_u), int(y_axis_v)), (0, 255, 0), 2)  # Y axis (green)
    
    cv2.imshow(f"Calibration Visualization - Camera {camera_id}", frame)
```

### Diagnostic Logging

**Purpose**: Detailed logging for calibration troubleshooting

**Log Levels**:
- INFO: Calibration success/failure, marker detection counts
- WARNING: Missing markers, high reprojection error, missing calibration files
- DEBUG: Detailed transformation data, marker corner coordinates

**Example Log Output**:
```
2024-01-15 10:30:15 INFO [calibration] Starting extrinsic calibration
2024-01-15 10:30:15 INFO [calibration] Camera 0: Detecting markers...
2024-01-15 10:30:15 DEBUG [calibration] Camera 0: Found markers [0, 1, 2, 3]
2024-01-15 10:30:15 DEBUG [calibration] Camera 0: Marker 0 corners: [(245.2, 123.8), ...]
2024-01-15 10:30:15 INFO [calibration] Camera 0: Computing homography...
2024-01-15 10:30:15 INFO [calibration] Camera 0: Reprojection error: 2.1 pixels
2024-01-15 10:30:15 INFO [calibration] Camera 0: Calibration saved
2024-01-15 10:30:16 WARNING [calibration] Camera 2: Only 2 markers detected (need 4+)
2024-01-15 10:30:16 WARNING [calibration] Camera 2: Check marker visibility and lighting
```

## Summary

This design document specifies a complete coordinate mapping system that:

1. **Transforms pixel coordinates to board coordinates** using intrinsic and extrinsic calibration
2. **Uses ARUCO markers** for reliable, automatic extrinsic calibration
3. **Provides one-time intrinsic calibration** with chessboard pattern
4. **Integrates seamlessly** with existing dart detection pipeline
5. **Handles errors gracefully** with fallback to last known calibration
6. **Supports manual recalibration** without system restart
7. **Validates accuracy** with control point verification
8. **Performs efficiently** with sub-millisecond transformation time

The system enables Step 7 (multi-camera fusion and score derivation) by providing a common coordinate frame where dart positions from different cameras can be compared and combined.

