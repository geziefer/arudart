# Manual Calibration Guide

This guide explains how to run manual calibration for the ARU-DART coordinate mapping system.

## Prerequisites

1. All 3 cameras connected and working
2. Dartboard clearly visible in all camera views
3. Good lighting (LED ring on)
4. No darts in the board

## Running Calibration

### Calibrate All Cameras

```bash
python calibration/calibrate_manual.py
```

This will calibrate all 3 cameras sequentially (cam0, cam1, cam2).

### Calibrate Single Camera

```bash
python calibration/calibrate_manual.py --camera 0  # Calibrate cam0 only
python calibration/calibrate_manual.py --camera 1  # Calibrate cam1 only
python calibration/calibrate_manual.py --camera 2  # Calibrate cam2 only
```

## Calibration Process

For each camera, you'll see an interactive window with the camera view.

### Control Points

You'll be prompted to click on 11 standard control points in order:

1. **BULL** - Bull center (center of the board)
2. **T20** - Triple 20 (top of board)
3. **T5** - Triple 5 (left side)
4. **T1** - Triple 1 (right side)
5. **D20** - Double 20 (top outer ring)
6. **D5** - Double 5 (left outer ring)
7. **D1** - Double 1 (right outer ring)
8. **S18** - Single 18 (upper right)
9. **S4** - Single 4 (upper left)
10. **S13** - Single 13 (lower left)
11. **S6** - Single 6 (lower right)

### Minimum Points

You need at least 4 points for calibration, but more points improve accuracy. We recommend clicking all 11 points.

### Interactive Controls

- **Left Click** - Click on the prompted control point
- **'d' key** - Delete the last clicked point (if you made a mistake)
- **'s' key** - Toggle spiderweb overlay (shows projected dartboard geometry)
- **'q' key** - Finish calibration (minimum 4 points required)

### Visual Feedback

- **Green points** - Good reprojection error (<10px)
- **Red points** - Outliers (>10px error) - consider re-clicking these
- **Yellow spiderweb** - Projected dartboard geometry (toggle with 's')
- **Error stats** - Average and max reprojection errors shown at bottom

### Tips for Accurate Calibration

1. **Click precisely** - Try to click exactly on the wire intersections
2. **Use spiderweb overlay** - Toggle with 's' to verify alignment
3. **Check errors** - If you see red points (>10px error), delete and re-click them
4. **Add more points** - More points = better accuracy
5. **Target <5mm error** - Aim for average reprojection error under 5mm

## Output Files

Calibration creates JSON files in the `calibration/` directory:

- `homography_cam0.json` - Homography matrix for cam0
- `homography_cam1.json` - Homography matrix for cam1
- `homography_cam2.json` - Homography matrix for cam2

Each file contains:
- Homography matrix (3x3)
- Number of points used
- Number of inliers (RANSAC)
- Reprojection error in millimeters
- Timestamp

## Troubleshooting

### Camera not found
- Check USB connections
- Verify cameras are detected: `ls /dev/video*` (Linux) or check System Preferences (macOS)

### High reprojection error (>10mm)
- Re-run calibration with more careful clicking
- Ensure dartboard is clearly visible
- Check lighting conditions
- Make sure board is not moving

### Spiderweb doesn't align
- Delete outlier points (red) and re-click them
- Add more control points for better coverage
- Ensure you're clicking on the correct features

### "Insufficient points" error
- You need at least 4 points
- Click more control points before pressing 'q'

## Next Steps

After calibration:

1. Verify calibration accuracy using `calibration/verify_calibration.py` (coming soon)
2. Integrate coordinate mapping into main.py
3. Test with actual dart throws

## Re-calibration

You should re-calibrate if:
- Cameras are moved or adjusted
- Dartboard is moved
- Lighting conditions change significantly
- Coordinate mapping accuracy degrades over time
