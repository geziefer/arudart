#!/usr/bin/env python3
"""
Ground Truth Annotation Tool

Annotate dart tip positions in recorded images by clicking.
Creates ground truth JSON files for regression testing.

Usage:
    python tools/annotate_ground_truth.py
"""

import cv2
import json
from pathlib import Path
import sys

# Global variables for mouse callback
click_x = None
click_y = None
mouse_x = 0
mouse_y = 0


def mouse_callback(event, x, y, flags, param):
    """Handle mouse events for tip position selection."""
    global click_x, click_y, mouse_x, mouse_y
    
    mouse_x = x
    mouse_y = y
    
    if event == cv2.EVENT_LBUTTONDOWN:
        click_x = x
        click_y = y


def get_unannotated_images(recordings_dir):
    """Find all POST images without matching ground truth JSON files."""
    image_files = sorted(recordings_dir.glob("*_post.jpg"))
    unannotated = []
    
    for img_file in image_files:
        json_file = img_file.with_suffix('.json')
        if not json_file.exists():
            unannotated.append(img_file)
    
    return unannotated


def group_by_recording_number(image_files):
    """Group images by recording number (e.g., all 001_cam*_*.jpg together)."""
    groups = {}
    
    for img_file in image_files:
        # Extract recording number from filename (e.g., "001" from "001_cam0_description.jpg")
        parts = img_file.stem.split('_')
        if len(parts) >= 2 and parts[0].isdigit():
            rec_num = parts[0]
            if rec_num not in groups:
                groups[rec_num] = []
            groups[rec_num].append(img_file)
    
    # Sort each group by camera ID (cam0, cam1, cam2)
    for rec_num in groups:
        groups[rec_num].sort()
    
    return groups


def annotate_image(img_file):
    """Annotate a single image by clicking on dart tip position."""
    global click_x, click_y, mouse_x, mouse_y
    
    # Reset click position
    click_x = None
    click_y = None
    
    # Load image
    image = cv2.imread(str(img_file))
    if image is None:
        print(f"Error: Could not load {img_file}")
        return None
    
    # Create window and set mouse callback
    window_name = "Annotate Ground Truth"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1024, 768)
    cv2.setMouseCallback(window_name, mouse_callback)
    
    print(f"\nAnnotating: {img_file.name}")
    print("Click on dart tip position")
    print("Press 's' to save, 'n' to skip (no dart visible), 'q' to quit")
    
    while True:
        # Create display image with crosshair at mouse position
        display = image.copy()
        
        # Draw crosshair at mouse position
        cv2.line(display, (mouse_x - 20, mouse_y), (mouse_x + 20, mouse_y), (0, 255, 255), 1)
        cv2.line(display, (mouse_x, mouse_y - 20), (mouse_x, mouse_y + 20), (0, 255, 255), 1)
        
        # Create magnified inset (4x zoom, 150x150 px region)
        zoom_size = 150
        zoom_factor = 4
        roi_size = zoom_size // zoom_factor  # 37x37 px region
        
        # Extract ROI around mouse position
        x1 = max(0, mouse_x - roi_size // 2)
        y1 = max(0, mouse_y - roi_size // 2)
        x2 = min(image.shape[1], mouse_x + roi_size // 2)
        y2 = min(image.shape[0], mouse_y + roi_size // 2)
        
        roi = image[y1:y2, x1:x2]
        
        if roi.size > 0:
            # Resize ROI to zoom_size
            zoomed = cv2.resize(roi, (zoom_size, zoom_size), interpolation=cv2.INTER_LINEAR)
            
            # Draw crosshair in center of zoomed view
            center = zoom_size // 2
            cv2.line(zoomed, (center - 30, center), (center + 30, center), (0, 255, 255), 2)
            cv2.line(zoomed, (center, center - 30), (center, center + 30), (0, 255, 255), 2)
            cv2.circle(zoomed, (center, center), 3, (0, 255, 255), -1)
            
            # Add border to zoomed view
            cv2.rectangle(zoomed, (0, 0), (zoom_size - 1, zoom_size - 1), (255, 255, 255), 2)
            
            # Place zoomed view in top-right corner
            margin = 10
            y_offset = margin
            x_offset = display.shape[1] - zoom_size - margin
            display[y_offset:y_offset + zoom_size, x_offset:x_offset + zoom_size] = zoomed
            
            # Add label
            cv2.putText(display, "4x ZOOM", (x_offset, y_offset - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        
        # If clicked, show the selected position
        if click_x is not None:
            cv2.circle(display, (click_x, click_y), 5, (0, 255, 0), -1)
            cv2.circle(display, (click_x, click_y), 10, (0, 255, 0), 2)
            cv2.putText(display, f"Tip: ({click_x}, {click_y})", (click_x + 15, click_y - 15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Show instructions
        cv2.putText(display, img_file.name, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(display, "Click on dart tip | 's'=save | 'n'=skip | 'q'=quit", (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        
        cv2.imshow(window_name, display)
        
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('s'):
            if click_x is not None:
                cv2.destroyWindow(window_name)
                return (click_x, click_y)
            else:
                print("No position selected! Click on tip first.")
        elif key == ord('n'):
            print("Skipped (no dart visible)")
            cv2.destroyWindow(window_name)
            return None
        elif key == ord('q'):
            cv2.destroyWindow(window_name)
            return 'quit'


def parse_sector_from_description(description):
    """
    Parse sector information from description.
    
    Examples:
        "BS_20" or "BS20" -> {"ring": "BS", "number": 20}
        "T_20" or "T20" -> {"ring": "T", "number": 20}
        "SB_right" or "SB-up" -> {"ring": "SB", "number": 25}
        "DB" -> {"ring": "DB", "number": 50}
    
    Returns:
        dict with "ring" and "number", or None if can't parse
    """
    # Handle bulls first (special cases)
    if description.upper().startswith("SB"):
        return {"ring": "SB", "number": 25}
    elif description.upper() == "DB":
        return {"ring": "DB", "number": 50}
    
    # Try to extract ring and number
    # Support both "BS_20" and "BS20" formats
    import re
    match = re.match(r'^([A-Z]+)[-_]?(\d+)', description.upper())
    
    if match:
        ring = match.group(1)
        try:
            number = int(match.group(2))
            if 1 <= number <= 20:
                return {"ring": ring, "number": number}
        except ValueError:
            pass
    
    return None


def save_ground_truth(img_file, tip_x, tip_y):
    """Save ground truth JSON file."""
    # Extract description from filename
    parts = img_file.stem.split('_', 2)  # Split into [number, cam, description]
    description = parts[2] if len(parts) >= 3 else "unknown"
    
    # Parse sector information
    sector_info = parse_sector_from_description(description)
    
    ground_truth = {
        "image": img_file.name,
        "tip_x": tip_x,
        "tip_y": tip_y,
        "description": description
    }
    
    # Add sector information if parsed successfully
    if sector_info:
        ground_truth["expected_ring"] = sector_info["ring"]
        ground_truth["expected_number"] = sector_info["number"]
    
    json_file = img_file.with_suffix('.json')
    with open(json_file, 'w') as f:
        json.dump(ground_truth, f, indent=2)
    
    print(f"Saved: {json_file.name}", end="")
    if sector_info:
        print(f" [{sector_info['ring']}_{sector_info['number']}]")
    else:
        print()



def main():
    recordings_dir = Path("data/recordings")
    
    if not recordings_dir.exists():
        print(f"Error: {recordings_dir} does not exist")
        print("Run recording mode first to capture images")
        return
    
    # Find unannotated images
    unannotated = get_unannotated_images(recordings_dir)
    
    if not unannotated:
        print("No unannotated images found!")
        print("All images have ground truth annotations.")
        return
    
    # Group by recording number
    groups = group_by_recording_number(unannotated)
    
    total_images = len(unannotated)
    print(f"\nFound {total_images} unannotated images in {len(groups)} recordings")
    print("=" * 60)
    
    annotated_count = 0
    skipped_count = 0
    
    # Process each recording group (cam0, cam1, cam2 in sequence)
    for rec_num in sorted(groups.keys()):
        images = groups[rec_num]
        
        print(f"\n--- Recording {rec_num} ({len(images)} cameras) ---")
        
        for img_file in images:
            result = annotate_image(img_file)
            
            if result == 'quit':
                print(f"\nQuitting. Annotated: {annotated_count}, Skipped: {skipped_count}")
                return
            elif result is not None:
                tip_x, tip_y = result
                save_ground_truth(img_file, tip_x, tip_y)
                annotated_count += 1
            else:
                skipped_count += 1
    
    print("\n" + "=" * 60)
    print(f"Annotation complete!")
    print(f"Annotated: {annotated_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Total: {annotated_count + skipped_count}")


if __name__ == "__main__":
    main()
