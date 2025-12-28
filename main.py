#!/usr/bin/env python3
import argparse
import time
import cv2
import numpy as np
from src.config import load_config
from src.camera.camera_manager import CameraManager
from src.processing.motion_detection import MotionDetector
from src.util.logging_setup import setup_logging
from src.util.metrics import FPSCounter


def draw_histogram(frame):
    """Draw histogram overlay on frame with semi-transparent background."""
    # Calculate histogram for each channel
    hist_height = 80
    hist_width = 256
    # Create semi-transparent black background
    hist_img = np.zeros((hist_height, hist_width, 3), dtype=np.uint8)
    
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]  # BGR
    for i, color in enumerate(colors):
        hist = cv2.calcHist([frame], [i], None, [256], [0, 256])
        # Normalize to histogram height
        if hist.max() > 0:
            hist = hist / hist.max() * (hist_height - 5)
        
        # Draw with thicker lines and slight transparency
        for x in range(256):
            h = int(hist[x])
            if h > 0:
                # Draw line for this channel
                cv2.line(hist_img, (x, hist_height), (x, hist_height - h), color, 1)
    
    # Add grid lines for reference
    cv2.line(hist_img, (0, hist_height // 2), (hist_width, hist_height // 2), (64, 64, 64), 1)
    cv2.line(hist_img, (128, 0), (128, hist_height), (64, 64, 64), 1)
    
    return hist_img


def main():
    parser = argparse.ArgumentParser(description='ARU-DART Camera Capture')
    parser.add_argument('--config', default='config.toml', help='Path to config file')
    parser.add_argument('--dev-mode', action='store_true', help='Enable development mode with preview')
    parser.add_argument('--show-histogram', action='store_true', help='Show histogram overlay (dev mode only)')
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
    
    # Initialize motion detector
    motion_config = config['motion_detection']
    motion_detector = MotionDetector(
        downscale_factor=motion_config['downscale_factor'],
        motion_threshold=motion_config['motion_threshold'],
        blur_kernel=motion_config['blur_kernel'],
        settled_threshold=motion_config['settled_threshold']
    )
    
    # FPS counters per camera
    camera_ids = camera_manager.get_camera_ids()
    fps_counters = {cam_id: FPSCounter() for cam_id in camera_ids}
    
    # Motion detection state
    motion_check_interval = motion_config['motion_check_interval']
    last_motion_check = 0
    background_initialized = False
    motion_state = "idle"  # idle, motion_detected, settled
    
    try:
        logger.info("Starting motion detection...")
        if args.show_histogram:
            logger.info("Histogram display enabled - use to verify exposure settings")
        
        # Position windows diagonally in dev mode
        if args.dev_mode:
            for i, camera_id in enumerate(camera_ids):
                cv2.namedWindow(f"Camera {camera_id}", cv2.WINDOW_NORMAL)
                cv2.resizeWindow(f"Camera {camera_id}", 640, 480)
                cv2.moveWindow(f"Camera {camera_id}", i * 200, i * 150)
        
        start_time = time.time()
        
        while True:
            current_time = time.time()
            
            # Get frames from all cameras
            frames = {}
            for camera_id in camera_ids:
                frame = camera_manager.get_latest_frame(camera_id)
                if frame is not None:
                    frames[camera_id] = frame
                    fps_counters[camera_id].tick()
            
            # Initialize background on first frames
            if not background_initialized and len(frames) == len(camera_ids):
                for camera_id, frame in frames.items():
                    motion_detector.update_background(camera_id, frame)
                background_initialized = True
                logger.info("Background initialized for all cameras")
            
            # Check motion at intervals
            if background_initialized and current_time - last_motion_check >= motion_check_interval:
                last_motion_check = current_time
                
                any_motion, per_camera_motion, max_motion = motion_detector.detect_combined_motion(frames)
                
                # State transitions
                if motion_state == "idle" and any_motion:
                    motion_state = "motion_detected"
                    logger.info(f"Motion detected! Max motion: {max_motion:.1f}%")
                    for cam_id, (detected, amount) in per_camera_motion.items():
                        if detected:
                            logger.info(f"  Camera {cam_id}: {amount:.1f}%")
                
                elif motion_state == "motion_detected" and not any_motion:
                    motion_state = "settled"
                    logger.info("Board settled")
                    # Update background for next throw
                    for camera_id, frame in frames.items():
                        motion_detector.update_background(camera_id, frame)
                    motion_state = "idle"
            
            # Display frames in dev mode
            if args.dev_mode and frames:
                for camera_id, frame in frames.items():
                    display_frame = frame.copy()
                    fps = fps_counters[camera_id].get_fps()
                    
                    # Add FPS and motion state overlay
                    cv2.putText(display_frame, f"Camera {camera_id} - FPS: {fps:.1f}", (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(display_frame, f"State: {motion_state}", (10, 60), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    # Add exposure info
                    mean_brightness = np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
                    cv2.putText(display_frame, f"Brightness: {mean_brightness:.1f}", (10, 90), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                    
                    # Overlay histogram if requested
                    if args.show_histogram:
                        hist_img = draw_histogram(frame)
                        # Resize histogram to fit in corner
                        hist_resized = cv2.resize(hist_img, (256, 80))
                        # Place in bottom-left corner
                        y_offset = display_frame.shape[0] - 80
                        display_frame[y_offset:y_offset+80, 0:256] = hist_resized
                    
                    cv2.imshow(f"Camera {camera_id}", display_frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                time.sleep(0.01)
            
            # Log FPS every 5 seconds
            if current_time - start_time >= 5.0:
                logger.info("=== FPS Report ===")
                for camera_id in camera_ids:
                    fps = fps_counters[camera_id].get_fps()
                    logger.info(f"Camera {camera_id}: {fps:.2f} FPS")
                start_time = current_time
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        camera_manager.stop_all()
        if args.dev_mode:
            cv2.destroyAllWindows()
        logger.info("Shutdown complete")


if __name__ == '__main__':
    main()
