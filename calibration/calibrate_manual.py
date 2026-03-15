#!/usr/bin/env python3
"""
Manual calibration script for ARU-DART coordinate mapping.

This script runs interactive manual calibration for each camera, allowing
the user to click on known control points to establish pixel-to-board
coordinate correspondences.

Usage:
    # With live cameras
    python calibration/calibrate_manual.py [--camera CAMERA_ID]

    # With saved images (no cameras needed)
    python calibration/calibrate_manual.py --from-image data/testimages/BS/BS10_cam0_pre.jpg --camera 0
"""

import argparse
import logging
import sys
from pathlib import Path

import cv2

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.calibration import BoardGeometry, HomographyCalculator, ManualCalibrator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.toml") -> dict:
    """Load configuration from TOML file."""
    with open(config_path, 'rb') as f:
        config = tomllib.load(f)
    return config


def calibrate_from_frame(
    camera_id: int,
    frame,
    board_geometry: BoardGeometry,
    homography_calculator: HomographyCalculator,
    output_dir: str = "calibration"
) -> bool:
    """
    Run manual calibration for a single camera using a provided frame.
    
    Args:
        camera_id: Camera identifier (0, 1, 2)
        frame: BGR image (numpy array)
        board_geometry: BoardGeometry instance
        homography_calculator: HomographyCalculator instance
        output_dir: Output directory for calibration files
    
    Returns:
        True if calibration successful, False otherwise
    """
    logger.info(f"=== Calibrating camera {camera_id} ===")
    logger.info(f"Frame shape: {frame.shape}")
    
    calibrator = ManualCalibrator(board_geometry)
    
    try:
        point_pairs = calibrator.calibrate(frame)
        
        if len(point_pairs) < 4:
            logger.error(f"Insufficient points collected: {len(point_pairs)} < 4")
            return False
        
        logger.info(f"Collected {len(point_pairs)} point pairs")
        
        # Compute homography
        result = homography_calculator.compute(point_pairs)
        
        if result is None:
            logger.error("Failed to compute homography")
            return False
        
        homography, metadata = result
        
        # Save homography
        homography_calculator.save(camera_id, homography, metadata, output_dir)
        
        # Display summary
        logger.info("=== Calibration Summary ===")
        logger.info(f"Camera: {camera_id}")
        logger.info(f"Points: {metadata['num_points']}")
        logger.info(f"Inliers: {metadata['num_inliers']}")
        logger.info(f"Reprojection error: {metadata['reprojection_error_mm']:.2f}mm")
        
        return True
    
    except Exception as e:
        logger.error(f"Error during calibration: {e}", exc_info=True)
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Manual calibration for ARU-DART coordinate mapping"
    )
    parser.add_argument(
        '--camera',
        type=int,
        choices=[0, 1, 2],
        help='Calibrate only specified camera (0, 1, or 2)'
    )
    parser.add_argument(
        '--from-image',
        type=str,
        help='Calibrate from saved image file instead of live camera'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='config.toml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='calibration',
        help='Output directory for calibration files'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    logger.info(f"Loading configuration from {args.config}")
    config = load_config(args.config)
    
    # Initialize components
    board_geometry = BoardGeometry()
    calibration_config = config.get('calibration', {})
    homography_config = calibration_config.get('homography', {})
    homography_calculator = HomographyCalculator(homography_config)
    
    # Mode: from image file
    if args.from_image:
        camera_id = args.camera if args.camera is not None else 0
        
        image_path = Path(args.from_image)
        if not image_path.exists():
            logger.error(f"Image file not found: {image_path}")
            sys.exit(1)
        
        frame = cv2.imread(str(image_path))
        if frame is None:
            logger.error(f"Failed to load image: {image_path}")
            sys.exit(1)
        
        logger.info(f"Loaded image: {image_path}")
        success = calibrate_from_frame(
            camera_id, frame, board_geometry, homography_calculator, args.output
        )
        
        cv2.destroyAllWindows()
        sys.exit(0 if success else 1)
    
    # Mode: live cameras
    from src.camera.camera_manager import CameraManager
    import time
    
    logger.info("Initializing cameras...")
    camera_manager = CameraManager(config)
    camera_manager.start_all()
    
    # Wait for cameras to capture first frames
    time.sleep(1.0)
    
    # Determine which cameras to calibrate
    all_camera_ids = sorted(camera_manager.get_camera_ids())
    
    if not all_camera_ids:
        logger.error("No cameras detected - check connections")
        camera_manager.stop_all()
        sys.exit(1)
    
    logger.info(f"Detected {len(all_camera_ids)} cameras: {all_camera_ids}")
    
    if args.camera is not None:
        if args.camera < len(all_camera_ids):
            camera_ids = [all_camera_ids[args.camera]]
            logger.info(f"Calibrating camera {args.camera} (device {camera_ids[0]})")
        else:
            logger.error(f"Camera {args.camera} not available (only {len(all_camera_ids)} detected)")
            camera_manager.stop_all()
            sys.exit(1)
    else:
        camera_ids = all_camera_ids
    
    # Calibrate each camera
    results = {}
    for camera_id in camera_ids:
        logger.info(f"Capturing frame from camera {camera_id}...")
        frame = camera_manager.get_latest_frame(camera_id)
        
        if frame is None:
            logger.error(f"Failed to capture frame from camera {camera_id}")
            results[camera_id] = False
            continue
        
        success = calibrate_from_frame(
            camera_id, frame, board_geometry, homography_calculator, args.output
        )
        results[camera_id] = success
        
        if not success:
            logger.warning(f"Calibration failed for camera {camera_id}")
        
        # Pause between cameras
        if camera_id != camera_ids[-1]:
            logger.info("Press any key to continue to next camera...")
            cv2.waitKey(0)
            cv2.destroyAllWindows()
    
    # Cleanup
    camera_manager.stop_all()
    cv2.destroyAllWindows()
    
    # Print final summary
    logger.info("\n=== Final Summary ===")
    for camera_id, success in results.items():
        status = "SUCCESS" if success else "FAILED"
        logger.info(f"Camera {camera_id}: {status}")
    
    all_success = all(results.values())
    if all_success:
        logger.info("All calibrations successful!")
    else:
        logger.error("Some calibrations failed")
    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    main()
