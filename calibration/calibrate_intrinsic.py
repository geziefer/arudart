#!/usr/bin/env python3
"""
Intrinsic Camera Calibration Script

Interactive script for capturing chessboard images and computing intrinsic calibration.
Uses the IntrinsicCalibrator class to perform calibration.

Usage:
    python calibration/calibrate_intrinsic.py --camera 0
    python calibration/calibrate_intrinsic.py --camera 1
    python calibration/calibrate_intrinsic.py --camera 2

Workflow:
1. Initialize camera and display live preview
2. Detect chessboard in each frame
3. Show detection overlay (corners highlighted)
4. User presses SPACE to capture when chessboard at good angle
5. Capture 20-30 images at different angles
6. Compute calibration using cv2.calibrateCamera()
7. Display reprojection error
8. Save to calibration/intrinsic_cam{N}.json

Requirements: AC-6.1.1, AC-6.1.2, AC-6.1.3, AC-6.1.4
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

from src.calibration.intrinsic_calibrator import IntrinsicCalibrator


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Set up logging for the calibration script."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger('calibrate_intrinsic')


def load_config(config_path: str = "config.toml") -> dict:
    """Load configuration from TOML file."""
    config_file = project_root / config_path
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    
    with open(config_file, 'rb') as f:
        return tomli.load(f)


def draw_instructions(frame: np.ndarray, captured: int, target: int, 
                      chessboard_found: bool, reprojection_error: float | None) -> np.ndarray:
    """Draw instruction overlay on the frame."""
    display = frame.copy()
    h, w = display.shape[:2]
    
    # Semi-transparent overlay for text background
    overlay = display.copy()
    cv2.rectangle(overlay, (0, 0), (w, 120), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, display, 0.4, 0, display)
    
    # Title
    cv2.putText(display, "Intrinsic Calibration", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    # Instructions
    cv2.putText(display, "Move chessboard to different angles", (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    cv2.putText(display, "SPACE: capture | q: finish early", (10, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    
    # Status
    status_text = f"Captured: {captured}/{target} images"
    cv2.putText(display, status_text, (10, 95),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    # Reprojection error (if available)
    if reprojection_error is not None:
        error_color = (0, 255, 0) if reprojection_error < 0.5 else (0, 165, 255)
        error_text = f"Current reprojection error: {reprojection_error:.3f} pixels"
        cv2.putText(display, error_text, (10, 115),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, error_color, 1)
    
    # Chessboard detection status (bottom of frame)
    if chessboard_found:
        status = "Chessboard DETECTED - Press SPACE to capture"
        color = (0, 255, 0)
    else:
        status = "Chessboard not detected - adjust position"
        color = (0, 0, 255)
    
    cv2.putText(display, status, (10, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    
    return display


def show_capture_feedback(window_name: str, frame: np.ndarray, count: int):
    """Show brief visual feedback when image is captured."""
    feedback = frame.copy()
    h, w = feedback.shape[:2]
    
    # Green flash overlay
    overlay = np.zeros_like(feedback)
    overlay[:, :] = (0, 255, 0)
    cv2.addWeighted(overlay, 0.3, feedback, 0.7, 0, feedback)
    
    # Captured text
    text = f"CAPTURED! ({count})"
    text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 3)[0]
    text_x = (w - text_size[0]) // 2
    text_y = (h + text_size[1]) // 2
    cv2.putText(feedback, text, (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
    
    cv2.imshow(window_name, feedback)
    cv2.waitKey(200)


def run_calibration(camera_id: int, config: dict, target_images: int = 25,
                    logger: logging.Logger = None) -> bool:
    """
    Run interactive intrinsic calibration for a camera.
    
    Args:
        camera_id: Camera device index to calibrate
        config: Configuration dictionary
        target_images: Target number of images to capture
        logger: Logger instance
    
    Returns:
        True if calibration succeeded, False otherwise
    """
    if logger is None:
        logger = logging.getLogger('calibrate_intrinsic')
    
    # Initialize calibrator
    calibrator = IntrinsicCalibrator(config)
    chessboard_size = calibrator.chessboard_size
    
    logger.info(f"Starting intrinsic calibration for camera {camera_id}")
    logger.info(f"Chessboard size: {chessboard_size[0]}x{chessboard_size[1]} inner corners")
    logger.info(f"Square size: {calibrator.square_size_mm}mm")
    logger.info(f"Target: {target_images} images")
    
    # Get camera settings
    camera_settings = config.get('camera_settings', {})
    width = camera_settings.get('width', 800)
    height = camera_settings.get('height', 600)
    
    # Open camera
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        logger.error(f"Failed to open camera {camera_id}")
        return False
    
    # Set camera resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    
    # Verify resolution
    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    logger.info(f"Camera resolution: {actual_width}x{actual_height}")
    
    # Create window
    window_name = f"Intrinsic Calibration - Camera {camera_id}"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, width, height)
    
    # Termination criteria for corner sub-pixel refinement
    subpix_criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30, 0.001
    )
    
    captured_images = []
    current_reprojection_error = None
    
    print("\n" + "=" * 60)
    print(f"  Intrinsic Calibration - Camera {camera_id}")
    print("=" * 60)
    print("\nInstructions:")
    print("  - Hold chessboard in front of camera")
    print("  - Move to different angles and distances")
    print("  - Press SPACE when chessboard is detected (green)")
    print(f"  - Capture {target_images} images at various angles")
    print("  - Press 'q' to finish early (minimum 10 images)")
    print("\nTips for good calibration:")
    print("  - Cover the entire frame with chessboard positions")
    print("  - Include tilted angles (not just flat)")
    print("  - Vary distance from camera")
    print("  - Ensure good lighting (no glare)")
    print("=" * 60 + "\n")
    
    try:
        while len(captured_images) < target_images:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Failed to read frame from camera")
                continue
            
            # Convert to grayscale for chessboard detection
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Find chessboard corners
            found, corners = cv2.findChessboardCorners(
                gray, chessboard_size,
                cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
            )
            
            # Create display frame
            display_frame = frame.copy()
            
            if found:
                # Refine corner positions to sub-pixel accuracy
                corners_refined = cv2.cornerSubPix(
                    gray, corners, (11, 11), (-1, -1), subpix_criteria
                )
                
                # Draw detected corners
                cv2.drawChessboardCorners(
                    display_frame, chessboard_size, corners_refined, found
                )
            
            # Draw instruction overlay
            display_frame = draw_instructions(
                display_frame, 
                len(captured_images), 
                target_images,
                found,
                current_reprojection_error
            )
            
            cv2.imshow(window_name, display_frame)
            
            # Handle key presses
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                logger.info("User requested early finish")
                break
            elif key == ord(' ') and found:
                # Capture this image
                captured_images.append(frame.copy())
                count = len(captured_images)
                logger.info(f"Captured image {count}/{target_images}")
                
                # Show capture feedback
                show_capture_feedback(window_name, display_frame, count)
                
                # Compute running reprojection error if we have enough images
                if count >= 5:
                    try:
                        _, _, current_reprojection_error = calibrator.calibrate(captured_images)
                    except ValueError:
                        pass  # Not enough valid images yet
    
    except KeyboardInterrupt:
        logger.info("Calibration interrupted by user")
    
    finally:
        cap.release()
        cv2.destroyWindow(window_name)
    
    # Check if we have enough images
    if len(captured_images) < 10:
        logger.error(f"Insufficient images captured: {len(captured_images)} (minimum 10 required)")
        print(f"\n❌ Calibration failed: Only {len(captured_images)} images captured (need at least 10)")
        return False
    
    logger.info(f"Captured {len(captured_images)} calibration images")
    
    # Run calibration
    print(f"\nRunning calibration with {len(captured_images)} images...")
    
    try:
        camera_matrix, distortion_coeffs, reprojection_error = calibrator.calibrate(captured_images)
    except ValueError as e:
        logger.error(f"Calibration failed: {e}")
        print(f"\n❌ Calibration failed: {e}")
        return False
    
    # Display results
    print("\n" + "=" * 60)
    print("  Calibration Results")
    print("=" * 60)
    print(f"\nCamera Matrix:")
    print(f"  fx = {camera_matrix[0, 0]:.2f}")
    print(f"  fy = {camera_matrix[1, 1]:.2f}")
    print(f"  cx = {camera_matrix[0, 2]:.2f}")
    print(f"  cy = {camera_matrix[1, 2]:.2f}")
    print(f"\nDistortion Coefficients:")
    print(f"  k1 = {distortion_coeffs[0]:.6f}")
    print(f"  k2 = {distortion_coeffs[1]:.6f}")
    print(f"  p1 = {distortion_coeffs[2]:.6f}")
    print(f"  p2 = {distortion_coeffs[3]:.6f}")
    print(f"  k3 = {distortion_coeffs[4]:.6f}")
    print(f"\nReprojection Error: {reprojection_error:.4f} pixels")
    
    # Check quality
    if reprojection_error < 0.5:
        print(f"✓ Quality: GOOD (error < 0.5 pixels)")
    else:
        print(f"⚠ Quality: MARGINAL (error >= 0.5 pixels)")
        print("  Consider recalibrating with more images at different angles")
    
    # Save calibration
    calibration_dir = config.get('calibration', {}).get('calibration_dir', 'calibration')
    output_file = calibrator.save_calibration(
        camera_id, camera_matrix, distortion_coeffs, reprojection_error, calibration_dir
    )
    
    print(f"\n✓ Calibration saved to: {output_file}")
    print("=" * 60 + "\n")
    
    return True


def main():
    """Main entry point for intrinsic calibration script."""
    parser = argparse.ArgumentParser(
        description='Intrinsic Camera Calibration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python calibration/calibrate_intrinsic.py --camera 0
    python calibration/calibrate_intrinsic.py --camera 1 --images 30
    python calibration/calibrate_intrinsic.py --camera 2 --verbose
        """
    )
    
    parser.add_argument(
        '--camera', '-c',
        type=int,
        required=True,
        help='Camera device index to calibrate (0, 1, or 2)'
    )
    
    parser.add_argument(
        '--images', '-n',
        type=int,
        default=25,
        help='Target number of images to capture (default: 25, minimum: 10)'
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
    
    # Validate arguments
    if args.images < 10:
        logger.warning(f"Target images ({args.images}) is below minimum (10), using 10")
        args.images = 10
    
    # Run calibration
    success = run_calibration(
        camera_id=args.camera,
        config=config,
        target_images=args.images,
        logger=logger
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
