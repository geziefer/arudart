#!/usr/bin/env python3
"""
Intrinsic calibration script for ARU-DART cameras.

Captures chessboard images from a camera and computes intrinsic
parameters (camera matrix + distortion coefficients).

Usage:
    # Live camera capture (interactive)
    python calibration/calibrate_intrinsic.py --camera 0

    # From saved images directory
    python calibration/calibrate_intrinsic.py --camera 0 --from-dir data/chessboard/cam0/

Controls (live mode):
    SPACE  - Capture current frame (if chessboard detected)
    ESC/q  - Finish capturing and run calibration
    r      - Reset (discard all captured images)
"""

import argparse
import logging
import sys
from pathlib import Path

import cv2
import numpy as np

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.calibration.intrinsic_calibrator import IntrinsicCalibrator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.toml") -> dict:
    """Load configuration from TOML file."""
    with open(config_path, 'rb') as f:
        return tomllib.load(f)


def calibrate_from_directory(
    camera_id: int,
    image_dir: str,
    calibrator: IntrinsicCalibrator,
    output_dir: str = "calibration"
) -> bool:
    """
    Run calibration from a directory of saved chessboard images.
    
    Args:
        camera_id: Camera identifier
        image_dir: Directory containing chessboard images
        calibrator: IntrinsicCalibrator instance
        output_dir: Output directory for calibration JSON
    
    Returns:
        True if calibration succeeded
    """
    image_path = Path(image_dir)
    extensions = ("*.jpg", "*.jpeg", "*.png", "*.bmp")
    image_files = []
    for ext in extensions:
        image_files.extend(sorted(image_path.glob(ext)))
    
    if not image_files:
        logger.error(f"No images found in {image_dir}")
        return False
    
    logger.info(f"Found {len(image_files)} images in {image_dir}")
    
    images = []
    for f in image_files:
        img = cv2.imread(str(f))
        if img is not None:
            images.append(img)
        else:
            logger.warning(f"Failed to load: {f}")
    
    result = calibrator.calibrate(images)
    if result is None:
        logger.error("Calibration failed")
        return False
    
    calibrator.save(camera_id, result, output_dir)
    _print_summary(camera_id, result)
    return True


def calibrate_live(
    camera_id: int,
    calibrator: IntrinsicCalibrator,
    config: dict,
    output_dir: str = "calibration",
    min_images: int = 10,
    max_images: int = 30
) -> bool:
    """
    Interactive live calibration with chessboard capture.
    
    Args:
        camera_id: Camera identifier (logical: 0, 1, 2)
        calibrator: IntrinsicCalibrator instance
        config: Full config dict for camera manager
        output_dir: Output directory
        min_images: Minimum captures before allowing calibration
        max_images: Maximum captures
    
    Returns:
        True if calibration succeeded
    """
    from src.camera.camera_manager import CameraManager
    import time
    
    logger.info("Initializing cameras...")
    camera_manager = CameraManager(config)
    camera_manager.start_all()
    time.sleep(1.0)
    
    all_camera_ids = sorted(camera_manager.get_camera_ids())
    if camera_id >= len(all_camera_ids):
        logger.error(
            f"Camera {camera_id} not available "
            f"(only {len(all_camera_ids)} detected)"
        )
        camera_manager.stop_all()
        return False
    
    physical_id = all_camera_ids[camera_id]
    logger.info(
        f"Using camera {camera_id} (device {physical_id})"
    )
    
    captured_images = []
    window_name = f"Intrinsic Calibration - Camera {camera_id}"
    
    logger.info("Controls: SPACE=capture, ESC/q=calibrate, r=reset")
    logger.info(
        f"Capture {min_images}-{max_images} images with chessboard "
        f"at different angles and positions"
    )
    
    try:
        while True:
            frame = camera_manager.get_latest_frame(physical_id)
            if frame is None:
                continue
            
            display = frame.copy()
            corners = calibrator.detect_corners(frame)
            
            # Draw corners if detected
            if corners is not None:
                display = calibrator.draw_corners(display, corners)
                status_color = (0, 255, 0)  # green
                status_text = "Chessboard DETECTED - press SPACE to capture"
            else:
                status_color = (0, 0, 255)  # red
                status_text = "No chessboard found"
            
            # Draw status bar
            cv2.rectangle(display, (0, 0), (display.shape[1], 35), (0, 0, 0), -1)
            cv2.putText(
                display, status_text, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 1
            )
            
            count_text = (
                f"Captured: {len(captured_images)}/{max_images} "
                f"(min {min_images})"
            )
            cv2.putText(
                display, count_text,
                (display.shape[1] - 300, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1
            )
            
            cv2.imshow(window_name, display)
            key = cv2.waitKey(30) & 0xFF
            
            if key == ord(' ') and corners is not None:
                # Capture
                captured_images.append(frame.copy())
                logger.info(
                    f"Captured image {len(captured_images)}/{max_images}"
                )
                
                if len(captured_images) >= max_images:
                    logger.info("Maximum images reached, running calibration")
                    break
            
            elif key == 27 or key == ord('q'):
                if len(captured_images) >= min_images:
                    logger.info("Running calibration...")
                    break
                elif len(captured_images) > 0:
                    logger.warning(
                        f"Need at least {min_images} images, "
                        f"have {len(captured_images)}"
                    )
                else:
                    logger.info("Cancelled")
                    camera_manager.stop_all()
                    cv2.destroyAllWindows()
                    return False
            
            elif key == ord('r'):
                captured_images.clear()
                logger.info("Reset - all captures discarded")
    
    finally:
        camera_manager.stop_all()
        cv2.destroyAllWindows()
    
    if len(captured_images) < min_images:
        logger.error(
            f"Insufficient images: {len(captured_images)} < {min_images}"
        )
        return False
    
    # Run calibration
    result = calibrator.calibrate(captured_images)
    if result is None:
        logger.error("Calibration failed")
        return False
    
    calibrator.save(camera_id, result, output_dir)
    _print_summary(camera_id, result)
    return True


def _print_summary(camera_id: int, result: dict):
    """Print calibration summary."""
    logger.info("=== Intrinsic Calibration Summary ===")
    logger.info(f"Camera: {camera_id}")
    logger.info(f"Images used: {result['num_images']}")
    logger.info(f"Image size: {result['image_size']}")
    logger.info(
        f"Reprojection error: {result['reprojection_error']:.4f} pixels"
    )
    
    K = result["camera_matrix"]
    logger.info(f"Focal length: fx={K[0,0]:.1f}, fy={K[1,1]:.1f}")
    logger.info(f"Principal point: cx={K[0,2]:.1f}, cy={K[1,2]:.1f}")
    
    D = result["distortion_coeffs"]
    logger.info(f"Distortion: k1={D[0]:.4f}, k2={D[1]:.4f}")
    
    if result["reprojection_error"] < 0.5:
        logger.info("Quality: GOOD (< 0.5px)")
    elif result["reprojection_error"] < 1.0:
        logger.warning("Quality: ACCEPTABLE (< 1.0px)")
    else:
        logger.error("Quality: POOR (>= 1.0px) - consider recalibrating")


def main():
    parser = argparse.ArgumentParser(
        description="Intrinsic camera calibration using chessboard pattern"
    )
    parser.add_argument(
        '--camera', type=int, required=True,
        choices=[0, 1, 2],
        help='Camera to calibrate (0, 1, or 2)'
    )
    parser.add_argument(
        '--from-dir', type=str,
        help='Calibrate from directory of saved chessboard images'
    )
    parser.add_argument(
        '--config', type=str, default='config.toml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--output', type=str, default='calibration',
        help='Output directory for calibration files'
    )
    parser.add_argument(
        '--min-images', type=int, default=10,
        help='Minimum number of chessboard captures (default: 10)'
    )
    parser.add_argument(
        '--max-images', type=int, default=30,
        help='Maximum number of chessboard captures (default: 30)'
    )
    
    args = parser.parse_args()
    
    config = load_config(args.config)
    calibrator = IntrinsicCalibrator(config)
    
    if args.from_dir:
        success = calibrate_from_directory(
            args.camera, args.from_dir, calibrator, args.output
        )
    else:
        success = calibrate_live(
            args.camera, calibrator, config, args.output,
            args.min_images, args.max_images
        )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
