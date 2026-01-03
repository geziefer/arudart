#!/usr/bin/env python3
import argparse
import time
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
from src.config import load_config
from src.camera.camera_manager import CameraManager
from src.processing.motion_detection import MotionDetector
from src.processing.background_model import BackgroundModel
from src.processing.dart_detection import DartDetector
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
    parser.add_argument('--manual-test', action='store_true', help='Enable manual testing mode (pause/place dart/detect)')
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
    
    # Initialize background model and dart detector
    background_model = BackgroundModel()
    dart_config = config['dart_detection']
    dart_detector = DartDetector(
        diff_threshold=dart_config['diff_threshold'],
        blur_kernel=dart_config['blur_kernel'],
        min_dart_area=dart_config['min_dart_area'],
        max_dart_area=dart_config['max_dart_area'],
        min_shaft_length=dart_config['min_shaft_length'],
        aspect_ratio_min=dart_config['aspect_ratio_min']
    )
    
    # FPS counters per camera
    camera_ids = camera_manager.get_camera_ids()
    fps_counters = {cam_id: FPSCounter() for cam_id in camera_ids}
    
    # Motion detection state
    motion_check_interval = motion_config['motion_check_interval']
    settled_time = motion_config.get('settled_time', 0.5)
    last_motion_check = 0
    last_motion_time = 0
    last_detection_time = 0  # Track last dart detection to prevent rapid re-detection
    detection_cooldown = 2.0  # Seconds to wait before detecting next dart
    background_initialized = False
    motion_state = "idle"  # idle, motion_detected, settled
    throw_count = 0
    last_logged_motion = 0  # Track last logged motion value to reduce spam
    paused = False  # Pause/play for manual dart placement testing
    
    # Create session folder for this run
    session_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # Find next session number
    throws_dir = Path("data/throws")
    throws_dir.mkdir(parents=True, exist_ok=True)
    existing_sessions = list(throws_dir.glob("Session_*"))
    session_number = len(existing_sessions) + 1
    
    session_dir = throws_dir / f"Session_{session_number:03d}_{session_timestamp}"
    session_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Session folder: {session_dir}")
    if args.manual_test:
        logger.info("=== MANUAL TESTING MODE: Press 'p' to pause/place dart, 'p' again to detect ===")
    
    try:
        logger.info("Starting motion detection...")
        if args.show_histogram:
            logger.info("Histogram display enabled - use to verify exposure settings")
        
        # Position windows diagonally in dev mode
        if args.dev_mode:
            # In manual test mode, only show camera 0
            cameras_to_show = [0] if args.manual_test else camera_ids
            for i, camera_id in enumerate(cameras_to_show):
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
                # Don't auto-initialize - wait for manual 'r' press
                # This ensures clean board without person in frame
                logger.info("=== Ready to initialize background - press 'r' when board is clear ===")
                background_initialized = "waiting"  # Flag to show message only once
            
            # Check motion at intervals (only when not paused)
            if not paused and background_initialized == True and current_time - last_motion_check >= motion_check_interval:
                last_motion_check = current_time
                
                # Use persistent change detection instead of transient motion
                persistent_change, per_camera_motion, max_motion = motion_detector.detect_persistent_change(
                    frames, current_time, persistence_time=0.3
                )
                
                # Slowly adapt background when idle AND no motion detected (compensates for lighting/camera drift)
                if motion_state == "idle" and not persistent_change and max_motion < 0.5:
                    for camera_id, frame in frames.items():
                        motion_detector.update_background(camera_id, frame, learning_rate=0.01)
                
                # Only log if motion changed significantly (>0.5%) or persistent change detected
                if abs(max_motion - last_logged_motion) > 0.5 or persistent_change:
                    logger.info(f"Motion: {max_motion:.2f}% (threshold={motion_config['settled_threshold']}, persistent={persistent_change})")
                    last_logged_motion = max_motion
                
                # Detect persistent change (dart stuck in board) OR manual trigger
                if (motion_state == "idle" and persistent_change) or motion_state == "dart_detected":
                    # Check cooldown to prevent rapid re-detection (skip for manual trigger)
                    if motion_state == "idle" and current_time - last_detection_time < detection_cooldown:
                        continue  # Skip this detection, too soon after last one
                    
                    if motion_state == "idle":  # Only log and update state if coming from idle
                        motion_state = "dart_detected"
                        last_detection_time = current_time
                        logger.info(f"=== DART THROW DETECTED ===")
                        logger.info(f"Max motion: {max_motion:.2f}%")
                        for cam_id, (detected, amount) in per_camera_motion.items():
                            if detected:
                                logger.info(f"  Camera {cam_id}: {amount:.2f}%")
                    
                    # Re-apply camera settings to prevent auto-adjustment drift
                    camera_manager.reapply_camera_settings()
                    
                    first_camera = camera_ids[0]
                    if background_model.has_pre_impact(first_camera) and first_camera in frames:
                        pre_frame = background_model.get_pre_impact(first_camera)
                        post_frame = frames[first_camera]
                        
                        tip_x, tip_y, confidence, debug_info = dart_detector.detect(pre_frame, post_frame)
                        
                        # Always save images (even if detection failed)
                        throw_count += 1
                        throw_timestamp = datetime.now().strftime("%H-%M-%S")
                        throw_dir = session_dir / f"Throw_{throw_count:03d}_{throw_timestamp}"
                        throw_dir.mkdir(parents=True, exist_ok=True)
                        
                        if tip_x is not None:
                            logger.info(f"Dart detected! Tip at ({tip_x}, {tip_y}), confidence: {confidence:.2f}")
                            
                            # Save annotated post frame with detection
                            annotated = post_frame.copy()
                            cv2.circle(annotated, (tip_x, tip_y), 10, (0, 0, 255), 2)
                            cv2.circle(annotated, (tip_x, tip_y), 3, (0, 255, 0), -1)
                            cv2.putText(annotated, f"Tip: ({tip_x},{tip_y})", (tip_x + 15, tip_y - 15),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                            cv2.putText(annotated, f"Conf: {confidence:.2f}", (tip_x + 15, tip_y),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                            
                            # Draw contour if available
                            if debug_info and 'contour' in debug_info:
                                cv2.drawContours(annotated, [debug_info['contour']], -1, (255, 0, 0), 2)
                            
                            cv2.imwrite(str(throw_dir / f"cam{first_camera}_annotated.jpg"), annotated)
                        else:
                            logger.warning("No dart detected in settled frame - saving images for analysis")
                            # Save post frame without annotation
                            cv2.imwrite(str(throw_dir / f"cam{first_camera}_annotated.jpg"), post_frame)
                        
                        # Always save pre/post and debug images
                        cv2.imwrite(str(throw_dir / f"cam{first_camera}_pre.jpg"), pre_frame)
                        cv2.imwrite(str(throw_dir / f"cam{first_camera}_post.jpg"), post_frame)
                        
                        # Save debug images
                        if debug_info:
                            if 'diff' in debug_info:
                                cv2.imwrite(str(throw_dir / f"cam{first_camera}_diff.jpg"), debug_info['diff'])
                            if 'thresh' in debug_info:
                                cv2.imwrite(str(throw_dir / f"cam{first_camera}_thresh.jpg"), debug_info['thresh'])
                        
                        logger.info(f"Saved images to {throw_dir}")
                    
                    # Update background to include this dart for next throw
                    # This way, next dart will only show the NEW dart, not previous ones
                    for camera_id, frame in frames.items():
                        motion_detector.update_background(camera_id, frame)
                        background_model.update_pre_impact(camera_id, frame)
                    
                    # Reset persistent change tracker to prevent repeated detections
                    for camera_id in camera_ids:
                        motion_detector.persistent_change_start[camera_id] = None
                    
                    motion_state = "idle"
            
            # Display frames in dev mode
            if args.dev_mode and frames:
                # In manual test mode, only show camera 0; otherwise show all cameras
                cameras_to_show = [camera_ids[0]] if args.manual_test else camera_ids
                
                for camera_id in cameras_to_show:
                    if camera_id not in frames:
                        continue
                    
                    frame = frames[camera_id]
                    display_frame = frame.copy()
                    fps = fps_counters[camera_id].get_fps()
                    
                    # Add FPS and motion state overlay
                    cv2.putText(display_frame, f"Camera {camera_id} - FPS: {fps:.1f}", (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    state_text = f"State: {motion_state}"
                    if args.manual_test and paused:
                        state_text += " [PAUSED]"
                    cv2.putText(display_frame, state_text, (10, 60), 
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
                
                # Check for keypresses (only call waitKey once)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    # Manual background reset - press 'r' after removing darts or at startup
                    # Can be used while paused to reset after removing dart
                    if paused:
                        logger.info("Resetting background while paused...")
                    else:
                        logger.info("Stabilizing camera for 2 seconds...")
                        time.sleep(2.0)
                    
                    # Capture single stable frame
                    stable_frames = {}
                    for camera_id in camera_ids:
                        frame = camera_manager.get_latest_frame(camera_id)
                        if frame is not None:
                            stable_frames[camera_id] = frame
                    
                    # Update background
                    for camera_id, frame in stable_frames.items():
                        motion_detector.update_background(camera_id, frame)
                        background_model.update_pre_impact(camera_id, frame)
                    
                    background_initialized = True
                    last_detection_time = 0  # Reset cooldown
                    logger.info("=== BACKGROUND CAPTURED - Ready to detect darts ===")
                elif key == ord('p'):
                    # Toggle pause for manual dart placement (only in manual test mode)
                    if not args.manual_test:
                        continue
                    
                    if not paused:
                        # Entering pause mode - capture current state as pre-impact
                        paused = True
                        for camera_id in camera_ids:
                            frame = camera_manager.get_latest_frame(camera_id)
                            if frame is not None:
                                background_model.update_pre_impact(camera_id, frame)
                        logger.info("=== PAUSED - Place dart manually, then press 'p' to detect ===")
                    else:
                        # Exiting pause mode - trigger detection
                        paused = False
                        logger.info("=== RESUMING - Triggering detection ===")
                        # Manually trigger detection
                        motion_state = "dart_detected"
                        last_detection_time = current_time
            else:
                time.sleep(0.01)
            
            # Log FPS every 60 seconds
            if current_time - start_time >= 60.0:
                logger.info("=== Status ===")
                for camera_id in camera_ids:
                    fps = fps_counters[camera_id].get_fps()
                    logger.info(f"Camera {camera_id}: {fps:.1f} FPS")
                logger.info(f"State: {motion_state}, Throws: {throw_count}")
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
