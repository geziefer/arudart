"""
Test feature detection across all cameras and images.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import cv2
from src.calibration.feature_detector import FeatureDetector

# Configuration with relaxed color ranges
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

# Find all test images
test_folder = Path('data/testimages/BS')
test_images = sorted(test_folder.glob('*_pre.jpg'))

print(f"Testing {len(test_images)} images\n")

# Track statistics by camera
stats = {
    'cam0': {'total': 0, 'bull_detected': 0, 'boundaries_ok': 0, 'avg_boundaries': []},
    'cam1': {'total': 0, 'bull_detected': 0, 'boundaries_ok': 0, 'avg_boundaries': []},
    'cam2': {'total': 0, 'bull_detected': 0, 'boundaries_ok': 0, 'avg_boundaries': []},
}

for image_path in test_images:
    # Extract camera ID
    if '_cam0_' in image_path.name:
        camera_id = 'cam0'
    elif '_cam1_' in image_path.name:
        camera_id = 'cam1'
    elif '_cam2_' in image_path.name:
        camera_id = 'cam2'
    else:
        continue
    
    stats[camera_id]['total'] += 1
    
    # Load and detect
    image = cv2.imread(str(image_path))
    if image is None:
        continue
    
    result = detector.detect(image)
    
    # Track statistics
    if result.bull_center is not None:
        stats[camera_id]['bull_detected'] += 1
    
    if len(result.sector_boundaries) >= 8:
        stats[camera_id]['boundaries_ok'] += 1
    
    stats[camera_id]['avg_boundaries'].append(len(result.sector_boundaries))

# Print summary
print(f"{'='*70}")
print(f"DETECTION SUMMARY")
print(f"{'='*70}")

for camera_id in ['cam0', 'cam1', 'cam2']:
    s = stats[camera_id]
    if s['total'] == 0:
        continue
    
    bull_rate = 100 * s['bull_detected'] / s['total']
    boundary_rate = 100 * s['boundaries_ok'] / s['total']
    avg_boundaries = sum(s['avg_boundaries']) / len(s['avg_boundaries']) if s['avg_boundaries'] else 0
    
    print(f"\n{camera_id.upper()}:")
    print(f"  Images tested: {s['total']}")
    print(f"  Bull detected: {s['bull_detected']}/{s['total']} ({bull_rate:.1f}%)")
    print(f"  Boundaries ≥8: {s['boundaries_ok']}/{s['total']} ({boundary_rate:.1f}%)")
    print(f"  Avg boundaries: {avg_boundaries:.1f}")

print(f"\n{'='*70}")
print("OVERALL:")
total_images = sum(s['total'] for s in stats.values())
total_bull = sum(s['bull_detected'] for s in stats.values())
total_boundaries_ok = sum(s['boundaries_ok'] for s in stats.values())

print(f"  Total images: {total_images}")
print(f"  Bull detection rate: {100*total_bull/total_images:.1f}%")
print(f"  Boundary detection rate (≥8): {100*total_boundaries_ok/total_images:.1f}%")
print(f"{'='*70}")
