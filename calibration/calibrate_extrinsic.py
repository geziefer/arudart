#!/usr/bin/env python3
"""
Extrinsic Camera Calibration Script

Computes homography transformation from camera image plane to board plane
using ARUCO markers. Calibrates all cameras in sequence.

Usage:
    python calibration/calibrate_extrinsic.py
    python calibration/calibrate_extrinsic.py --camera 0
    python calibration/calibrate_extrinsic.py --visualize

Workflow:
1. Initialize all cameras (or single camera if specified)
2. For each camera:
   a. Capture current frame
   b. Detect ARUCO markers
   c. Compute homography from marker correspondences
   d. Verify reprojection error
   e. Save to calibration/homography_cam{N}.json
3. Display summary with marker counts and reprojection errors

Requirements: AC-6.3.1, AC-6.3.2, AC-6.3.3, AC-6.3.4
"""

import argparse
import logging
import sys
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

from src.calibration.aruco_detector import ArucoDetector
from src.calibration.extrinsic_calibrator import ExtrinsicCalibrator


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Set up logging for the calibration script."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger('calibrate_extrinsic')


def load_config(config_path: str = "config.toml") -> dict:
    """Load configuration from TOML file."""
    config_file = project_root / config_path
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    
    with open(config_file, 'rb') as f:
        return tomli.load(f)


def draw_marker_overlay(frame: np.ndarray, detected_markers: dict,
                        aruco_detector: ArucoDetector) -> np.ndarray:
    """Draw detected markers and status on frame."""
    display = aruco_detector.draw_markers(frame, detected_markers)
    h, w = display.shape[:2]
    
    # Semi-transparent overlay for text background
    overlay = display.copy()
    cv2.rectangle(overlay, (0, 0), (w, 80), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, display, 0.4, 0, display)
    
    # Title
    cv2.putText(display, "Extrinsic Calibration", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    # Marker count
    num_markers = len(detected_markers)
    if num_markers >= 4:
        color = (0, 255, 0)
        status = f"Markers detected: {num_markers} (OK)"
    else:
        color = (0, 0, 255)
        status = f"Markers detected: {num_markers} (need at least 4)"
    
    cv2.putText(display, status, (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    
    # Instructions
    cv2.putText(display, "Press SPACE to calibrate | q to quit", (10, h - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    
    return display


def calibrate_single_camera(camera_id: int, config: dict, 
                            aruco_detector: ArucoDetector,
                            calibrator: ExtrinsicCalibrator,
                            visualize: bool = False,
                            logger: logging.Logger = None) -> dict | None:
    """
    Calibrate a single camera.
    
    Args:
        camera_id: Camera device index
        config: Configuration dictionary
        aruco_detector: ArucoDetector instance
        calibrator: ExtrinsicCalibrator instance
        visualize: Show visualization window
        logger: Logger instance
    
    Returns:
        Calibration result dict or None if failed
    """
    if logger is None:
        logger = logging.getLogger('calibrate_extrinsic')
    
    # Get camera settings
    camera_settings = config.get('camera_settings', {})
    width = camera_settings.get('width', 800)
    height = camera_settings.get('height', 600)
    
    # Open camera
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        logger.error(f"Failed to open camera {camera_id}")
        return None
    
    # Set camera resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    
    result = None
    
    try:
        if visualize:
            # Interactive mode with visualization
            window_name = f"Extrinsic Calibration - Camera {camera_id}"
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, width, height)
            
            print(f"\nCamera {camera_id}: Press SPACE to calibrate, 'q' to skip")
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"Camera {camera_id}: Failed to read frame")
                    continue
                
                # Detect markers
                detected_markers = aruco_detector.detect_markers(frame)
                
                # Draw overlay
                display = draw_marker_overlay(frame, detected_markers, aruco_detector)
                cv2.imshow(window_name, display)
                
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q'):
                    logger.info(f"Camera {camera_id}: Skipped by user")
                    break
                elif key == ord(' '):
                    # Perform calibration
                    calibration_result = calibrator.calibrate(camera_id, frame)
                    
                    if calibration_result is not None:
                        homography, debug_info = calibration_result
                        
                        # Save calibration
                        calibration_dir = config.get('calibration', {}).get(
                            'calibration_dir', 'calibration'
                        )
                        calibrator.save_calibration(
                            camera_id, homography, debug_info, calibration_dir
                        )
                        
                        result = {
                            'camera_id': camera_id,
                            'success': True,
                            'markers_detected': len(debug_info.get('markers_detected', [])),
                            'markers_used': len(debug_info.get('markers_used', [])),
                            'reprojection_error': debug_info.get('reprojection_error', 0.0),
                        }
                        
                        # Show success feedback
                        success_frame = frame.copy()
                        overlay = np.zeros_like(success_frame)
                        overlay[:, :] = (0, 255, 0)
                        cv2.addWeighted(overlay, 0.3, success_frame, 0.7, 0, success_frame)
                        cv2.putText(success_frame, "CALIBRATION SAVED!", 
                                    (width // 4, height // 2),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
                        cv2.imshow(window_name, success_frame)
                        cv2.waitKey(500)
                    else:
                        # Show failure feedback
                        fail_frame = frame.copy()
                        overlay = np.zeros_like(fail_frame)
                        overlay[:, :] = (0, 0, 255)
                        cv2.addWeighted(overlay, 0.3, fail_frame, 0.7, 0, fail_frame)
                        cv2.putText(fail_frame, "CALIBRATION FAILED!", 
                                    (width // 4, height // 2),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
                        cv2.imshow(window_name, fail_frame)
                        cv2.waitKey(500)
                        continue  # Let user try again
                    
                    break
            
            cv2.destroyWindow(window_name)
        
        else:
            # Non-interactive mode - capture single frame and calibrate
            ret, frame = cap.read()
            if not ret:
                logger.error(f"Camera {camera_id}: Failed to capture frame")
                return None
            
            # Perform calibration
            calibration_result = calibrator.calibrate(camera_id, frame)
            
            if calibration_result is not None:
                homography, debug_info = calibration_result
                
                # Save calibration
                calibration_dir = config.get('calibration', {}).get(
                    'calibration_dir', 'calibration'
                )
                calibrator.save_calibration(
                    camera_id, homography, debug_info, calibration_dir
                )
                
                result = {
                    'camera_id': camera_id,
                    'success': True,
                    'markers_detected': len(debug_info.get('markers_detected', [])),
                    'markers_used': len(debug_info.get('markers_used', [])),
                    'reprojection_error': debug_info.get('reprojection_error', 0.0),
                }
            else:
                result = {
                    'camera_id': camera_id,
                    'success': False,
                    'markers_detected': 0,
                    'markers_used': 0,
                    'reprojection_error': float('inf'),
                }
    
    finally:
        cap.release()
    
    return result


def run_calibration(camera_ids: list[int], config: dict, 
                    visualize: bool = False,
                    logger: logging.Logger = None) -> list[dict]:
    """
    Run extrinsic calibration for specified cameras.
    
    Args:
        camera_ids: List of camera device indices
        config: Configuration dictionary
        visualize: Show visualization windows
        logger: Logger instance
    
    Returns:
        List of calibration results
    """
    if logger is None:
        logger = logging.getLogger('calibrate_extrinsic')
    
    # Initialize detector and calibrator
    aruco_detector = ArucoDetector(config)
    calibrator = ExtrinsicCalibrator(config, aruco_detector)
    
    # Get marker positions for display
    marker_positions = calibrator.marker_positions
    logger.info(f"Configured marker positions: {len(marker_positions)} markers")
    for marker_id, (x, y) in sorted(marker_positions.items()):
        logger.info(f"  Marker {marker_id}: ({x:.1f}, {y:.1f}) mm")
    
    results = []
    
    print("\n" + "=" * 60)
    print("  Extrinsic Calibration")
    print("=" * 60)
    print(f"\nCalibrating cameras: {camera_ids}")
    print(f"Marker positions configured: {len(marker_positions)}")
    print("\nEnsure ARUCO markers are visible to all cameras.")
    print("=" * 60 + "\n")
    
    for camera_id in camera_ids:
        logger.info(f"Calibrating camera {camera_id}...")
        
        result = calibrate_single_camera(
            camera_id, config, aruco_detector, calibrator,
            visualize=visualize, logger=logger
        )
        
        if result is not None:
            results.append(result)
            
            if result['success']:
                logger.info(
                    f"Camera {camera_id}: SUCCESS - "
                    f"{result['markers_used']} markers, "
                    f"error {result['reprojection_error']:.2f} px"
                )
            else:
                logger.warning(f"Camera {camera_id}: FAILED")
        else:
            results.append({
                'camera_id': camera_id,
                'success': False,
                'markers_detected': 0,
                'markers_used': 0,
                'reprojection_error': float('inf'),
            })
            logger.warning(f"Camera {camera_id}: FAILED (could not open camera)")
    
    return results


def print_summary(results: list[dict]):
    """Print calibration summary."""
    print("\n" + "=" * 60)
    print("  Calibration Summary")
    print("=" * 60)
    
    success_count = sum(1 for r in results if r['success'])
    total_count = len(results)
    
    print(f"\nCameras calibrated: {success_count}/{total_count}")
    print()
    
    for result in results:
        camera_id = result['camera_id']
        if result['success']:
            markers = result['markers_used']
            error = result['reprojection_error']
            
            # Quality indicator
            if error < 3.0:
                quality = "✓ GOOD"
            elif error < 5.0:
                quality = "~ OK"
            else:
                quality = "⚠ MARGINAL"
            
            print(f"  Camera {camera_id}: {quality}")
            print(f"    Markers used: {markers}")
            print(f"    Reprojection error: {error:.2f} pixels")
        else:
            print(f"  Camera {camera_id}: ✗ FAILED")
    
    print()
    
    if success_count == total_count:
        print("✓ All cameras calibrated successfully!")
    elif success_count > 0:
        print(f"⚠ {total_count - success_count} camera(s) failed calibration")
    else:
        print("✗ All cameras failed calibration")
        print("\nTroubleshooting:")
        print("  - Ensure ARUCO markers are visible and well-lit")
        print("  - Check marker positions in config.toml match physical placement")
        print("  - Try running with --visualize to see marker detection")
    
    print("=" * 60 + "\n")


def main():
    """Main entry point for extrinsic calibration script."""
    parser = argparse.ArgumentParser(
        description='Extrinsic Camera Calibration using ARUCO markers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python calibration/calibrate_extrinsic.py
    python calibration/calibrate_extrinsic.py --camera 0
    python calibration/calibrate_extrinsic.py --visualize
    python calibration/calibrate_extrinsic.py --camera 1 --visualize
        """
    )
    
    parser.add_argument(
        '--camera', '-c',
        type=int,
        default=None,
        help='Calibrate single camera (default: all cameras 0, 1, 2)'
    )
    
    parser.add_argument(
        '--visualize', '-v',
        action='store_true',
        help='Show visualization window with marker detection'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config.toml',
        help='Path to configuration file (default: config.toml)'
    )
    
    parser.add_argument(
        '--verbose',
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
    
    # Determine which cameras to calibrate
    if args.camera is not None:
        camera_ids = [args.camera]
    else:
        camera_ids = [0, 1, 2]
    
    # Run calibration
    results = run_calibration(
        camera_ids=camera_ids,
        config=config,
        visualize=args.visualize,
        logger=logger
    )
    
    # Print summary
    print_summary(results)
    
    # Exit with appropriate code
    success_count = sum(1 for r in results if r['success'])
    sys.exit(0 if success_count == len(results) else 1)


if __name__ == "__main__":
    main()
