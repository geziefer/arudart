"""
Check bull detection accuracy.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import cv2
import numpy as np
from src.calibration.feature_detector import FeatureDetector

# Configuration
config = {
    'calibration': {
        'feature_detection': {
            'bull_min_radius_px': 10,
            'bull_max_radius_px': 30,
            'canny_threshold_low': 50,
            'canny_threshold_high': 150,
            'black_singles_h_min': 0,
            'black_singles_h_max': 180,
            'black_singles_s_min': 0,
            'black_singles_s_max': 80,
            'black_singles_v_min': 0,
            'black_singles_v_max': 100,
            'white_singles_h_min': 0,
            'white_singles_h_max': 180,
            'white_singles_s_min': 0,
            'white_singles_s_max': 80,
            'white_singles_v_min': 120,
            'white_singles_v_max': 255,
            'red_ring_h_min_1': 0,
            'red_ring_h_max_1': 15,
            'red_ring_h_min_2': 165,
            'red_ring_h_max_2': 180,
            'red_ring_s_min': 80,
            'red_ring_s_max': 255,
            'red_ring_v_min': 80,
            'red_ring_v_max': 255,
            'green_ring_h_min': 35,
            'green_ring_h_max': 85,
            'green_ring_s_min': 80,
            'green_ring_s_max': 255,
            'green_ring_v_min': 80,
            'green_ring_v_max': 255,
            'min_boundary_edge_points': 5,
            'boundary_clustering_angle_deg': 3.0
        }
    }
}

detector = FeatureDetector(config)

# Test on one image from each camera
test_images = [
    'data/testimages/BS/BS10_cam0_pre.jpg',
    'data/testimages/BS/BS10_cam1_pre.jpg',
    'data/testimages/BS/BS10_cam2_pre.jpg',
]

for test_image in test_images:
    print(f"\n{'='*60}")
    print(f"Testing: {test_image}")
    
    image = cv2.imread(test_image)
    if image is None:
        print("Failed to load image")
        continue
    
    # Detect bull
    bull_center = detector.detect_bull_center(image)
    
    if bull_center:
        bull_u, bull_v = bull_center
        print(f"Bull detected at: ({bull_u:.1f}, {bull_v:.1f})")
        
        # Create visualization
        vis = image.copy()
        
        # Draw detected bull center
        cv2.circle(vis, (int(bull_u), int(bull_v)), 5, (0, 255, 0), -1)
        cv2.circle(vis, (int(bull_u), int(bull_v)), 30, (0, 255, 0), 2)
        cv2.putText(vis, "DETECTED", (int(bull_u) + 35, int(bull_v)),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # Draw image center for reference
        img_center_u = image.shape[1] / 2
        img_center_v = image.shape[0] / 2
        cv2.circle(vis, (int(img_center_u), int(img_center_v)), 5, (255, 0, 0), -1)
        cv2.putText(vis, "IMG CENTER", (int(img_center_u) + 10, int(img_center_v) - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)
        
        # Save visualization
        output_path = test_image.replace('_pre.jpg', '_bull_check.jpg')
        cv2.imwrite(output_path, vis)
        print(f"Saved visualization to: {output_path}")
        
        # Check if bull is roughly in the center
        dist_from_center = np.sqrt((bull_u - img_center_u)**2 + (bull_v - img_center_v)**2)
        print(f"Distance from image center: {dist_from_center:.1f} pixels")
        
        if dist_from_center > 100:
            print("⚠️  WARNING: Bull detection seems off - too far from image center!")
    else:
        print("❌ Bull not detected")

print(f"\n{'='*60}")
print("Check the *_bull_check.jpg files to visually verify bull detection")
