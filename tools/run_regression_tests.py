#!/usr/bin/env python3
"""
Regression Test Runner

Tests dart detection against ground truth annotations.
Runs detection on recorded images and compares with human-annotated tip positions.
Includes fusion-based analysis (≥2/3 cameras = success for multi-camera system).

Usage:
    python tools/run_regression_tests.py [--tolerance PIXELS]
    
Options:
    --tolerance PIXELS    Position error tolerance in pixels (default: 10)
"""

import cv2
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.processing.dart_detection import DartDetector
from src.config import load_config


def load_test_cases(testimages_dir):
    """Load all test cases (POST images with ground truth JSON) from testimages and subdirectories.
    
    Expected format: 
    - Images: <description>_camX_post.jpg
    - Ground truth: <description>_camX.json (without _post suffix)
    Example: BS20_cam0_post.jpg → BS20_cam0.json
    """
    test_cases = []
    
    # Find all JSON files recursively (ground truth files without _post suffix)
    json_files = sorted(testimages_dir.rglob("*_cam*.json"))
    
    # Filter out files that have _post in the name (old format)
    json_files = [f for f in json_files if '_post' not in f.stem]
    
    for json_file in json_files:
        # Load ground truth
        with open(json_file, 'r') as f:
            ground_truth = json.load(f)
        
        # Check if POST image exists (in same directory as JSON)
        post_image_file = json_file.parent / ground_truth["image_post"]
        if not post_image_file.exists():
            continue
        
        # Get PRE image from ground truth
        pre_image_file = json_file.parent / ground_truth["image_pre"]
        
        if not pre_image_file.exists():
            print(f"Warning: PRE image not found: {ground_truth['image_pre']}")
            continue
        
        # Extract camera ID and description from filename
        # Format: <description>_camX_post.jpg -> description, X
        parts = post_image_file.stem.split('_cam')
        if len(parts) >= 2:
            description = parts[0]
            cam_id = int(parts[1][0])  # Extract number after "cam"
            test_cases.append({
                "pre_image_file": pre_image_file,
                "post_image_file": post_image_file,
                "camera_id": cam_id,
                "description": description,
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
    # Parse arguments
    parser = argparse.ArgumentParser(description='Run regression tests on dart detection')
    parser.add_argument('--tolerance', type=int, default=10,
                       help='Position error tolerance in pixels (default: 10)')
    args = parser.parse_args()
    
    tolerance = args.tolerance
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    print("=" * 70)
    print("ARU-DART Regression Test Suite")
    print(f"Timestamp: {timestamp}")
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
    
    # List test folder contents
    print(f"Test folder: {testimages_dir}")
    print(f"Found {len(test_cases)} test cases")
    print(f"Tolerance: {tolerance} pixels")
    print()
    
    # Run tests and collect results
    results = {
        "total": 0,
        "passed": 0,
        "failed_no_detection": 0,
        "failed_position": 0,
        "per_camera": {0: {"total": 0, "passed": 0}, 
                       1: {"total": 0, "passed": 0}, 
                       2: {"total": 0, "passed": 0}},
        "per_ring": {},
        "per_throw": defaultdict(lambda: {"cameras": {}, "description": ""})
    }
    
    detailed_results = []
    
    for i, test_case in enumerate(test_cases, 1):
        pre_image_file = test_case["pre_image_file"]
        post_image_file = test_case["post_image_file"]
        cam_id = test_case["camera_id"]
        description = test_case["description"]
        gt = test_case["ground_truth"]
        
        # Load pre and post images
        pre_image = cv2.imread(str(pre_image_file))
        post_image = cv2.imread(str(post_image_file))
        
        if pre_image is None or post_image is None:
            print(f"[{i}/{len(test_cases)}] SKIP {post_image_file.name} (could not load images)")
            continue
        
        # Run detection
        tip_x, tip_y, confidence = run_detection(detector, pre_image, post_image)
        
        # Update stats
        results["total"] += 1
        results["per_camera"][cam_id]["total"] += 1
        results["per_throw"][description]["description"] = description
        
        ring = gt.get("expected_ring", "unknown")
        if ring not in results["per_ring"]:
            results["per_ring"][ring] = {"total": 0, "passed": 0}
        results["per_ring"][ring]["total"] += 1
        
        # Check result
        if tip_x is None:
            results["failed_no_detection"] += 1
            status = "FAIL"
            error_total = None
            reason = "No detection"
            results["per_throw"][description]["cameras"][cam_id] = {
                "status": "FAIL", "error": None, "reason": "No detection"
            }
            print(f"[{i}/{len(test_cases)}] FAIL {post_image_file.name} - No detection")
        else:
            error_x = abs(tip_x - gt["tip_x"])
            error_y = abs(tip_y - gt["tip_y"])
            error_total = np.sqrt(error_x**2 + error_y**2)
            
            if error_x < tolerance and error_y < tolerance:
                results["passed"] += 1
                results["per_camera"][cam_id]["passed"] += 1
                results["per_ring"][ring]["passed"] += 1
                status = "PASS"
                reason = None
                results["per_throw"][description]["cameras"][cam_id] = {
                    "status": "PASS", "error": error_total
                }
                print(f"[{i}/{len(test_cases)}] PASS {post_image_file.name} - Error: {error_total:.1f}px (conf={confidence:.2f})")
            else:
                results["failed_position"] += 1
                status = "FAIL"
                reason = f"Position error (X:{error_x:.0f}, Y:{error_y:.0f})"
                results["per_throw"][description]["cameras"][cam_id] = {
                    "status": "FAIL", "error": error_total, "reason": reason
                }
                print(f"[{i}/{len(test_cases)}] FAIL {post_image_file.name} - Error: {error_total:.1f}px (X:{error_x:.0f}, Y:{error_y:.0f})")
        
        detailed_results.append({
            "file": post_image_file.name,
            "camera": cam_id,
            "description": description,
            "ring": ring,
            "status": status,
            "error": error_total,
            "reason": reason
        })
    
    # Print per-camera summary
    print()
    print("=" * 70)
    print("PER-CAMERA SUMMARY")
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
    
    # Fusion-based analysis (grouped by throw)
    print("=" * 70)
    print("FUSION-BASED ANALYSIS (Grouped by Throw)")
    print("=" * 70)
    print()
    print("In a 3-camera fusion system, success means ≥2 cameras detect correctly.")
    print()
    
    throws_with_2plus = 0
    throws_with_3 = 0
    total_throws = len(results["per_throw"])
    
    for desc in sorted(results["per_throw"].keys()):
        throw_data = results["per_throw"][desc]
        cameras = throw_data["cameras"]
        passed = sum(1 for cam in cameras.values() if cam["status"] == "PASS")
        
        status_icon = "✓" if passed >= 2 else "✗"
        fusion_status = "FUSION OK" if passed >= 2 else "FUSION FAIL"
        
        print(f"Throw: {desc}")
        print(f"  {status_icon} {fusion_status} ({passed}/{len(cameras)} cameras)")
        
        for cam_id in sorted(cameras.keys()):
            cam = cameras[cam_id]
            if cam["status"] == "PASS":
                print(f"    cam{cam_id}: ✓ PASS (error: {cam['error']:.1f}px)")
            else:
                print(f"    cam{cam_id}: ✗ FAIL ({cam.get('reason', 'Unknown')})")
        print()
        
        if passed >= 2:
            throws_with_2plus += 1
        if passed == len(cameras) and len(cameras) > 0:
            throws_with_3 += 1
    
    print("=" * 70)
    print("FUSION SUMMARY")
    print("=" * 70)
    if total_throws > 0:
        print(f"Total throws:                    {total_throws}")
        print(f"Throws with ≥2 cameras (GOOD):   {throws_with_2plus} ({100*throws_with_2plus/total_throws:.0f}%)")
        print(f"Throws with all cameras (IDEAL): {throws_with_3} ({100*throws_with_3/total_throws:.0f}%)")
        print()
        
        if throws_with_2plus == total_throws:
            print("✓ EXCELLENT: All throws have sufficient camera coverage for fusion!")
        elif throws_with_2plus >= 0.75 * total_throws:
            print("✓ GOOD: Most throws (≥75%) have sufficient camera coverage for fusion.")
        else:
            print("⚠ WARNING: Less than 75% of throws have sufficient camera coverage.")
    print()
    
    # Save report with timestamp
    report_dir = Path("tests")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"regression_report_{timestamp}.txt"
    
    with open(report_file, 'w') as f:
        f.write("ARU-DART Regression Test Report\n")
        f.write(f"Timestamp: {timestamp}\n")
        f.write("=" * 70 + "\n\n")
        
        f.write("TEST FOLDER CONTENTS\n")
        f.write("-" * 40 + "\n")
        f.write(f"Directory: {testimages_dir}\n")
        f.write(f"Test cases: {len(test_cases)}\n")
        f.write(f"Unique throws: {total_throws}\n\n")
        
        f.write("PER-CAMERA SUMMARY\n")
        f.write("-" * 40 + "\n")
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
        
        f.write("\n" + "=" * 70 + "\n")
        f.write("FUSION-BASED ANALYSIS\n")
        f.write("=" * 70 + "\n\n")
        
        if total_throws > 0:
            f.write(f"Total throws:                    {total_throws}\n")
            f.write(f"Throws with ≥2 cameras (GOOD):   {throws_with_2plus} ({100*throws_with_2plus/total_throws:.0f}%)\n")
            f.write(f"Throws with all cameras (IDEAL): {throws_with_3} ({100*throws_with_3/total_throws:.0f}%)\n\n")
        
        f.write("Per-Throw Details:\n")
        for desc in sorted(results["per_throw"].keys()):
            throw_data = results["per_throw"][desc]
            cameras = throw_data["cameras"]
            passed = sum(1 for cam in cameras.values() if cam["status"] == "PASS")
            fusion_status = "OK" if passed >= 2 else "FAIL"
            f.write(f"  {desc}: {fusion_status} ({passed}/{len(cameras)} cameras)\n")
    
    print(f"Report saved to: {report_file}")
    print()
    
    # Exit code based on fusion success (≥75% throws with ≥2 cameras)
    if total_throws > 0 and throws_with_2plus >= 0.75 * total_throws:
        print("✓ Regression tests passed (fusion criteria met)")
        sys.exit(0)
    else:
        print("✗ Regression tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
