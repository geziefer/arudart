#!/usr/bin/env python3
import argparse
import time
import cv2
from src.config import load_config
from src.camera.camera_manager import CameraManager
from src.util.logging_setup import setup_logging
from src.util.metrics import FPSCounter


def main():
    parser = argparse.ArgumentParser(description='ARU-DART Camera Capture')
    parser.add_argument('--config', default='config.toml', help='Path to config file')
    parser.add_argument('--dev-mode', action='store_true', help='Enable development mode with preview')
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging()
    logger.info("Starting ARU-DART camera capture")
    
    # Load config
    config = load_config(args.config)
    logger.info(f"Loaded config from {args.config}")
    
    # Initialize camera manager
    camera_manager = CameraManager(config)
    
    # Check if any cameras are available
    if not camera_manager.get_camera_ids():
        logger.error("No cameras available - exiting")
        return
    
    camera_manager.start_all()
    
    # FPS counters per camera
    camera_ids = camera_manager.get_camera_ids()
    fps_counters = {cam_id: FPSCounter() for cam_id in camera_ids}
    
    try:
        logger.info("Starting FPS measurement (10 seconds)...")
        start_time = time.time()
        
        while time.time() - start_time < 10.0:
            for camera_id in camera_ids:
                frame = camera_manager.get_latest_frame(camera_id)
                
                if frame is not None:
                    fps_counters[camera_id].tick()
                    
                    if args.dev_mode:
                        # Show preview with FPS overlay
                        fps = fps_counters[camera_id].get_fps()
                        cv2.putText(frame, f"Camera {camera_id} - FPS: {fps:.1f}", (10, 30), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        cv2.imshow(f"Camera {camera_id}", frame)
            
            if args.dev_mode:
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                time.sleep(0.01)
        
        # Final FPS report
        logger.info("=== Final FPS Report ===")
        for camera_id in camera_ids:
            final_fps = fps_counters[camera_id].get_fps()
            logger.info(f"Camera {camera_id}: {final_fps:.2f} FPS")
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        camera_manager.stop_all()
        if args.dev_mode:
            cv2.destroyAllWindows()
        logger.info("Shutdown complete")


if __name__ == '__main__':
    main()
