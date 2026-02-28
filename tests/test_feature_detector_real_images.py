"""
Test FeatureDetector on real camera images.

This script tests the feature detector on actual dartboard images
from the camera system to verify it works in real-world conditions.
"""

import cv2
import numpy as np
from pathlib import Path

from src.calibration.feature_detector import FeatureDetector


def test_feature_detection_on_real_images():
    """Test feature detection on real camera images."""
    
    # Configuration
    config = {
        'calibration': {
            'feature_detection': {
                'bull_min_radius_px': 10,
                'bull_max_radius_px': 30,
                'canny_threshold_low': 50,
                'canny_threshold_high': 150,
                'hough_line_threshold': 50,
                'min_wire_length_px': 50
            }
        }
    }
    
    detector = FeatureDetector(config)
    
    # Test on all pre-throw images (clean dartboard without dart)
    # BS1-BS20, 3 cameras each = 60 images total
    test_images = []
    for i in range(1, 21):  # BS1 to BS20
        for cam in ['cam0', 'cam1', 'cam2']:
            test_images.append(f'data/testimages/BS/BS{i}_{cam}_pre.jpg')
    
    results = {}
    per_camera_results = {'cam0': [], 'cam1': [], 'cam2': []}
    
    print(f"Testing feature detection on {len(test_images)} images...")
    print(f"{'='*60}\n")
    
    for image_path in test_images:
        path = Path(image_path)
        if not path.exists():
            print(f"⚠️  Image not found: {image_path}")
            continue
        
        # Load image
        image = cv2.imread(str(path))
        if image is None:
            print(f"❌ Failed to load image: {image_path}")
            continue
        
        # Run detection
        result = detector.detect(image)
        
        # Store results
        camera_id = path.stem.split('_')[1]  # Extract cam0, cam1, cam2
        scenario = path.stem.split('_')[0]  # Extract BS1, BS2, etc.
        key = f"{scenario}_{camera_id}"
        results[key] = result
        per_camera_results[camera_id].append(result)
        
        # Print brief results (not full details for 60 images)
        status = "✅" if result.error is None else "❌"
        bull = "✓" if result.bull_center else "✗"
        wires = len(result.radial_wires)
        intersections = len(result.wire_intersections)
        print(f"{status} {scenario:5} {camera_id}: bull={bull} wires={wires:2d} intersections={intersections:2d}")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"{'SUMMARY - ALL IMAGES':^60}")
    print(f"{'='*60}")
    
    total_images = len(results)
    bull_detected = sum(1 for r in results.values() if r.bull_center is not None)
    sufficient_wires = sum(1 for r in results.values() if len(r.radial_wires) >= 8)
    sufficient_intersections = sum(1 for r in results.values() if len(r.wire_intersections) >= 4)
    
    print(f"Total images tested: {total_images}")
    print(f"Bull center detected: {bull_detected}/{total_images} ({bull_detected/total_images*100:.1f}%)")
    print(f"Sufficient wires (≥8): {sufficient_wires}/{total_images} ({sufficient_wires/total_images*100:.1f}%)")
    print(f"Sufficient intersections (≥4): {sufficient_intersections}/{total_images} ({sufficient_intersections/total_images*100:.1f}%)")
    
    # Per-camera breakdown
    print(f"\n{'PER-CAMERA BREAKDOWN':^60}")
    print(f"{'-'*60}")
    
    for cam_id in ['cam0', 'cam1', 'cam2']:
        cam_results = per_camera_results[cam_id]
        if not cam_results:
            continue
        
        total = len(cam_results)
        bull = sum(1 for r in cam_results if r.bull_center is not None)
        wires_8 = sum(1 for r in cam_results if len(r.radial_wires) >= 8)
        intersections_4 = sum(1 for r in cam_results if len(r.wire_intersections) >= 4)
        
        avg_wires = sum(len(r.radial_wires) for r in cam_results) / total
        avg_intersections = sum(len(r.wire_intersections) for r in cam_results) / total
        
        print(f"\n{cam_id}:")
        print(f"  Bull detected: {bull}/{total} ({bull/total*100:.1f}%)")
        print(f"  Sufficient wires (≥8): {wires_8}/{total} ({wires_8/total*100:.1f}%)")
        print(f"  Sufficient intersections (≥4): {intersections_4}/{total} ({intersections_4/total*100:.1f}%)")
        print(f"  Avg wires: {avg_wires:.1f}")
        print(f"  Avg intersections: {avg_intersections:.1f}")
    
    # Overall assessment
    print(f"\n{'OVERALL ASSESSMENT':^60}")
    print(f"{'-'*60}")
    
    if bull_detected >= total_images * 0.9:
        print("✅ Bull center detection: EXCELLENT (≥90%)")
    elif bull_detected >= total_images * 0.7:
        print("⚠️  Bull center detection: GOOD (≥70%)")
    elif bull_detected > 0:
        print(f"⚠️  Bull center detection: POOR ({bull_detected/total_images*100:.1f}%)")
    else:
        print("❌ Bull center detection: FAIL (0%)")
    
    if sufficient_intersections >= total_images * 0.9:
        print("✅ Feature detection: EXCELLENT (≥90% have ≥4 intersections)")
    elif sufficient_intersections >= total_images * 0.7:
        print("⚠️  Feature detection: GOOD (≥70% have ≥4 intersections)")
    elif sufficient_intersections > 0:
        print(f"⚠️  Feature detection: POOR ({sufficient_intersections/total_images*100:.1f}% have ≥4 intersections)")
    else:
        print("❌ Feature detection: FAIL (no images have sufficient features)")
    
    print(f"\n{'='*60}\n")
    
    return results


if __name__ == '__main__':
    test_feature_detection_on_real_images()
