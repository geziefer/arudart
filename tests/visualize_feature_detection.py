"""
Visualize feature detection on real camera images.

This script shows the detected features overlaid on the images
to help debug and tune the detection parameters.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import cv2
import numpy as np

from src.calibration.feature_detector import FeatureDetector


def visualize_detection(image_path: str, save_output: bool = True, window_name: str = None):
    """Visualize feature detection on a single image."""
    
    # Configuration - use relaxed HSV ranges that work better
    config = {
        'calibration': {
            'feature_detection': {
                'bull_min_radius_px': 10,
                'bull_max_radius_px': 30,
                'canny_threshold_low': 50,
                'canny_threshold_high': 150,
                # HSV color ranges - RELAXED for better detection
                'black_singles_h_min': 0,
                'black_singles_h_max': 180,
                'black_singles_s_min': 0,
                'black_singles_s_max': 80,  # Relaxed from 50
                'black_singles_v_min': 0,
                'black_singles_v_max': 100,  # Relaxed from 80
                'white_singles_h_min': 0,
                'white_singles_h_max': 180,
                'white_singles_s_min': 0,
                'white_singles_s_max': 80,  # Relaxed from 50
                'white_singles_v_min': 120,  # Relaxed from 150
                'white_singles_v_max': 255,
                'red_ring_h_min_1': 0,
                'red_ring_h_max_1': 15,  # Relaxed from 10
                'red_ring_h_min_2': 165,  # Relaxed from 170
                'red_ring_h_max_2': 180,
                'red_ring_s_min': 80,  # Relaxed from 100
                'red_ring_s_max': 255,
                'red_ring_v_min': 80,  # Relaxed from 100
                'red_ring_v_max': 255,
                'green_ring_h_min': 35,  # Relaxed from 40
                'green_ring_h_max': 85,  # Relaxed from 80
                'green_ring_s_min': 80,  # Relaxed from 100
                'green_ring_s_max': 255,
                'green_ring_v_min': 80,  # Relaxed from 100
                'green_ring_v_max': 255,
                'min_boundary_edge_points': 5,  # Relaxed from 10
                'boundary_clustering_angle_deg': 3.0  # Relaxed from 2.0
            }
        }
    }
    
    detector = FeatureDetector(config)
    
    # Load image
    path = Path(image_path)
    image = cv2.imread(str(path))
    
    if image is None:
        print(f"Failed to load image: {image_path}")
        return None
    
    # Run detection
    result = detector.detect(image)
    
    # Create visualization
    vis = image.copy()
    
    # Draw bull center (green ellipse)
    if result.bull_center is not None:
        bull_u, bull_v = result.bull_center
        cv2.circle(vis, (int(bull_u), int(bull_v)), 5, (0, 255, 0), -1)
        cv2.circle(vis, (int(bull_u), int(bull_v)), 30, (0, 255, 0), 2)
        cv2.putText(vis, "BULL", (int(bull_u) + 10, int(bull_v) - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    # Draw ring edges (blue ellipses)
    for ring_type, color in [('double_ring', (255, 0, 0)), ('triple_ring', (255, 128, 0))]:
        if ring_type in result.ring_edges and result.ring_edges[ring_type]:
            points = result.ring_edges[ring_type]
            for i, (x, y) in enumerate(points):
                if i % 3 == 0:  # Draw every 3rd point to reduce clutter
                    cv2.circle(vis, (int(x), int(y)), 2, color, -1)
    
    # Draw sector boundaries (yellow lines from bull center)
    if result.bull_center is not None:
        bull_u, bull_v = result.bull_center
        for boundary in result.sector_boundaries:
            # Draw line from bull center outward at boundary angle
            angle_rad = np.radians(boundary.angle)
            # Length of line (extend to edge of image)
            length = 400
            dx = np.sin(angle_rad)  # sin because 0° = up
            dy = -np.cos(angle_rad)  # -cos because Y increases downward
            
            end_x = int(bull_u + length * dx)
            end_y = int(bull_v + length * dy)
            
            cv2.line(vis, (int(bull_u), int(bull_v)), (end_x, end_y), (0, 255, 255), 1)
            
            # Draw sector number near the boundary
            label_dist = 300
            label_x = int(bull_u + label_dist * dx)
            label_y = int(bull_v + label_dist * dy)
            cv2.putText(vis, str(boundary.sector), (label_x, label_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    
    # Draw boundary intersections (red dots)
    for intersection in result.boundary_intersections:
        x, y = intersection.pixel
        cv2.circle(vis, (int(x), int(y)), 4, (0, 0, 255), -1)
    
    # Add text overlay with detection stats (top)
    # Extract camera ID from filename (e.g., BS1_cam0_pre.jpg -> cam0)
    camera_id = "unknown"
    if '_cam' in path.stem:
        camera_id = path.stem.split('_cam')[1].split('_')[0]
        camera_id = f"cam{camera_id}"
    
    y_offset = 30
    # Add camera ID prominently at the top
    cv2.putText(vis, f"Camera: {camera_id.upper()}", 
               (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    y_offset += 30
    cv2.putText(vis, f"Bull: {'YES' if result.bull_center else 'NO'}", 
               (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    y_offset += 25
    cv2.putText(vis, f"Double ring: {len(result.ring_edges.get('double_ring', []))} pts", 
               (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    y_offset += 25
    cv2.putText(vis, f"Triple ring: {len(result.ring_edges.get('triple_ring', []))} pts", 
               (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    y_offset += 25
    cv2.putText(vis, f"Boundaries: {len(result.sector_boundaries)}", 
               (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    y_offset += 25
    cv2.putText(vis, f"Intersections: {len(result.boundary_intersections)}", 
               (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    # Add validation options overlay at bottom
    height = vis.shape[0]
    # Create semi-transparent black bar at bottom
    overlay = vis.copy()
    cv2.rectangle(overlay, (0, height - 120), (vis.shape[1], height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.7, vis, 0.3, 0, vis)
    
    # Add validation options text
    options_y = height - 95
    cv2.putText(vis, "VALIDATION OPTIONS:", 
               (10, options_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    options_y += 20
    cv2.putText(vis, "1 = All OK  |  2 = Bull wrong  |  3 = Rings wrong  |  4 = Boundaries wrong", 
               (10, options_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
    options_y += 18
    cv2.putText(vis, "5 = Intersections wrong  |  6 = Multiple issues  |  s = Skip  |  q = Quit", 
               (10, options_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
    options_y += 18
    cv2.putText(vis, "Press the corresponding key...", 
               (10, options_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
    
    # Save visualization
    if save_output:
        output_path = path.parent / f"{path.stem}_features.jpg"
        cv2.imwrite(str(output_path), vis)
    
    # Display (but don't wait here - let caller handle input)
    if window_name is None:
        window_name = f"Feature Detection - {path.name}"
    cv2.imshow(window_name, vis)
    
    return result


if __name__ == '__main__':
    import glob
    import json
    from datetime import datetime
    
    # Find all *_pre.jpg images in the test folder
    test_folder = Path('data/testimages/BS')
    test_images = sorted(test_folder.glob('*_pre.jpg'))
    
    if not test_images:
        print(f"No *_pre.jpg images found in {test_folder}")
        exit(1)
    
    print(f"Found {len(test_images)} pre-images to process")
    print("Instructions:")
    print("  - Review the detected features (bull, rings, boundaries, intersections)")
    print("  - Press the corresponding key:")
    print("    1 = All OK")
    print("    2 = Bull wrong (wrong position or not the bull)")
    print("    3 = Rings wrong (ring edges incorrectly fitted)")
    print("    4 = Boundaries wrong (not sector boundaries or wrong sectors)")
    print("    5 = Intersections wrong (incorrect boundary-ring crossings)")
    print("    6 = Multiple issues (combination of above)")
    print("    s = Skip (no evaluation, just browse)")
    print("    q = Quit early")
    print()
    
    # Store manual validation results
    results = []
    
    # Use consistent window name for all images
    window_name = "ARU-DART Feature Detection"
    
    for i, image_path in enumerate(test_images, 1):
        print(f"\n[{i}/{len(test_images)}] Processing: {image_path.name}")
        
        # Run detection and visualization
        result = visualize_detection(str(image_path), save_output=True, window_name=window_name)
        
        if result is None:
            print("  ⚠️  Failed to load image, skipping...")
            continue
        
        # Wait for user input
        print("  Press 1-6, s (skip), or q (quit)...")
        
        validation_map = {
            ord('1'): ('ALL_OK', 'All OK'),
            ord('2'): ('BULL_WRONG', 'Bull wrong'),
            ord('3'): ('RINGS_WRONG', 'Rings wrong'),
            ord('4'): ('BOUNDARIES_WRONG', 'Boundaries wrong'),
            ord('5'): ('INTERSECTIONS_WRONG', 'Intersections wrong'),
            ord('6'): ('MULTIPLE_ISSUES', 'Multiple issues'),
            ord('s'): ('SKIP', 'Skipped'),
            ord('q'): ('QUIT', 'Quit')
        }
        
        validation_code = None
        while True:
            key = cv2.waitKey(0) & 0xFF
            
            if key in validation_map:
                validation_code, validation_label = validation_map[key]
                
                if validation_code == 'QUIT':
                    print("\n  Quitting early...")
                    validation_code = 'SKIPPED'
                elif validation_code == 'SKIP':
                    print(f"  ⊘ Skipped (no evaluation)")
                else:
                    symbol = "✓" if validation_code == 'ALL_OK' else "✗"
                    print(f"  {symbol} Marked as: {validation_label}")
                
                break
            else:
                print(f"  Invalid key. Press 1-6, s, or q")
        
        # Store result
        results.append({
            'image': image_path.name,
            'validation': validation_code,
            'bull_detected': result.bull_center is not None,
            'num_boundaries': len(result.sector_boundaries),
            'num_intersections': len(result.boundary_intersections),
            'double_ring_points': len(result.ring_edges.get('double_ring', [])),
            'triple_ring_points': len(result.ring_edges.get('triple_ring', [])),
            'error': result.error
        })
        
        if key == ord('q'):
            break
    
    # Clean up window
    cv2.destroyAllWindows()
    
    # Save results to JSON
    results_file = test_folder / f'manual_validation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*60}")
    print("Manual Validation Complete")
    print(f"{'='*60}")
    print(f"Total images processed: {len(results)}")
    print(f"All OK: {sum(1 for r in results if r['validation'] == 'ALL_OK')}")
    print(f"Bull wrong: {sum(1 for r in results if r['validation'] == 'BULL_WRONG')}")
    print(f"Rings wrong: {sum(1 for r in results if r['validation'] == 'RINGS_WRONG')}")
    print(f"Boundaries wrong: {sum(1 for r in results if r['validation'] == 'BOUNDARIES_WRONG')}")
    print(f"Intersections wrong: {sum(1 for r in results if r['validation'] == 'INTERSECTIONS_WRONG')}")
    print(f"Multiple issues: {sum(1 for r in results if r['validation'] == 'MULTIPLE_ISSUES')}")
    print(f"Skipped: {sum(1 for r in results if r['validation'] == 'SKIP')}")
    print(f"Quit early: {sum(1 for r in results if r['validation'] == 'SKIPPED')}")
    print(f"\nResults saved to: {results_file}")
    print(f"Annotated images saved to: {test_folder}/*_features.jpg")
