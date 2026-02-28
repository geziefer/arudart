"""
Visualize feature detection on real camera images.

This script shows the detected features overlaid on the images
to help debug and tune the detection parameters.
"""

import cv2
import numpy as np
from pathlib import Path

from src.calibration.feature_detector import FeatureDetector


def visualize_detection(image_path: str, save_output: bool = True):
    """Visualize feature detection on a single image."""
    
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
    
    # Load image
    path = Path(image_path)
    image = cv2.imread(str(path))
    
    if image is None:
        print(f"Failed to load image: {image_path}")
        return
    
    # Run detection
    result = detector.detect(image)
    
    # Create visualization
    vis = image.copy()
    
    # Draw bull center (green circle)
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
    
    # Draw radial wires (yellow lines)
    for wire in result.radial_wires:
        (x1, y1), (x2, y2) = wire.endpoints
        cv2.line(vis, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 255), 2)
    
    # Draw wire intersections (red dots)
    for intersection in result.wire_intersections:
        x, y = intersection.pixel
        cv2.circle(vis, (int(x), int(y)), 4, (0, 0, 255), -1)
    
    # Add text overlay with detection stats
    y_offset = 30
    cv2.putText(vis, f"Bull: {'YES' if result.bull_center else 'NO'}", 
               (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    y_offset += 25
    cv2.putText(vis, f"Double ring: {len(result.ring_edges.get('double_ring', []))} pts", 
               (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    y_offset += 25
    cv2.putText(vis, f"Triple ring: {len(result.ring_edges.get('triple_ring', []))} pts", 
               (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    y_offset += 25
    cv2.putText(vis, f"Wires: {len(result.radial_wires)}", 
               (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    y_offset += 25
    cv2.putText(vis, f"Intersections: {len(result.wire_intersections)}", 
               (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    # Save visualization
    if save_output:
        output_path = path.parent / f"{path.stem}_features.jpg"
        cv2.imwrite(str(output_path), vis)
        print(f"Saved visualization to: {output_path}")
    
    # Display
    cv2.imshow(f"Feature Detection - {path.name}", vis)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    return result


if __name__ == '__main__':
    # Test on all three cameras
    test_images = [
        'data/testimages/BS/BS1_cam0_pre.jpg',
        'data/testimages/BS/BS1_cam1_pre.jpg',
        'data/testimages/BS/BS1_cam2_pre.jpg',
    ]
    
    for image_path in test_images:
        print(f"\nProcessing: {image_path}")
        visualize_detection(image_path, save_output=True)
