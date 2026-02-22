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
    marker_size_mm: int = 40,
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
    
    # Generate markers 0-5 (we'll use 4, but generate extras for redundancy)
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
        print(f"  Generated marker {marker_id}: {output_file}")
    
    print()
    
    # Generate combined sheet with all 4 markers
    generate_marker_sheet(output_path, aruco_dict, marker_size_px, dpi)
    
    # Print summary and instructions
    print_instructions(output_dir, marker_size_mm, marker_size_px, dpi)


def generate_marker_sheet(
    output_path: Path,
    aruco_dict,
    marker_size_px: int,
    dpi: int
) -> None:
    """
    Generate a single sheet with all 4 markers for easy printing.
    
    Args:
        output_path: Directory to save the sheet
        aruco_dict: ARUCO dictionary object
        marker_size_px: Marker size in pixels
        dpi: Print resolution
    """
    # Create A4 sheet at specified DPI
    # A4 = 210mm x 297mm
    # At 300 DPI: 2480 x 3508 pixels
    sheet_width = int((210 / 25.4) * dpi)   # 2480 at 300 DPI
    sheet_height = int((297 / 25.4) * dpi)  # 3508 at 300 DPI
    sheet = np.ones((sheet_height, sheet_width), dtype=np.uint8) * 255
    
    # Calculate spacing for 2x2 grid with good margins
    margin = marker_size_px
    spacing_x = (sheet_width - 2 * marker_size_px - 2 * margin) // 2
    spacing_y = (sheet_height - 2 * marker_size_px - 2 * margin) // 2
    
    # Arrange 4 markers in 2x2 grid
    positions = [
        (margin, margin),                                    # Top-left: Marker 0
        (margin + marker_size_px + spacing_x, margin),       # Top-right: Marker 1
        (margin, margin + marker_size_px + spacing_y),       # Bottom-left: Marker 2
        (margin + marker_size_px + spacing_x, margin + marker_size_px + spacing_y),  # Bottom-right: Marker 3
    ]
    
    # Marker placement descriptions for labeling
    placements = [
        "Top (12 o'clock)",
        "Right (3 o'clock)",
        "Bottom (6 o'clock)",
        "Left (9 o'clock)"
    ]
    
    for i, (x, y) in enumerate(positions):
        # Generate marker
        marker_img = cv2.aruco.generateImageMarker(aruco_dict, i, marker_size_px)
        
        # Place marker on sheet
        sheet[y:y + marker_size_px, x:x + marker_size_px] = marker_img
        
        # Add marker ID label below marker
        label = f"ID: {i} - {placements[i]}"
        font_scale = 0.8
        thickness = 2
        cv2.putText(
            sheet, label,
            (x, y + marker_size_px + 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale, 0, thickness
        )
    
    # Add title at top
    title = "ARU-DART Calibration Markers - DICT_4X4_50"
    cv2.putText(
        sheet, title,
        (margin, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0, 0, 2
    )
    
    # Add instructions at bottom
    instructions = [
        "Print at 100% scale (no fit-to-page). Verify 40mm size with ruler.",
        "Cut out markers leaving white border. Mount flat on rigid backing."
    ]
    y_pos = sheet_height - 100
    for instruction in instructions:
        cv2.putText(
            sheet, instruction,
            (margin, y_pos),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6, 0, 1
        )
        y_pos += 35
    
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
    
    print("=" * 70)
    print("ARUCO MARKER GENERATION COMPLETE")
    print("=" * 70)
    print()
    print(f"Output directory: {output_dir}")
    print(f"Marker size: {marker_size_mm}mm ({marker_size_px}px at {dpi} DPI)")
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
    print(f"   - Measure printed marker with ruler")
    print(f"   - Should be exactly {marker_size_mm}mm × {marker_size_mm}mm")
    print("   - If size is wrong, check print settings and reprint")
    print()
    print("3. PREPARATION:")
    print("   - Cut out each marker leaving white border intact")
    print("   - Mount on rigid backing (cardboard or foam board)")
    print("   - Ensure markers are perfectly flat (no wrinkles or bends)")
    print()
    print("-" * 70)
    print("MOUNTING INSTRUCTIONS")
    print("-" * 70)
    print()
    print("Marker positions (200mm from board center):")
    print("   - Marker 0: 12 o'clock (top)")
    print("   - Marker 1:  3 o'clock (right)")
    print("   - Marker 2:  6 o'clock (bottom)")
    print("   - Marker 3:  9 o'clock (left)")
    print()
    print("Mounting process:")
    print("   1. Measure 200mm from board center in each direction")
    print("   2. Mark positions on wall/mounting surface")
    print("   3. Attach markers with tape or adhesive")
    print("   4. Ensure markers are:")
    print("      - Flat against surface (no curling)")
    print("      - Parallel to board plane")
    print("      - Clearly visible from all 3 camera positions")
    print("      - Not occluded by LED ring or other objects")
    print()
    print("-" * 70)
    print("CONFIGURATION")
    print("-" * 70)
    print()
    print("After mounting, verify positions in config.toml:")
    print()
    print("  [calibration.aruco_markers]")
    print("  marker_0 = [0.0, 200.0]      # Top (12 o'clock)")
    print("  marker_1 = [200.0, 0.0]      # Right (3 o'clock)")
    print("  marker_2 = [0.0, -200.0]     # Bottom (6 o'clock)")
    print("  marker_3 = [-200.0, 0.0]     # Left (9 o'clock)")
    print()
    print("-" * 70)
    print("VERIFICATION CHECKLIST")
    print("-" * 70)
    print()
    print("Before running calibration, verify:")
    print("  [ ] Markers printed at correct size (40mm)")
    print("  [ ] Markers mounted flat and parallel to board")
    print("  [ ] Markers visible from all 3 camera positions")
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
        default=40,
        help="Marker size in millimeters (default: 40)"
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
