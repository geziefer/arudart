#!/usr/bin/env python3
"""
Combine multiple throw images into a grid for documentation.
Usage: python combine_images.py <session_folder> <output_file>
Example: python combine_images.py data/throws/Session_002_2026-01-03_17-16-24 docs/tc3_orientation_test.jpg
"""

import cv2
import numpy as np
import sys
from pathlib import Path


def combine_images_grid(session_folder, output_file, rows=3, cols=3):
    """Combine throw images into a grid."""
    session_path = Path(session_folder)
    
    # Get all throw folders sorted by number
    throw_folders = sorted(session_path.glob("Throw_*"), 
                          key=lambda x: int(x.name.split('_')[1]))
    
    if len(throw_folders) == 0:
        print(f"No throw folders found in {session_folder}")
        return False
    
    # Limit to rows * cols images
    throw_folders = throw_folders[:rows * cols]
    
    print(f"Found {len(throw_folders)} throws")
    
    # Load all images
    images = []
    for throw_folder in throw_folders:
        # Try to find annotated image
        annotated = throw_folder / "cam0_annotated.jpg"
        if not annotated.exists():
            print(f"Warning: {annotated} not found, skipping")
            continue
        
        img = cv2.imread(str(annotated))
        if img is None:
            print(f"Warning: Could not load {annotated}")
            continue
        
        images.append(img)
        print(f"Loaded: {throw_folder.name}")
    
    if len(images) == 0:
        print("No images loaded")
        return False
    
    # Get dimensions (assume all images same size)
    h, w = images[0].shape[:2]
    
    # Create grid
    grid_rows = []
    for row_idx in range(rows):
        row_images = []
        for col_idx in range(cols):
            img_idx = row_idx * cols + col_idx
            if img_idx < len(images):
                row_images.append(images[img_idx])
            else:
                # Fill with black if not enough images
                row_images.append(np.zeros((h, w, 3), dtype=np.uint8))
        
        # Concatenate horizontally
        row_combined = np.hstack(row_images)
        grid_rows.append(row_combined)
    
    # Concatenate vertically
    grid = np.vstack(grid_rows)
    
    # Create output directory if needed
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save
    cv2.imwrite(str(output_path), grid)
    print(f"\nSaved combined image to: {output_path}")
    print(f"Grid size: {grid.shape[1]}x{grid.shape[0]} pixels")
    
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python combine_images.py <session_folder> <output_file>")
        print("Example: python combine_images.py data/throws/Session_002_2026-01-03_17-16-24 docs/tc3_orientation_test.jpg")
        sys.exit(1)
    
    session_folder = sys.argv[1]
    output_file = sys.argv[2]
    
    success = combine_images_grid(session_folder, output_file)
    sys.exit(0 if success else 1)
