#!/usr/bin/env python3
"""
ARUCO Marker Generation Script for ARU-DART Calibration

Generates ARUCO markers from DICT_4X4_50 dictionary for dartboard calibration.
Markers are used as reference points for extrinsic calibration (homography computation).

Usage:
    python calibration/generate_aruco_markers.py

Output:
    calibration/markers/aruco_marker_0.png  (individual markers)
    calibration/markers/aruco_marker_1.png
    calibration/markers/aruco_marker_2.png
    calibration/markers/aruco_marker_3.png
    calibration/markers/aruco_marker_4.png
    calibration/markers/aruco_marker_5.png
    calibration/markers/aruco_markers_sheet.png  (all 4 on one page)

Requirements: AC-6.2.1, AC-6.2.6
"""

import cv2
import numpy as np
from pathlib import Path


def generate_aruco_markers(
    output_dir: str = "calibration/markers",
    marker_size_mm: int = 20,
    dpi: int = 300
) -> None:
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
    
    print(f"Generating ARUCO markers...")
    print(f"  Dictionary: DICT_4X4_50")
    print(f"  Marker size: {marker_size_mm}mm ({marker_size_px}px at {dpi} DPI)")
    print()
    
    # Generate markers 0-7 (8 markers at 45° intervals)
    for marker_id in range(8):
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
        print(f"  Generated marker {marker_id}: {output_file}")
    
    print()
    
    # Generate combined sheet with all 4 markers
    generate_marker_sheet(output_path, aruco_dict, marker_size_px, dpi, marker_size_mm)
    
    # Print summary and instructions
    print_instructions(output_dir, marker_size_mm, marker_size_px, dpi)


def generate_marker_sheet(
    output_path: Path,
    aruco_dict,
    marker_size_px: int,
    dpi: int,
    marker_size_mm: int
) -> None:
    """
    Generate a single sheet with all 8 markers.
    
    Args:
        output_path: Directory to save the sheet
        aruco_dict: ARUCO dictionary object
        marker_size_px: Marker size in pixels
        dpi: Print resolution
        marker_size_mm: Marker size in mm for label
    """
    # Create A4 sheet at specified DPI
    sheet_width = int((210 / 25.4) * dpi)
    sheet_height = int((297 / 25.4) * dpi)
    sheet = np.ones((sheet_height, sheet_width), dtype=np.uint8) * 255
    
    # All 8 markers with positions (clockwise from top)
    placements = [
        "ID 0: Top (12 o'clock)",
        "ID 1: Right (3 o'clock)",
        "ID 2: Bottom (6 o'clock)",
        "ID 3: Left (9 o'clock)",
        "ID 4: Top-right (1:30)",
        "ID 5: Bottom-right (4:30)",
        "ID 6: Bottom-left (7:30)",
        "ID 7: Top-left (10:30)"
    ]
    
    # Calculate spacing for 4x2 grid
    margin_x = marker_size_px // 2
    margin_y = marker_size_px
    cols = 4
    rows = 2
    spacing_x = (sheet_width - cols * marker_size_px - 2 * margin_x) // (cols - 1)
    spacing_y = (sheet_height - rows * marker_size_px - 2 * margin_y - 150) // (rows - 1)
    
    for marker_id in range(8):
        col = marker_id % cols
        row = marker_id // cols
        x = margin_x + col * (marker_size_px + spacing_x)
        y = margin_y + 80 + row * (marker_size_px + spacing_y + 60)
        
        marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_size_px)
        sheet[y:y + marker_size_px, x:x + marker_size_px] = marker_img
        
        # Add label below marker
        label = placements[marker_id]
        font_scale = 0.5
        thickness = 1
        cv2.putText(
            sheet, label,
            (x, y + marker_size_px + 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale, 0, thickness
        )
    
    # Add title at top
    title = f"ARU-DART Calibration Markers ({marker_size_mm}mm)"
    cv2.putText(
        sheet, title,
        (margin_x, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0, 0, 2
    )
    
    # Add instructions at bottom
    border_mm = marker_size_mm // 5
    total_mm = marker_size_mm + 2 * border_mm
    instructions = [
        f"Print at 100% scale. Black square = {marker_size_mm}mm, total with border = {total_mm}mm.",
        "Mount at 185mm from board center in gap between double ring and numbers."
    ]
    y_pos = sheet_height - 80
    for instruction in instructions:
        cv2.putText(
            sheet, instruction,
            (margin_x, y_pos),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5, 0, 1
        )
        y_pos += 30
    
    # Save sheet
    output_file = output_path / "aruco_markers_sheet.png"
    cv2.imwrite(str(output_file), sheet)
    print(f"  Generated marker sheet: {output_file}")


def print_instructions(
    output_dir: str,
    marker_size_mm: int,
    marker_size_px: int,
    dpi: int
) -> None:
    """Print detailed instructions for marker usage."""
    
    border_mm = marker_size_mm // 5
    total_mm = marker_size_mm + 2 * border_mm
    
    print("=" * 70)
    print("ARUCO MARKER GENERATION COMPLETE")
    print("=" * 70)
    print()
    print(f"Output directory: {output_dir}")
    print(f"Marker size: {marker_size_mm}mm black square + {border_mm}mm border = {total_mm}mm total")
    print(f"Resolution: {marker_size_px}px at {dpi} DPI")
    print()
    print("-" * 70)
    print("PRINTING INSTRUCTIONS")
    print("-" * 70)
    print()
    print("1. PRINT SETTINGS:")
    print("   - Paper: White A4 (210mm × 297mm)")
    print("   - Quality: Best/High quality")
    print("   - Scale: 100% (NO fit-to-page, NO scaling)")
    print("   - Color: Black & White")
    print()
    print("2. VERIFICATION:")
    print(f"   - Measure printed marker black square with ruler")
    print(f"   - Black square should be exactly {marker_size_mm}mm × {marker_size_mm}mm")
    print(f"   - Total with white border should be {total_mm}mm × {total_mm}mm")
    print("   - If size is wrong, check print settings and reprint")
    print()
    print("3. PREPARATION:")
    print("   - Cut out each marker leaving white border intact")
    print("   - Mount on board in gap between double ring and number ring")
    print("   - Ensure markers are flat against board surface")
    print()
    print("-" * 70)
    print("MOUNTING INSTRUCTIONS")
    print("-" * 70)
    print()
    print("8 markers at 185mm from board center (clockwise from top):")
    print("   - Marker 0: Top (12 o'clock)")
    print("   - Marker 1: Right (3 o'clock)")
    print("   - Marker 2: Bottom (6 o'clock)")
    print("   - Marker 3: Left (9 o'clock)")
    print("   - Marker 4: Top-right (1:30)")
    print("   - Marker 5: Bottom-right (4:30)")
    print("   - Marker 6: Bottom-left (7:30)")
    print("   - Marker 7: Top-left (10:30)")
    print()
    print("-" * 70)
    print("CONFIGURATION")
    print("-" * 70)
    print()
    print("After mounting, update config.toml with actual measured positions:")
    print()
    print("  [calibration.aruco_markers]")
    print("  marker_0 = [0.0, 185.0]        # Top (12 o'clock)")
    print("  marker_1 = [185.0, 0.0]        # Right (3 o'clock)")
    print("  marker_2 = [0.0, -185.0]       # Bottom (6 o'clock)")
    print("  marker_3 = [-185.0, 0.0]       # Left (9 o'clock)")
    print("  marker_4 = [130.8, 130.8]      # Top-right (1:30)")
    print("  marker_5 = [130.8, -130.8]     # Bottom-right (4:30)")
    print("  marker_6 = [-130.8, -130.8]    # Bottom-left (7:30)")
    print("  marker_7 = [-130.8, 130.8]     # Top-left (10:30)")
    print()
    print("-" * 70)
    print("VERIFICATION CHECKLIST")
    print("-" * 70)
    print()
    print(f"Before running calibration, verify:")
    print(f"  [ ] Markers printed at correct size ({marker_size_mm}mm black square)")
    print("  [ ] Markers placed in gap between double ring and numbers")
    print("  [ ] At least 4 markers visible from each camera")
    print("  [ ] Marker positions recorded in config.toml")
    print("  [ ] Good lighting (markers clearly visible, no glare)")
    print()
    print("=" * 70)


def verify_marker_detection(image_path: str) -> None:
    """
    Utility function to verify marker detection in an image.
    
    Args:
        image_path: Path to image containing markers
    """
    image = cv2.imread(image_path)
    if image is None:
        print(f"Error: Could not load image: {image_path}")
        return
    
    # Detect markers
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    detector_params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, detector_params)
    
    corners, ids, rejected = detector.detectMarkers(image)
    
    if ids is not None:
        print(f"Detected {len(ids)} markers: {ids.flatten().tolist()}")
        
        # Draw detected markers
        cv2.aruco.drawDetectedMarkers(image, corners, ids)
        
        # Show result
        cv2.imshow("Detected Markers", image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    else:
        print("No markers detected")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate ARUCO markers for ARU-DART calibration"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="calibration/markers",
        help="Output directory for marker images (default: calibration/markers)"
    )
    parser.add_argument(
        "--size", "-s",
        type=int,
        default=20,
        help="Marker size in millimeters (default: 20)"
    )
    parser.add_argument(
        "--dpi", "-d",
        type=int,
        default=300,
        help="Print resolution in DPI (default: 300)"
    )
    parser.add_argument(
        "--verify",
        type=str,
        metavar="IMAGE",
        help="Verify marker detection in an image (for testing)"
    )
    
    args = parser.parse_args()
    
    if args.verify:
        verify_marker_detection(args.verify)
    else:
        generate_aruco_markers(
            output_dir=args.output_dir,
            marker_size_mm=args.size,
            dpi=args.dpi
        )
