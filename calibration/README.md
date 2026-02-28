# Calibration Directory

This directory stores calibration data for the ARU-DART coordinate mapping system.

## File Structure

### Intrinsic Calibration Files
- `intrinsic_cam0.json` - Camera matrix and distortion coefficients for cam0
- `intrinsic_cam1.json` - Camera matrix and distortion coefficients for cam1
- `intrinsic_cam2.json` - Camera matrix and distortion coefficients for cam2

### Homography Files
- `homography_cam0.json` - Homography matrix for cam0 (pixel to board coordinates)
- `homography_cam1.json` - Homography matrix for cam1 (pixel to board coordinates)
- `homography_cam2.json` - Homography matrix for cam2 (pixel to board coordinates)

## Calibration Workflow

1. **Intrinsic Calibration** (once per camera, unless camera moves):
   ```bash
   python calibration/calibrate_intrinsic.py --camera 0
   ```
   - Uses chessboard pattern (9×6 inner corners, 25mm squares)
   - Captures 20-30 images at different angles
   - Computes camera matrix and distortion coefficients
   - Saves to `intrinsic_cam{N}.json`

2. **Spiderweb Calibration** (extrinsic, per camera):
   ```bash
   python calibration/calibrate_spiderweb.py
   ```
   - Detects dartboard features (bull, rings, radial wires)
   - Matches features to known board coordinates
   - Computes homography matrix
   - Saves to `homography_cam{N}.json`

3. **Verification**:
   ```bash
   python calibration/verify_calibration.py
   ```
   - Interactive tool to click known points (T20, D20, bull)
   - Displays transformed board coordinates
   - Reports mapping error

## File Formats

### intrinsic_cam{N}.json
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

### homography_cam{N}.json
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

## Board Specifications (Winmau Blade 6)

Standard dartboard dimensions used for calibration:
- **Double Bull radius**: 6.35mm
- **Single Bull outer radius**: 15.9mm
- **Triple ring inner radius**: 99mm
- **Triple ring outer radius**: 107mm
- **Double ring inner radius**: 162mm
- **Double ring outer radius**: 170mm
- **Sector width**: 18° each (360° / 20 sectors)
- **Sector 20 position**: Top (12 o'clock, 0° in board coordinates)

## Camera Positions

- **cam0**: Upper right (near sector 18, ~1 o'clock)
- **cam1**: Lower right (near sector 17, ~5 o'clock)
- **cam2**: Left (near sector 11, ~9 o'clock)

Each camera has its own homography due to different viewing angles.
