#!/usr/bin/env python3
"""
Regression Test Runner

Tests dart detection against ground truth annotations.
Runs detection on recorded images and compares with human-annotated tip positions.

Usage:
    python tools/run_regression_tests.py
"""

import cv2
import json
import sys
from pathlib import Path
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.processing.dart_detection import DartDetector
from src.config import load_config


def load_pre_images(data_dir):
    """Load pre-images (clean board) for each camera."""
    pre_images = {}
    
    for cam_id in [0, 1, 2]:
        pre_file = data_dir / f"cam{cam_id}_pre.jpg"
        if pre_file.exists():
            pre_images[cam_id] = cv2.imread(str(pre_file))
            print(f"Loaded pre-image: {pre_file}")
        else:
            print(f"Warning: Pre-image not found: {pre_file}")
    
    return pre_images


def load_test_cases(testimages_dir):
    """Load all test cases (images with ground truth JSON) from testimages and subdirectories."""
    test_cases = []
    
    # Find all JSON files recursively
    json_files = sorted(testimages_dir.rglob("*.json"))
    
    for json_file in json_files:
        # Load ground truth
        with open(json_file, 'r') as f:
            ground_truth = json.load(f)
        
        # Check if image exists (in same directory as JSON)
        image_file = json_file.parent / ground_truth["image"]
        if not image_file.exists():
            continue
        
        # Extract camera ID from filename (e.g., "001_cam0_BS1.jpg" -> 0)
        parts = image_file.stem.split('_')
        if len(parts) >= 2 and parts[1].startswith('cam'):
            cam_id = int(parts[1][3])  # Extract number from "cam0"
            test_cases.append({
                "image_file": image_file,
                "camera_id": cam_id,
                "ground_truth": ground_truth
            })
    
    return test_cases


def run_detection(detector, pre_image, post_image):
    """Run detection on image pair."""
    try:
        tip_x, tip_y, confidence, debug_info = detector.detect(
            pre_image, post_image, mask_previous=False
        )
        return tip_x, tip_y, confidence
    except Exception as e:
        print(f"    Detection error: {e}")
        return None, None, 0.0


def main():
    print("=" * 70)
    print("ARU-DART Regression Test Suite")
    print("=" * 70)
    print()
    
    # Load config
    config = load_config("config.toml")
    dart_config = config['dart_detection']
    
    # Initialize detector
    detector = DartDetector(
        diff_threshold=dart_config['diff_threshold'],
        blur_kernel=dart_config['blur_kernel'],
        min_dart_area=dart_config['min_dart_area'],
        max_dart_area=dart_config['max_dart_area'],
        min_shaft_length=dart_config['min_shaft_length'],
        aspect_ratio_min=dart_config['aspect_ratio_min']
    )
    
    # Load pre-images
    data_dir = Path("data")
    pre_images = load_pre_images(data_dir)
    
    if not pre_images:
        print("Error: No pre-images found!")
        print("Please place cam0_pre.jpg, cam1_pre.jpg, cam2_pre.jpg in data/")
        return
    
    # Load test cases
    testimages_dir = Path("data/testimages")
    
    if not testimages_dir.exists():
        print(f"Error: {testimages_dir} does not exist!")
        print("Please create data/testimages/ and copy annotated images there")
        return
    
    test_cases = load_test_cases(testimages_dir)
    
    if not test_cases:
        print("Error: No test cases found!")
        print("Please copy annotated images and JSON files to data/testimages/")
        return
    
    print(f"Found {len(test_cases)} test cases")
    print(f"Tolerance: 10 pixels")
    print()
    
    # Run tests
    results = {
        "total": 0,
        "passed": 0,
        "failed_no_detection": 0,
        "failed_position": 0,
        "per_camera": {0: {"total": 0, "passed": 0}, 
                       1: {"total": 0, "passed": 0}, 
                       2: {"total": 0, "passed": 0}},
        "per_ring": {}
    }
    
    tolerance = 10  # pixels
    
    for i, test_case in enumerate(test_cases, 1):
        image_file = test_case["image_file"]
        cam_id = test_case["camera_id"]
        gt = test_case["ground_truth"]
        
        # Check if pre-image available for this camera
        if cam_id not in pre_images:
            print(f"[{i}/{len(test_cases)}] SKIP {image_file.name} (no pre-image for cam{cam_id})")
            continue
        
        # Load post-image
        post_image = cv2.imread(str(image_file))
        if post_image is None:
            print(f"[{i}/{len(test_cases)}] SKIP {image_file.name} (could not load)")
            continue
        
        # Run detection
        tip_x, tip_y, confidence = run_detection(detector, pre_images[cam_id], post_image)
        
        # Update stats
        results["total"] += 1
        results["per_camera"][cam_id]["total"] += 1
        
        ring = gt.get("expected_ring", "unknown")
        if ring not in results["per_ring"]:
            results["per_ring"][ring] = {"total": 0, "passed": 0}
        results["per_ring"][ring]["total"] += 1
        
        # Check result
        if tip_x is None:
            results["failed_no_detection"] += 1
            print(f"[{i}/{len(test_cases)}] FAIL {image_file.name} - No detection")
        else:
            error_x = abs(tip_x - gt["tip_x"])
            error_y = abs(tip_y - gt["tip_y"])
            error_total = np.sqrt(error_x**2 + error_y**2)
            
            if error_x < tolerance and error_y < tolerance:
                results["passed"] += 1
                results["per_camera"][cam_id]["passed"] += 1
                results["per_ring"][ring]["passed"] += 1
                print(f"[{i}/{len(test_cases)}] PASS {image_file.name} - Error: {error_total:.1f}px (conf={confidence:.2f})")
            else:
                results["failed_position"] += 1
                print(f"[{i}/{len(test_cases)}] FAIL {image_file.name} - Error: {error_total:.1f}px (X:{error_x:.0f}, Y:{error_y:.0f})")
    
    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total tests:        {results['total']}")
    print(f"Passed:             {results['passed']} ({100*results['passed']/results['total']:.1f}%)")
    print(f"Failed (no detect): {results['failed_no_detection']}")
    print(f"Failed (position):  {results['failed_position']}")
    print()
    
    print("Per-Camera Results:")
    for cam_id in sorted(results["per_camera"].keys()):
        stats = results["per_camera"][cam_id]
        if stats["total"] > 0:
            pct = 100 * stats["passed"] / stats["total"]
            print(f"  cam{cam_id}: {stats['passed']}/{stats['total']} ({pct:.1f}%)")
    print()
    
    print("Per-Ring Results:")
    for ring in sorted(results["per_ring"].keys()):
        stats = results["per_ring"][ring]
        if stats["total"] > 0:
            pct = 100 * stats["passed"] / stats["total"]
            print(f"  {ring:3s}: {stats['passed']}/{stats['total']} ({pct:.1f}%)")
    print()
    
    # Save report
    report_file = Path("tests/regression_report.txt")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_file, 'w') as f:
        f.write("ARU-DART Regression Test Report\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Total tests:        {results['total']}\n")
        f.write(f"Passed:             {results['passed']} ({100*results['passed']/results['total']:.1f}%)\n")
        f.write(f"Failed (no detect): {results['failed_no_detection']}\n")
        f.write(f"Failed (position):  {results['failed_position']}\n\n")
        f.write("Per-Camera Results:\n")
        for cam_id in sorted(results["per_camera"].keys()):
            stats = results["per_camera"][cam_id]
            if stats["total"] > 0:
                pct = 100 * stats["passed"] / stats["total"]
                f.write(f"  cam{cam_id}: {stats['passed']}/{stats['total']} ({pct:.1f}%)\n")
        f.write("\nPer-Ring Results:\n")
        for ring in sorted(results["per_ring"].keys()):
            stats = results["per_ring"][ring]
            if stats["total"] > 0:
                pct = 100 * stats["passed"] / stats["total"]
                f.write(f"  {ring:3s}: {stats['passed']}/{stats['total']} ({pct:.1f}%)\n")
    
    print(f"Report saved to: {report_file}")
    print()
    
    # Exit code
    if results["passed"] == results["total"]:
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
