#!/usr/bin/env python3
"""
Calibration Verification Script

Interactive tool for verifying calibration accuracy by clicking control points
and comparing transformed coordinates against known ground truth positions.

Usage:
    python calibration/verify_calibration.py
    python calibration/verify_calibration.py --camera 0
    python calibration/verify_calibration.py --save-report

Workflow:
1. Load coordinate mapper with calibration data
2. Display camera view with coordinate overlay
3. User clicks on known control points (T20, D20, bull, etc.)
4. Transform clicked pixels to board coordinates
5. Compare against ground truth positions
6. Display error statistics and optionally save report

Requirements: AC-6.5.1, AC-6.5.2, AC-6.5.3, AC-6.5.4, AC-6.5.5
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import tomli
except ImportError:
    import tomllib as tomli

from src.calibration.coordinate_mapper import CoordinateMapper


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Set up logging for the verification script."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger('verify_calibration')


def load_config(config_path: str = "config.toml") -> dict:
    """Load configuration from TOML file."""
    config_file = project_root / config_path
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    
    with open(config_file, 'rb') as f:
        return tomli.load(f)


# Known control points on dartboard (board coordinates in mm from center)
# These are approximate positions for standard dartboard geometry
CONTROL_POINTS = {
    'bull': (0.0, 0.0),           # Double bull center
    'T20': (0.0, 103.0),          # Triple 20 (top)
    'D20': (0.0, 166.0),          # Double 20 (top)
    'T3': (0.0, -103.0),          # Triple 3 (bottom)
    'D3': (0.0, -166.0),          # Double 3 (bottom)
    'T6': (103.0, 0.0),           # Triple 6 (right)
    'D6': (166.0, 0.0),           # Double 6 (right)
    'T11': (-103.0, 0.0),         # Triple 11 (left)
    'D11': (-166.0, 0.0),         # Double 11 (left)
    'T1': (72.8, 72.8),           # Triple 1 (upper right, ~45°)
    'T5': (72.8, -72.8),          # Triple 5 (lower right)
    'T12': (-72.8, 72.8),         # Triple 12 (upper left)
    'T9': (-72.8, -72.8),         # Triple 9 (lower left)
}


class VerificationUI:
    """Interactive UI for calibration verification."""
    
    def __init__(self, camera_id: int, config: dict, coordinate_mapper: CoordinateMapper):
        self.camera_id = camera_id
        self.config = config
        self.coordinate_mapper = coordinate_mapper
        
        self.clicked_points = []  # List of (pixel, board, label) tuples
        self.current_label = None
        self.frame = None
        
        # Camera settings
        camera_settings = config.get('camera_settings', {})
        self.width = camera_settings.get('width', 800)
        self.height = camera_settings.get('height', 600)
        
        self.window_name = f"Calibration Verification - Camera {camera_id}"
    
    def mouse_callback(self, event, x, y, flags, param):
        """Handle mouse clicks."""
        if event == cv2.EVENT_LBUTTONDOWN:
            # Transform pixel to board coordinates
            board_coords = self.coordinate_mapper.map_to_board(self.camera_id, x, y)
            
            if board_coords is not None:
                bx, by = board_coords
                self.clicked_points.append({
                    'pixel': (x, y),
                    'board': (bx, by),
                    'label': self.current_label,
                })
                print(f"  Clicked: pixel ({x}, {y}) → board ({bx:.1f}, {by:.1f}) mm")
                
                if self.current_label and self.current_label in CONTROL_POINTS:
                    expected = CONTROL_POINTS[self.current_label]
                    error = np.sqrt((bx - expected[0])**2 + (by - expected[1])**2)
                    print(f"  Expected: ({expected[0]:.1f}, {expected[1]:.1f}) mm")
                    print(f"  Error: {error:.1f} mm")
            else:
                print(f"  Clicked: pixel ({x}, {y}) → OUT OF BOUNDS")
    
    def draw_overlay(self, frame: np.ndarray) -> np.ndarray:
        """Draw verification overlay on frame."""
        display = frame.copy()
        h, w = display.shape[:2]
        
        # Draw instruction panel
        overlay = display.copy()
        cv2.rectangle(overlay, (0, 0), (w, 100), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, display, 0.4, 0, display)
        
        # Title
        cv2.putText(display, f"Calibration Verification - Camera {self.camera_id}",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Instructions
        cv2.putText(display, "Click on control points to verify calibration",
                    (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        label_text = f"Current label: {self.current_label or 'None (press 1-9 to select)'}"
        cv2.putText(display, label_text, (10, 70), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        
        cv2.putText(display, "Keys: 1=bull, 2=T20, 3=D20, 4=T3, 5=D3, r=report, q=quit",
                    (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Draw clicked points
        for point in self.clicked_points:
            px, py = point['pixel']
            label = point['label'] or '?'
            
            # Draw crosshair
            cv2.drawMarker(display, (px, py), (0, 255, 0), 
                          cv2.MARKER_CROSS, 20, 2)
            
            # Draw label
            cv2.putText(display, label, (px + 10, py - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        # Draw coordinate grid if calibrated
        self._draw_coordinate_grid(display)
        
        return display
    
    def _draw_coordinate_grid(self, display: np.ndarray):
        """Draw board coordinate grid overlay."""
        # Draw concentric circles at key radii
        radii_mm = [6.35, 15.9, 99.0, 107.0, 162.0, 170.0]  # Bull, triple, double rings
        colors = [(255, 0, 0), (255, 0, 0), (0, 255, 255), (0, 255, 255), 
                  (255, 255, 0), (255, 255, 0)]
        
        for radius_mm, color in zip(radii_mm, colors):
            # Sample points around circle
            points = []
            for angle in np.linspace(0, 2*np.pi, 36):
                x = radius_mm * np.cos(angle)
                y = radius_mm * np.sin(angle)
                
                pixel = self.coordinate_mapper.map_to_image(self.camera_id, x, y)
                if pixel is not None:
                    u, v = pixel
                    if 0 <= u < self.width and 0 <= v < self.height:
                        points.append((int(u), int(v)))
            
            # Draw circle segments
            if len(points) > 2:
                for i in range(len(points) - 1):
                    cv2.line(display, points[i], points[i+1], color, 1)
                cv2.line(display, points[-1], points[0], color, 1)
        
        # Draw coordinate axes
        # X axis (red)
        x_start = self.coordinate_mapper.map_to_image(self.camera_id, -180, 0)
        x_end = self.coordinate_mapper.map_to_image(self.camera_id, 180, 0)
        if x_start and x_end:
            cv2.line(display, (int(x_start[0]), int(x_start[1])),
                    (int(x_end[0]), int(x_end[1])), (0, 0, 255), 1)
        
        # Y axis (green)
        y_start = self.coordinate_mapper.map_to_image(self.camera_id, 0, -180)
        y_end = self.coordinate_mapper.map_to_image(self.camera_id, 0, 180)
        if y_start and y_end:
            cv2.line(display, (int(y_start[0]), int(y_start[1])),
                    (int(y_end[0]), int(y_end[1])), (0, 255, 0), 1)
    
    def compute_statistics(self) -> dict:
        """Compute error statistics for clicked points."""
        errors = []
        
        for point in self.clicked_points:
            label = point['label']
            if label and label in CONTROL_POINTS:
                expected = CONTROL_POINTS[label]
                actual = point['board']
                error = np.sqrt((actual[0] - expected[0])**2 + 
                               (actual[1] - expected[1])**2)
                errors.append({
                    'label': label,
                    'expected': expected,
                    'actual': actual,
                    'error_mm': error,
                })
        
        if not errors:
            return {'num_points': 0}
        
        error_values = [e['error_mm'] for e in errors]
        
        return {
            'num_points': len(errors),
            'mean_error_mm': np.mean(error_values),
            'max_error_mm': np.max(error_values),
            'min_error_mm': np.min(error_values),
            'std_error_mm': np.std(error_values),
            'points': errors,
        }
    
    def print_report(self):
        """Print verification report."""
        stats = self.compute_statistics()
        
        print("\n" + "=" * 60)
        print("  Calibration Verification Report")
        print("=" * 60)
        print(f"\nCamera: {self.camera_id}")
        print(f"Points verified: {stats['num_points']}")
        
        if stats['num_points'] > 0:
            print(f"\nError Statistics:")
            print(f"  Mean error: {stats['mean_error_mm']:.2f} mm")
            print(f"  Max error:  {stats['max_error_mm']:.2f} mm")
            print(f"  Min error:  {stats['min_error_mm']:.2f} mm")
            print(f"  Std dev:    {stats['std_error_mm']:.2f} mm")
            
            # Quality assessment
            mean_error = stats['mean_error_mm']
            if mean_error < 5.0:
                quality = "✓ GOOD (< 5mm)"
            elif mean_error < 10.0:
                quality = "~ ACCEPTABLE (< 10mm)"
            else:
                quality = "✗ POOR (>= 10mm)"
            
            print(f"\nQuality: {quality}")
            
            print(f"\nPer-point errors:")
            for point in stats['points']:
                print(f"  {point['label']}: {point['error_mm']:.2f} mm")
        else:
            print("\nNo control points verified yet.")
        
        print("=" * 60 + "\n")
        
        return stats
    
    def save_report(self, output_dir: str = "calibration"):
        """Save verification report to JSON file."""
        stats = self.compute_statistics()
        
        report = {
            'camera_id': self.camera_id,
            'verification_date': datetime.now().isoformat(),
            'statistics': {
                'num_points': stats['num_points'],
                'mean_error_mm': stats.get('mean_error_mm', 0),
                'max_error_mm': stats.get('max_error_mm', 0),
                'min_error_mm': stats.get('min_error_mm', 0),
                'std_error_mm': stats.get('std_error_mm', 0),
            },
            'points': stats.get('points', []),
        }
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        output_file = output_path / f"verification_cam{self.camera_id}.json"
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"Report saved to: {output_file}")
        return output_file
    
    def run(self):
        """Run interactive verification UI."""
        # Open camera
        cap = cv2.VideoCapture(self.camera_id)
        if not cap.isOpened():
            print(f"Error: Could not open camera {self.camera_id}")
            return False
        
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        
        # Create window and set mouse callback
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, self.width, self.height)
        cv2.setMouseCallback(self.window_name, self.mouse_callback)
        
        print("\n" + "=" * 60)
        print("  Calibration Verification")
        print("=" * 60)
        print("\nInstructions:")
        print("  1. Select a control point label (1-9 keys)")
        print("  2. Click on that point in the camera view")
        print("  3. Repeat for multiple points")
        print("  4. Press 'r' to see report")
        print("  5. Press 's' to save report")
        print("  6. Press 'q' to quit")
        print("\nControl point keys:")
        print("  1=bull, 2=T20, 3=D20, 4=T3, 5=D3")
        print("  6=T6, 7=D6, 8=T11, 9=D11")
        print("=" * 60 + "\n")
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    continue
                
                self.frame = frame
                display = self.draw_overlay(frame)
                cv2.imshow(self.window_name, display)
                
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    self.print_report()
                elif key == ord('s'):
                    self.save_report()
                elif key == ord('1'):
                    self.current_label = 'bull'
                    print("Selected: bull")
                elif key == ord('2'):
                    self.current_label = 'T20'
                    print("Selected: T20")
                elif key == ord('3'):
                    self.current_label = 'D20'
                    print("Selected: D20")
                elif key == ord('4'):
                    self.current_label = 'T3'
                    print("Selected: T3")
                elif key == ord('5'):
                    self.current_label = 'D3'
                    print("Selected: D3")
                elif key == ord('6'):
                    self.current_label = 'T6'
                    print("Selected: T6")
                elif key == ord('7'):
                    self.current_label = 'D6'
                    print("Selected: D6")
                elif key == ord('8'):
                    self.current_label = 'T11'
                    print("Selected: T11")
                elif key == ord('9'):
                    self.current_label = 'D11'
                    print("Selected: D11")
                elif key == ord('c'):
                    # Clear points
                    self.clicked_points = []
                    print("Cleared all points")
        
        finally:
            cap.release()
            cv2.destroyWindow(self.window_name)
        
        return True


def main():
    """Main entry point for verification script."""
    parser = argparse.ArgumentParser(
        description='Verify calibration accuracy with control points',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python calibration/verify_calibration.py
    python calibration/verify_calibration.py --camera 0
    python calibration/verify_calibration.py --save-report
        """
    )
    
    parser.add_argument(
        '--camera', '-c',
        type=int,
        default=0,
        help='Camera to verify (default: 0)'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config.toml',
        help='Path to configuration file (default: config.toml)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.verbose)
    
    # Load configuration
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    
    # Initialize coordinate mapper
    calibration_dir = config.get('calibration', {}).get('calibration_dir', 'calibration')
    
    try:
        coordinate_mapper = CoordinateMapper(config, calibration_dir)
    except Exception as e:
        logger.error(f"Failed to initialize CoordinateMapper: {e}")
        sys.exit(1)
    
    # Check if camera is calibrated
    if not coordinate_mapper.is_calibrated(args.camera):
        logger.error(f"Camera {args.camera} is not calibrated")
        logger.error("Run intrinsic and extrinsic calibration first")
        sys.exit(1)
    
    # Run verification UI
    ui = VerificationUI(args.camera, config, coordinate_mapper)
    success = ui.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
