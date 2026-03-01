"""
Find board center by detecting where sector boundaries intersect.

This is a more robust approach that uses the geometric structure of the dartboard.
All sector boundaries (radial lines) converge at the bull center.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import cv2
import numpy as np

# Test image
test_image = 'data/testimages/BS/BS10_cam0_pre.jpg'
print(f"Analyzing: {test_image}\n")

image = cv2.imread(test_image)
if image is None:
    print("Failed to load image")
    sys.exit(1)

# Convert to grayscale
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Apply Canny edge detection
edges = cv2.Canny(gray, 50, 150)

# Detect lines using Hough Line Transform
# These should include the sector boundaries (radial lines)
lines = cv2.HoughLinesP(
    edges,
    rho=1,
    theta=np.pi/180,
    threshold=50,
    minLineLength=50,
    maxLineGap=10
)

print(f"Detected {len(lines) if lines is not None else 0} lines")

if lines is not None:
    # Find intersection points of lines
    # Lines that are part of the radial structure should intersect near the bull center
    
    intersections = []
    
    for i in range(len(lines)):
        for j in range(i+1, len(lines)):
            x1, y1, x2, y2 = lines[i][0]
            x3, y3, x4, y4 = lines[j][0]
            
            # Compute intersection of two lines
            # Line 1: (x1,y1) to (x2,y2)
            # Line 2: (x3,y3) to (x4,y4)
            
            denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
            
            if abs(denom) < 1e-6:
                continue  # Lines are parallel
            
            t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
            
            # Intersection point
            ix = x1 + t*(x2-x1)
            iy = y1 + t*(y2-y1)
            
            # Only consider intersections within image bounds
            if 0 <= ix < image.shape[1] and 0 <= iy < image.shape[0]:
                intersections.append((ix, iy))
    
    print(f"Found {len(intersections)} line intersections")
    
    if intersections:
        # Cluster intersections - the bull center should be where many lines intersect
        intersections = np.array(intersections)
        
        # Use mean shift or simple clustering
        # For simplicity, find the region with highest density of intersections
        
        # Create a 2D histogram
        hist, xedges, yedges = np.histogram2d(
            intersections[:, 0],
            intersections[:, 1],
            bins=[image.shape[1]//10, image.shape[0]//10]
        )
        
        # Find the bin with maximum intersections
        max_bin = np.unravel_index(np.argmax(hist), hist.shape)
        
        # Convert bin to pixel coordinates
        center_x = (xedges[max_bin[0]] + xedges[max_bin[0]+1]) / 2
        center_y = (yedges[max_bin[1]] + yedges[max_bin[1]+1]) / 2
        
        print(f"\nEstimated board center from line intersections:")
        print(f"  ({center_x:.1f}, {center_y:.1f})")
        
        # Compare with image center
        image_center = (image.shape[1] / 2, image.shape[0] / 2)
        dist = np.sqrt((center_x - image_center[0])**2 + (center_y - image_center[1])**2)
        print(f"  Distance from image center: {dist:.1f} pixels")
        
        # Visualize
        vis = image.copy()
        
        # Draw all intersections
        for ix, iy in intersections[:100]:  # Limit to first 100
            cv2.circle(vis, (int(ix), int(iy)), 2, (0, 255, 255), -1)
        
        # Draw estimated center
        cv2.circle(vis, (int(center_x), int(center_y)), 10, (0, 255, 0), 2)
        cv2.putText(vis, "ESTIMATED CENTER", (int(center_x) + 15, int(center_y)),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # Draw image center for reference
        cv2.circle(vis, (int(image_center[0]), int(image_center[1])), 5, (255, 0, 0), -1)
        
        cv2.imwrite('debug_board_center_from_lines.jpg', vis)
        print(f"\nVisualization saved to: debug_board_center_from_lines.jpg")
