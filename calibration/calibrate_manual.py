#!/usr/bin/env python3
"""
Manual calibration script for ARU-DART coordinate mapping.

This script runs interactive manual calibration for each camera, allowing
the user to click on known control points to establish pixel-to-board
coordinate correspondences.

Usage:
    python calibration/calibrate_manual.py [--camera CAMERA_ID]

Options:
    --camera CAMERA_ID    Calibrate only specified camera (0, 1, or 2)
                         If not specified, calibrates all cameras sequentially
"""

import argparse
import logging
import sys
from pathlib import Path

import cv2
import tomli

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.calibration import BoardGeometry, HomographyCalculator, ManualCalibrator
from src.camera_manager import CameraManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.toml") -> dict:
    """Load configuration from TOML file."""
    with open(config_path, 'rb') as f:
        config = tomli.load(f)
    return config


def calibrate_camera(
    camera_id: int,
    camera_manager: CameraManager,
    board_geometry: BoardGeometry,
    homography_calculator: HomographyCalculator,
    output_dir: str = "calibration"
) -> bool:
    """
    Run manual calibration for a single camera.
    
    Args:
        camera_id: Camera identifier (0, 1, 2)
        camera_manager: CameraManager instance
        board_geometry: BoardGeometry instance
        homography_calculator: HomographyCalculator instance
        output_dir: Output directory for calibration files
    
    Returns:
        True if calibration successful, False otherwise
    """
    logger.info(f"=== Calibrating camera {camera_id} ===")
    
    # Capture frame
    logger.info("Capturing frame from camera...")
    frame = camera_manager.get_latest_frame(camera_id)
    
    if frame is None:
        logger.error(f"Failed to capture frame from camera {camera_id}")
        return False
    
    logger.info(f"Frame captured: {frame.shape}")
    
    # Run manual calibration
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
        logger.info(f"Timestamp: {metadata['timestamp']}")
        
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
    
    # Get calibration config (with defaults)
    calibration_config = config.get('calibration', {})
    homography_config = calibration_config.get('homography', {})
    homography_calculator = HomographyCalculator(homography_config)
    
    # Initialize camera manager
    logger.info("Initializing cameras...")
    camera_manager = CameraManager(config)
    
    # Determine which cameras to calibrate
    if args.camera is not None:
        camera_ids = [args.camera]
    else:
        camera_ids = [0, 1, 2]
    
    # Calibrate each camera
    results = {}
    for camera_id in camera_ids:
        success = calibrate_camera(
            camera_id,
            camera_manager,
            board_geometry,
            homography_calculator,
            args.output
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
    camera_manager.release_all()
    cv2.destroyAllWindows()
    
    # Print final summary
    logger.info("\n=== Final Summary ===")
    for camera_id, success in results.items():
        status = "SUCCESS" if success else "FAILED"
        logger.info(f"Camera {camera_id}: {status}")
    
    # Exit with appropriate code
    if all(results.values()):
        logger.info("All calibrations successful!")
        sys.exit(0)
    else:
        logger.error("Some calibrations failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
