# Step 6: Coordinate Mapping (Image → Board Plane)

## Overview

Map camera pixel coordinates to board coordinate system using intrinsic and extrinsic calibration. This enables converting detected dart tip positions from each camera's image space to a common board-centered coordinate system in millimeters.

## User Stories

### US-6.1: Intrinsic Camera Calibration
**As a** system operator  
**I want to** calibrate each camera's intrinsic parameters (camera matrix, distortion coefficients)  
**So that** I can correct for lens distortion and accurately map image coordinates to real-world coordinates

**Acceptance Criteria:**
- AC-6.1.1: Calibration script captures 20-30 chessboard images per camera at different angles
- AC-6.1.2: Calibration computes camera matrix and distortion coefficients using `cv2.calibrateCamera`
- AC-6.1.3: Reprojection error is less than 0.5 pixels for each camera
- AC-6.1.4: Calibration results saved to `calibration/intrinsic_cam{0,1,2}.json`
- AC-6.1.5: Calibration is one-time unless cameras are moved

### US-6.2: ARUCO Marker Setup
**As a** system operator  
**I want to** place ARUCO markers at known positions around the dartboard  
**So that** the system can automatically detect reference points for extrinsic calibration

**Acceptance Criteria:**
- AC-6.2.1: Generate 4-6 ARUCO markers from DICT_4X4_50 dictionary using provided script
- AC-6.2.2: Markers printed at ~40mm square size on white paper
- AC-6.2.3: Markers mounted at known positions (12, 3, 6, 9 o'clock) outside double ring (~200mm from center)
- AC-6.2.4: Marker positions and IDs documented in `config.toml`
- AC-6.2.5: Markers reliably detected in all 3 camera views
- AC-6.2.6: Detailed instructions provided for marker generation, printing, and mounting

### US-6.3: Extrinsic Calibration (Homography)
**As a** system operator  
**I want to** compute homography matrices mapping each camera's image plane to the board plane  
**So that** detected dart positions can be transformed to board coordinates

**Acceptance Criteria:**
- AC-6.3.1: System detects ARUCO markers in each camera view
- AC-6.3.2: Homography computed using `cv2.findHomography` with marker corners
- AC-6.3.3: Homography matrices saved per camera to `calibration/homography_cam{0,1,2}.json`
- AC-6.3.4: Extrinsic calibration runs at startup by default (fast, <1 second)
- AC-6.3.5: Manual calibration trigger available via `--calibrate` flag or API endpoint
- AC-6.3.6: System logs warning if markers not detected, uses last known calibration
- AC-6.3.7: Calibration can be triggered during runtime without restart

### US-6.4: Coordinate Transformation
**As a** developer  
**I want to** transform image coordinates (u, v) to board coordinates (x, y) in millimeters  
**So that** dart positions from different cameras can be compared and fused

**Acceptance Criteria:**
- AC-6.4.1: `CoordinateMapper` class loads intrinsic and homography parameters
- AC-6.4.2: `map_to_board(camera_id, u, v)` returns (x, y) in mm
- AC-6.4.3: Points are undistorted using intrinsic parameters before transformation
- AC-6.4.4: Board coordinate system: center (0, 0), +X right, +Y up
- AC-6.4.5: Transformation handles edge cases (points outside board, invalid homography)

### US-6.5: Calibration Verification
**As a** system operator  
**I want to** verify calibration accuracy using known control points  
**So that** I can ensure the coordinate mapping is accurate before using the system

**Acceptance Criteria:**
- AC-6.5.1: Verification script allows manual marking of known points (T20, D20, bull)
- AC-6.5.2: System maps marked points to board coordinates
- AC-6.5.3: Mapping error computed for each control point
- AC-6.5.4: Average mapping error is less than 5mm
- AC-6.5.5: Verification results logged and saved

## Board Specifications (Winmau Blade 6)

**Source**: Standard dartboard dimensions from [dartboardreview.com](https://dartboardreview.com/what-are-the-measurements-of-a-dart-board-ultimate-guide/) and [measuringstuff.com](https://measuringstuff.com/what-are-the-dimensions-of-a-dartboard-and-cabinet)

**Note**: These are standard dartboard dimensions that apply to Winmau Blade 6 and other regulation boards. Step 6 only handles coordinate mapping (pixel → mm). Score derivation (mm → sector/ring) is handled in Step 7.

- **Board diameter**: 451mm (17.75 inches) - regulation size
- **Board radius**: 170mm (from center to outer edge of double ring)
- **Bull (double bull)**: 12.7mm diameter (6.35mm radius)
- **Single bull**: 31.8mm diameter (15.9mm radius) - outer edge at 15.9mm from center
- **Triple ring**: 8mm wide, outer edge at 107mm from center (inner edge at 99mm)
- **Double ring**: 8mm wide, outer edge at 170mm from center (inner edge at 162mm)
- **Sector angles**: 20° wedges (18° scoring area + ~2° wire), starting at top for sector 20

**Clarification**: Step 6 provides coordinate mapping only. The actual score determination (which sector/ring) happens in Step 7 using these dimensions.

## Technical Constraints

- Calibration must work on both macOS (development) and Raspberry Pi (production)
- Chessboard pattern: 9×6 squares, 25mm each (printable on A4)
- ARUCO markers: DICT_4X4_50, IDs 0-5, 40mm square
- Homography assumes dart tips lie on board plane (ignoring dart tilt)
- Calibration files stored in JSON format for portability
- Calibration does NOT detect board features (spider web, sectors) - uses ARUCO markers only
- Manual calibration trigger must be available for recalibration without restart

## Dependencies

- OpenCV with ARUCO module (`cv2.aruco`)
- NumPy for matrix operations
- Existing camera capture system (Steps 1-2)
- Configuration system (`config.toml`)

## Success Metrics

- Intrinsic calibration reprojection error < 0.5 pixels
- ARUCO markers detected in 100% of startup attempts (with proper lighting)
- Control point mapping error < 5mm average
- Calibration completes in < 5 seconds at startup
- System gracefully handles missing markers (logs warning, continues with last known calibration)


---

## ARUCO Marker Generation Instructions

### What are ARUCO Markers?

ARUCO markers are square fiducial markers with unique black/white patterns that can be reliably detected by computer vision algorithms. We use them as reference points to calibrate the camera-to-board coordinate transformation.

### Generation Script

Create `calibration/generate_aruco_markers.py`:

```python
import cv2
import numpy as np
from pathlib import Path

def generate_aruco_markers(output_dir: str = "calibration/markers", 
                          marker_size_mm: int = 40,
                          dpi: int = 300):
    """
    Generate ARUCO markers for dartboard calibration.
    
    Args:
        output_dir: Directory to save marker images
        marker_size_mm: Size of each marker in millimeters
        dpi: Print resolution (dots per inch)
    """
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Use DICT_4X4_50 dictionary (4x4 bits, 50 unique markers)
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    
    # Calculate pixel size for given DPI
    # 1 inch = 25.4 mm, so marker_size_mm / 25.4 = inches
    # inches * dpi = pixels
    marker_size_px = int((marker_size_mm / 25.4) * dpi)
    
    # Generate markers 0-5 (we'll use 4, but generate extras)
    for marker_id in range(6):
        # Generate marker image
        marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_size_px)
        
        # Add white border (10% of marker size)
        border_size = marker_size_px // 10
        marker_with_border = cv2.copyMakeBorder(
            marker_img, 
            border_size, border_size, border_size, border_size,
            cv2.BORDER_CONSTANT, 
            value=255
        )
        
        # Save marker
        output_file = output_path / f"aruco_marker_{marker_id}.png"
        cv2.imwrite(str(output_file), marker_with_border)
        print(f"Generated marker {marker_id}: {output_file}")
    
    # Generate combined sheet with all markers
    generate_marker_sheet(output_path, aruco_dict, marker_size_px)
    
    print(f"\nMarkers saved to: {output_dir}")
    print(f"Marker size: {marker_size_mm}mm ({marker_size_px}px at {dpi} DPI)")
    print("\nPrinting instructions:")
    print("1. Print on white A4 paper at 100% scale (no scaling)")
    print("2. Verify printed size with ruler (should be 40mm)")
    print("3. Cut out markers leaving white border")
    print("4. Mount flat on rigid backing (cardboard/foam board)")

def generate_marker_sheet(output_path: Path, aruco_dict, marker_size_px: int):
    """Generate a single sheet with all 4 markers for easy printing."""
    # Create A4 sheet at 300 DPI (2480 x 3508 pixels)
    sheet_width = 2480
    sheet_height = 3508
    sheet = np.ones((sheet_height, sheet_width), dtype=np.uint8) * 255
    
    # Arrange 4 markers in 2x2 grid
    spacing = marker_size_px // 2
    positions = [
        (spacing, spacing),  # Top-left: Marker 0
        (sheet_width // 2 + spacing, spacing),  # Top-right: Marker 1
        (spacing, sheet_height // 2 + spacing),  # Bottom-left: Marker 2
        (sheet_width // 2 + spacing, sheet_height // 2 + spacing),  # Bottom-right: Marker 3
    ]
    
    for i, (x, y) in enumerate(positions):
        marker_img = cv2.aruco.generateImageMarker(aruco_dict, i, marker_size_px)
        sheet[y:y+marker_size_px, x:x+marker_size_px] = marker_img
        
        # Add marker ID label below marker
        label = f"ID: {i}"
        cv2.putText(sheet, label, (x, y + marker_size_px + 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2)
    
    # Save sheet
    output_file = output_path / "aruco_markers_sheet.png"
    cv2.imwrite(str(output_file), sheet)
    print(f"Generated marker sheet: {output_file}")

if __name__ == "__main__":
    generate_aruco_markers()
```

### Usage

```bash
# Generate markers
python calibration/generate_aruco_markers.py

# Output:
# calibration/markers/aruco_marker_0.png
# calibration/markers/aruco_marker_1.png
# calibration/markers/aruco_marker_2.png
# calibration/markers/aruco_marker_3.png
# calibration/markers/aruco_markers_sheet.png  (all 4 on one page)
```

### Printing Instructions

1. **Print Settings**:
   - Paper: White A4 (210mm × 297mm)
   - Quality: Best/High quality
   - Scale: 100% (no fit-to-page)
   - Color: Black & White

2. **Verification**:
   - Measure printed marker with ruler
   - Should be exactly 40mm × 40mm
   - If not, adjust DPI in script and reprint

3. **Preparation**:
   - Cut out each marker leaving white border
   - Mount on rigid backing (cardboard or foam board)
   - Ensure markers are perfectly flat (no wrinkles or bends)

### Mounting Instructions

**Marker Positions** (recommended):
- **Marker 0**: 12 o'clock (top), 200mm from board center
- **Marker 1**: 3 o'clock (right), 200mm from board center
- **Marker 2**: 6 o'clock (bottom), 200mm from board center
- **Marker 3**: 9 o'clock (left), 200mm from board center

**Mounting Process**:
1. Measure 200mm from board center in each direction
2. Mark positions on wall/mounting surface
3. Attach markers with tape or adhesive
4. Ensure markers are:
   - Flat against surface (no curling)
   - Parallel to board plane
   - Clearly visible from all 3 camera positions
   - Not occluded by LED ring or other objects

**Measurement Recording**:
After mounting, measure exact positions and record in `config.toml`:

```toml
[calibration.aruco_markers]
# Marker positions in board coordinates (mm from center)
# Format: [x, y] where (0, 0) is board center, +X right, +Y up
marker_0 = [0, 200]      # Top
marker_1 = [200, 0]      # Right
marker_2 = [0, -200]     # Bottom
marker_3 = [-200, 0]     # Left
```

---

## Calibration Timing and Triggers

### When Calibration Happens

**Automatic (Default)**:
- Extrinsic calibration runs at program startup
- Takes <1 second (ARUCO marker detection + homography computation)
- Uses last known intrinsic calibration (one-time setup)

**Manual Triggers**:
1. **Command-line flag**: `python main.py --calibrate`
   - Runs full calibration (intrinsic + extrinsic)
   - Useful after camera adjustment or marker repositioning

2. **Runtime API** (Step 9):
   - `POST /calibrate/intrinsic` - Run intrinsic calibration
   - `POST /calibrate/extrinsic` - Run extrinsic calibration
   - `GET /calibrate/status` - Check calibration status

3. **Keyboard shortcut** (dev mode):
   - Press 'c' to trigger extrinsic calibration
   - Useful for quick recalibration during testing

### Calibration Persistence

- **Intrinsic calibration**: Saved to `calibration/intrinsic_cam{0,1,2}.json`
  - One-time setup, valid until cameras are moved
  - Rerun if camera position/angle changes

- **Extrinsic calibration**: Saved to `calibration/homography_cam{0,1,2}.json`
  - Runs at startup by default
  - Rerun if markers are moved or board is adjusted
  - Can be triggered manually without restart

### Calibration Failure Handling

If calibration fails (markers not detected):
1. Log warning with details
2. Use last known good calibration
3. Continue operation (degraded mode)
4. Notify user via API/logs

---

## Clarifications on Calibration Approach

### What Calibration Does

**Step 6 (Coordinate Mapping)**:
- ✅ Maps pixel coordinates (u, v) to board coordinates (x, y) in millimeters
- ✅ Uses ARUCO markers as reference points
- ✅ Computes homography transformation
- ✅ Corrects for lens distortion
- ❌ Does NOT detect board features (sectors, rings, spider web)
- ❌ Does NOT determine scores (that's Step 7)

**Step 7 (Score Derivation)**:
- Uses board coordinates (x, y) from Step 6
- Converts to polar coordinates (r, θ)
- Determines ring based on radius (using dimensions above)
- Determines sector based on angle
- Computes final score

### Why Not Detect Board Features?

**Reasons for ARUCO marker approach**:
1. **Reliability**: Markers are easier to detect than thin wires
2. **Accuracy**: Markers provide precise reference points
3. **Flexibility**: Works even if board is rotated or offset
4. **Simplicity**: No need for complex feature detection
5. **Robustness**: Not affected by lighting, dart occlusion, or board wear

**Board feature detection challenges**:
- Spider web wires are thin (1-2mm) and reflective
- Sector colors can vary with lighting
- Darts may occlude features
- Board may have wear or damage
- More complex and error-prone

### Coordinate System

```
Board Coordinate System (after calibration):
         +Y (up)
          |
          |
    ------+------ +X (right)
          |
          |
       (0,0) = Board center
```

**Example**:
- Dart at (50, 100) mm → 50mm right, 100mm up from center
- Step 6 provides: (50, 100) mm
- Step 7 converts: r = 111.8mm, θ = 63.4° → determines sector and ring → score

---

## Success Metrics (Updated)

- Intrinsic calibration reprojection error < 0.5 pixels
- ARUCO markers detected in 100% of startup attempts (with proper lighting)
- Control point mapping error < 5mm average
- Extrinsic calibration completes in < 1 second at startup
- Manual calibration trigger works without restart
- System gracefully handles missing markers (logs warning, uses last known calibration)
