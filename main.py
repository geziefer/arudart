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
from src.calibration.coordinate_mapper import CoordinateMapper
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


def draw_calibration_overlay(frame, camera_id, coordinate_mapper):
    """Draw board coordinate grid overlay on camera frame."""
    if not coordinate_mapper.is_calibrated(camera_id):
        return frame
    
    display = frame.copy()
    h, w = display.shape[:2]
    
    # Draw concentric circles at key radii (board rings)
    radii_mm = [
        (6.35, (0, 0, 255), "DB"),      # Double bull
        (15.9, (0, 128, 255), "SB"),    # Single bull
        (99.0, (0, 255, 255), "T-in"),  # Triple inner
        (107.0, (0, 255, 255), "T-out"),# Triple outer
        (162.0, (255, 255, 0), "D-in"), # Double inner
        (170.0, (255, 255, 0), "D-out"),# Double outer
    ]
    
    for radius_mm, color, label in radii_mm:
        # Sample points around circle
        points = []
        for angle in np.linspace(0, 2*np.pi, 72):
            x = radius_mm * np.cos(angle)
            y = radius_mm * np.sin(angle)
            
            pixel = coordinate_mapper.map_to_image(camera_id, x, y)
            if pixel is not None:
                u, v = pixel
                if 0 <= u < w and 0 <= v < h:
                    points.append((int(u), int(v)))
        
        # Draw circle segments
        if len(points) > 2:
            for i in range(len(points) - 1):
                cv2.line(display, points[i], points[i+1], color, 1)
            cv2.line(display, points[-1], points[0], color, 1)
    
    # Draw coordinate axes
    # X axis (red) - horizontal through center
    x_points = []
    for x in np.linspace(-180, 180, 20):
        pixel = coordinate_mapper.map_to_image(camera_id, x, 0)
        if pixel is not None:
            u, v = pixel
            if 0 <= u < w and 0 <= v < h:
                x_points.append((int(u), int(v)))
    
    if len(x_points) > 1:
        for i in range(len(x_points) - 1):
            cv2.line(display, x_points[i], x_points[i+1], (0, 0, 255), 2)
    
    # Y axis (green) - vertical through center
    y_points = []
    for y in np.linspace(-180, 180, 20):
        pixel = coordinate_mapper.map_to_image(camera_id, 0, y)
        if pixel is not None:
            u, v = pixel
            if 0 <= u < w and 0 <= v < h:
                y_points.append((int(u), int(v)))
    
    if len(y_points) > 1:
        for i in range(len(y_points) - 1):
            cv2.line(display, y_points[i], y_points[i+1], (0, 255, 0), 2)
    
    # Draw origin marker
    origin = coordinate_mapper.map_to_image(camera_id, 0, 0)
    if origin is not None:
        u, v = int(origin[0]), int(origin[1])
        if 0 <= u < w and 0 <= v < h:
            cv2.drawMarker(display, (u, v), (255, 255, 255), cv2.MARKER_CROSS, 20, 2)
            cv2.putText(display, "Origin", (u + 10, v - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    # Add legend
    cv2.putText(display, "Calibration Overlay (press 'v' to toggle)", (10, h - 10),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    return display


def main():
    parser = argparse.ArgumentParser(description='ARU-DART Camera Capture')
    parser.add_argument('--config', default='config.toml', help='Path to config file')
    parser.add_argument('--dev-mode', action='store_true', help='Enable development mode with preview')
    parser.add_argument('--show-histogram', action='store_true', help='Show histogram overlay (dev mode only)')
    parser.add_argument('--manual-test', action='store_true', help='Enable manual testing mode (pause/place dart/detect)')
    parser.add_argument('--record-mode', action='store_true', help='Enable recording mode (capture images for regression tests)')
    parser.add_argument('--single-camera', type=int, choices=[0, 1, 2], help='Test single camera only (0, 1, or 2)')
    parser.add_argument('--calibrate', action='store_true', help='Run extrinsic calibration at startup')
    parser.add_argument('--verify-calibration', action='store_true', help='Run calibration verification script')
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
    
    # Filter to single camera if requested
    all_camera_ids = camera_manager.get_camera_ids()
    if args.single_camera is not None:
        # Map logical camera index (0,1,2) to physical device ID
        if args.single_camera < len(all_camera_ids):
            camera_ids = [sorted(all_camera_ids)[args.single_camera]]
            logger.info(f"Single-camera mode: Using camera {args.single_camera} (device {camera_ids[0]})")
        else:
            logger.error(f"Camera {args.single_camera} not available (only {len(all_camera_ids)} cameras detected)")
            return
    else:
        camera_ids = all_camera_ids
        logger.info(f"Multi-camera mode: Using all {len(camera_ids)} cameras")
    
    camera_manager.start_all()
    
    # Initialize coordinate mapper for pixel-to-board transformation
    calibration_dir = config.get('calibration', {}).get('calibration_dir', 'calibration')
    coordinate_mapper = CoordinateMapper(config, calibration_dir)
    
    # Log calibration status
    calibration_status = coordinate_mapper.get_calibration_status()
    calibrated_cameras = [cid for cid, status in calibration_status.items() if status['is_calibrated']]
    if calibrated_cameras:
        logger.info(f"Coordinate mapping enabled for cameras: {calibrated_cameras}")
    else:
        logger.warning("No cameras calibrated - coordinate mapping disabled")
        logger.warning("Run calibration scripts to enable board coordinate output")
    
    # Handle calibration flags
    if args.calibrate:
        logger.info("Running extrinsic calibration...")
        import subprocess
        result = subprocess.run(
            ['python', 'calibration/calibrate_extrinsic.py', '--visualize'],
            cwd=str(Path(__file__).parent)
        )
        if result.returncode == 0:
            logger.info("Calibration complete - reloading calibration data")
            coordinate_mapper.reload_calibration()
        else:
            logger.warning("Calibration failed or was cancelled")
    
    if args.verify_calibration:
        logger.info("Running calibration verification...")
        import subprocess
        subprocess.run(
            ['python', 'calibration/verify_calibration.py'],
            cwd=str(Path(__file__).parent)
        )
        return  # Exit after verification
    
    # Initialize motion detector
    motion_config = config['motion_detection']
    motion_detector = MotionDetector(
        downscale_factor=motion_config['downscale_factor'],
        motion_threshold=motion_config['motion_threshold'],
        blur_kernel=motion_config['blur_kernel'],
        settled_threshold=motion_config['settled_threshold']
    )
    
    # Initialize background model and per-camera dart detectors
    background_model = BackgroundModel()
    dart_config = config['dart_detection']
    
    # Create separate detector instance for each camera (each maintains its own previous_darts_mask)
    dart_detectors = {}
    for cam_id in camera_ids:
        dart_detectors[cam_id] = DartDetector(
            diff_threshold=dart_config['diff_threshold'],
            blur_kernel=dart_config['blur_kernel'],
            min_dart_area=dart_config['min_dart_area'],
            max_dart_area=dart_config['max_dart_area'],
            min_shaft_length=dart_config['min_shaft_length'],
            aspect_ratio_min=dart_config['aspect_ratio_min']
        )
    
    # FPS counters per camera (use filtered camera_ids from above)
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
    reset_message_time = 0  # Track when reset message was shown
    reset_message_duration = 2.0  # Show reset message for 2 seconds
    recording_state = "waiting_for_pre"  # State: waiting_for_pre, waiting_for_post, entering_description
    pre_frames = {}  # Store pre-frames for current recording
    post_frames = {}  # Store post-frames for current recording
    recording_description = ""  # Current description being typed
    show_calibration_overlay = False  # Toggle for calibration visualization
    
    # Create recordings folder if in record mode
    if args.record_mode:
        recordings_dir = Path("data/recordings")
        recordings_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Recording mode enabled - save format: <description>_camX_pre|post.jpg")
    
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
    if args.record_mode:
        logger.info("=== RECORDING MODE ===")
        logger.info("Press '1' for single dart recording")
        logger.info("Press '3' for 3-dart sequence recording")
    
    try:
        logger.info("Starting motion detection...")
        if args.show_histogram:
            logger.info("Histogram display enabled - use to verify exposure settings")
        
        # Position windows in a tiled layout in dev mode
        if args.dev_mode:
            # Show all cameras in overlapping layout (cascaded)
            for i, camera_id in enumerate(camera_ids):
                cv2.namedWindow(f"Camera {camera_id}", cv2.WINDOW_NORMAL)
                cv2.resizeWindow(f"Camera {camera_id}", 640, 480)
                # Cascade windows with offset
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
            
            # Initialize background on first frames (skip in record mode)
            if not args.record_mode and not background_initialized and len(frames) == len(camera_ids):
                # Auto-initialize background after 2 seconds (allow cameras to stabilize)
                if current_time - start_time > 2.0:
                    logger.info("Auto-initializing background...")
                    for camera_id, frame in frames.items():
                        motion_detector.update_background(camera_id, frame)
                        background_model.update_pre_impact(camera_id, frame)
                    background_initialized = True
                    reset_message_time = current_time
                    logger.info("=== BACKGROUND CAPTURED - Ready to detect darts ===")
            
            # Check motion at intervals (only when not paused and not in record mode)
            if not paused and not args.record_mode and background_initialized == True and current_time - last_motion_check >= motion_check_interval:
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
                    
                    # Capture multiple post-impact frames for noise reduction
                    if motion_state == "idle":  # First detection after idle
                        motion_state = "dart_detected"
                        last_detection_time = current_time
                        logger.info(f"=== DART THROW DETECTED ===")
                        logger.info(f"Max motion: {max_motion:.2f}%")
                        for cam_id, (detected, amount) in per_camera_motion.items():
                            if detected:
                                logger.info(f"  Camera {cam_id}: {amount:.2f}%")
                    
                    # Always capture post frames (for both automatic and manual test mode)
                    logger.info("Capturing multiple post-impact frames...")
                    num_post_frames = 3
                    post_frame_interval = 0.1  # 100ms between frames
                    
                    for i in range(num_post_frames):
                        if i > 0:
                            time.sleep(post_frame_interval)
                        # Get current frames
                        for camera_id in camera_ids:
                            frame = camera_manager.get_latest_frame(camera_id)
                            if frame is not None:
                                background_model.add_post_impact_candidate(camera_id, frame)
                    
                    # Run detection on all cameras
                    throw_count += 1
                    throw_timestamp = datetime.now().strftime("%H-%M-%S")
                    throw_dir = session_dir / f"Throw_{throw_count:03d}_{throw_timestamp}"
                    throw_dir.mkdir(parents=True, exist_ok=True)
                    
                    detections = {}
                    for camera_id in camera_ids:
                        if background_model.has_pre_impact(camera_id):
                            pre_frame = background_model.get_pre_impact(camera_id)
                            post_frame = background_model.get_best_post_impact(camera_id)
                            
                            if post_frame is None:
                                logger.warning(f"No post frame available for camera {camera_id}")
                                continue
                            
                            tip_x, tip_y, confidence, debug_info = dart_detectors[camera_id].detect(pre_frame, post_frame, mask_previous=False)
                            
                            detections[camera_id] = {
                                'tip_x': tip_x,
                                'tip_y': tip_y,
                                'confidence': confidence,
                                'debug_info': debug_info,
                                'board_x': None,
                                'board_y': None,
                            }
                            
                            # Transform to board coordinates if calibrated
                            if tip_x is not None and coordinate_mapper.is_calibrated(camera_id):
                                board_coords = coordinate_mapper.map_to_board(camera_id, tip_x, tip_y)
                                if board_coords is not None:
                                    detections[camera_id]['board_x'] = board_coords[0]
                                    detections[camera_id]['board_y'] = board_coords[1]
                            
                            # Save annotated image
                            if tip_x is not None:
                                annotated = post_frame.copy()
                                cv2.circle(annotated, (tip_x, tip_y), 10, (0, 0, 255), 2)
                                cv2.circle(annotated, (tip_x, tip_y), 3, (0, 255, 0), -1)
                                cv2.putText(annotated, f"Tip: ({tip_x},{tip_y})", (tip_x + 15, tip_y - 15),
                                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                                cv2.putText(annotated, f"Conf: {confidence:.2f}", (tip_x + 15, tip_y),
                                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                                if debug_info and 'contour' in debug_info:
                                    cv2.drawContours(annotated, [debug_info['contour']], -1, (255, 0, 0), 2)
                                cv2.imwrite(str(throw_dir / f"cam{camera_id}_annotated.jpg"), annotated)
                            else:
                                cv2.imwrite(str(throw_dir / f"cam{camera_id}_annotated.jpg"), post_frame)
                            
                            # Save pre/post and debug images
                            cv2.imwrite(str(throw_dir / f"cam{camera_id}_pre.jpg"), pre_frame)
                            cv2.imwrite(str(throw_dir / f"cam{camera_id}_post.jpg"), post_frame)
                            if debug_info:
                                if 'diff' in debug_info:
                                    cv2.imwrite(str(throw_dir / f"cam{camera_id}_diff.jpg"), debug_info['diff'])
                                if 'thresh' in debug_info:
                                    cv2.imwrite(str(throw_dir / f"cam{camera_id}_thresh.jpg"), debug_info['thresh'])
                    
                    # Log per-camera results
                    detected_cameras = [cam_id for cam_id, det in detections.items() if det['tip_x'] is not None]
                    if detected_cameras:
                        logger.info(f"Dart detected in {len(detected_cameras)}/{len(camera_ids)} cameras:")
                        for cam_id in detected_cameras:
                            det = detections[cam_id]
                            if det['board_x'] is not None:
                                logger.info(f"  Camera {cam_id}: Pixel ({det['tip_x']}, {det['tip_y']}), "
                                           f"Board ({det['board_x']:.1f}, {det['board_y']:.1f}) mm, "
                                           f"confidence: {det['confidence']:.2f}")
                            else:
                                logger.info(f"  Camera {cam_id}: Pixel ({det['tip_x']}, {det['tip_y']}), "
                                           f"Board (not calibrated), confidence: {det['confidence']:.2f}")
                    else:
                        logger.warning("No dart detected in any camera - saving images for analysis")
                    
                    logger.info(f"Saved images to {throw_dir}")
                    
                    # Update background to include this dart for next throw
                    # Use post-impact frame (with dart) as new pre-impact for next detection
                    for camera_id in camera_ids:
                        post_frame = background_model.get_best_post_impact(camera_id)
                        if post_frame is not None:
                            motion_detector.update_background(camera_id, post_frame)
                            background_model.update_pre_impact(camera_id, post_frame)
                    logger.info("Background updated to include detected dart")
                    
                    # Reset persistent change tracker to prevent repeated detections
                    for camera_id in camera_ids:
                        motion_detector.persistent_change_start[camera_id] = None
                    
                    motion_state = "idle"
            
            # Display frames in dev mode
            if args.dev_mode and frames:
                # Show all cameras in tiled layout
                for camera_id in camera_ids:
                    if camera_id not in frames:
                        continue
                    
                    frame = frames[camera_id]
                    display_frame = frame.copy()
                    fps = fps_counters[camera_id].get_fps()
                    
                    # Add FPS overlay
                    cv2.putText(display_frame, f"Camera {camera_id} - FPS: {fps:.1f}", (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    # Add state text with pause/reset indicators
                    state_text = f"State: {motion_state}"
                    if args.manual_test:
                        if paused:
                            state_text += " [PAUSED]"
                        if current_time - reset_message_time < reset_message_duration:
                            state_text += " [BACKGROUND RESET]"
                    if args.record_mode:
                        if recording_state == "waiting_for_pre":
                            state_text += f" [REC - Press 'r' for PRE]"
                        elif recording_state == "waiting_for_post":
                            state_text += f" [REC - Press 'c' for POST]"
                        elif recording_state == "entering_description":
                            state_text += f" [REC - ENTER NAME]"
                    cv2.putText(display_frame, state_text, (10, 60), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    # Show input overlay when entering description
                    if args.record_mode and recording_state == "entering_description":
                        # Create semi-transparent overlay at bottom
                        overlay = display_frame.copy()
                        overlay_height = 120
                        y_start = display_frame.shape[0] - overlay_height
                        cv2.rectangle(overlay, (0, y_start), (display_frame.shape[1], display_frame.shape[0]), 
                                     (0, 0, 0), -1)
                        cv2.addWeighted(overlay, 0.7, display_frame, 0.3, 0, display_frame)
                        
                        # Add instruction text
                        instruction = "Enter description (e.g., 'T20', 'bull', 'two_darts'):"
                        cv2.putText(display_frame, instruction, (20, y_start + 30), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                        
                        # Add current input text with cursor
                        input_text = recording_description + "_"
                        cv2.putText(display_frame, input_text, (20, y_start + 70), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        
                        # Add hint text
                        hint = "Press ENTER to save, ESC to cancel"
                        cv2.putText(display_frame, hint, (20, y_start + 105), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                    
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
                    
                    # Draw calibration overlay if enabled
                    if show_calibration_overlay:
                        display_frame = draw_calibration_overlay(display_frame, camera_id, coordinate_mapper)
                    
                    cv2.imshow(f"Camera {camera_id}", display_frame)
                
                # Check for keypresses (only call waitKey once)
                key = cv2.waitKey(1) & 0xFF
                
                # Handle text input when entering description
                if args.record_mode and recording_state == "entering_description":
                    if key == 13:  # Enter key
                        # Save recording with description
                        if not recording_description:
                            recording_description = "unnamed"
                        
                        # Save all frames with new naming: description_camX_pre|post.jpg
                        recordings_dir = Path("data/recordings")
                        for camera_id in camera_ids:
                            pre_path = recordings_dir / f"{recording_description}_cam{camera_id}_pre.jpg"
                            post_path = recordings_dir / f"{recording_description}_cam{camera_id}_post.jpg"
                            cv2.imwrite(str(pre_path), pre_frames[camera_id])
                            cv2.imwrite(str(post_path), post_frames[camera_id])
                        
                        logger.info(f"=== SAVED recording: {recording_description} ===")
                        logger.info(f"=== Ready for next recording - Press 'r' for PRE ===")
                        
                        # Reset for next recording (no auto-increment needed with name-based scheme)
                        recording_state = "waiting_for_pre"
                        pre_frames = {}
                        post_frames = {}
                        recording_description = ""
                        continue
                    elif key == 27:  # ESC key
                        # Cancel recording
                        logger.info("=== Recording cancelled ===")
                        recording_state = "waiting_for_pre"
                        pre_frames = {}
                        post_frames = {}
                        recording_description = ""
                        continue
                    elif key == 8 or key == 127:  # Backspace or Delete
                        if recording_description:
                            recording_description = recording_description[:-1]
                        continue
                    elif key != 255 and 32 <= key <= 126:  # Printable ASCII characters
                        recording_description += chr(key)
                        continue
                
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    # In record mode: capture PRE frame
                    # In normal/manual-test mode: reset background
                    if args.record_mode and recording_state == "waiting_for_pre":
                        # Capture PRE frame (clean board)
                        logger.info("=== CAPTURING PRE-FRAME ===")
                        
                        # Capture current frames from all cameras
                        pre_frames = {}
                        for camera_id in camera_ids:
                            frame = camera_manager.get_latest_frame(camera_id)
                            if frame is not None:
                                pre_frames[camera_id] = frame.copy()
                        
                        logger.info(f"=== PRE-FRAME CAPTURED - Now place dart and press 'c' for POST ===")
                        recording_state = "waiting_for_post"
                    else:
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
                        
                        # Reset previous darts mask for all cameras when capturing new background
                        for dart_detector in dart_detectors.values():
                            dart_detector.reset_previous_darts()
                        
                        background_initialized = True
                        last_detection_time = 0  # Reset cooldown
                        reset_message_time = current_time  # Show reset message
                        logger.info("=== BACKGROUND CAPTURED - Ready to detect darts ===")
                elif key == ord('c'):
                    # Capture POST frame in record mode
                    if not args.record_mode:
                        continue
                    
                    if recording_state != "waiting_for_post":
                        logger.info("Please capture PRE frame first: Press 'r'")
                        continue
                    
                    # Capture POST frame (with dart)
                    logger.info("=== CAPTURING POST-FRAME ===")
                    
                    # Capture current frames from all cameras
                    post_frames = {}
                    for camera_id in camera_ids:
                        frame = camera_manager.get_latest_frame(camera_id)
                        if frame is not None:
                            post_frames[camera_id] = frame.copy()
                    
                    # Switch to description entry mode
                    recording_state = "entering_description"
                    recording_description = ""
                    logger.info("=== Enter description in camera window ===")
                    continue
                
                elif key == ord('p'):
                    # Toggle pause for manual dart placement (manual test mode only)
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
                
                elif key == ord('x'):
                    # Trigger extrinsic calibration (dev mode only)
                    if not args.dev_mode:
                        continue
                    
                    logger.info("=== RUNNING EXTRINSIC CALIBRATION ===")
                    import subprocess
                    
                    # Close camera windows temporarily
                    for cam_id in camera_ids:
                        cv2.destroyWindow(f"Camera {cam_id}")
                    
                    # Run calibration
                    result = subprocess.run(
                        ['python', 'calibration/calibrate_extrinsic.py', '--visualize'],
                        cwd=str(Path(__file__).parent)
                    )
                    
                    if result.returncode == 0:
                        logger.info("Calibration complete - reloading calibration data")
                        coordinate_mapper.reload_calibration()
                        
                        # Log new calibration status
                        calibration_status = coordinate_mapper.get_calibration_status()
                        calibrated_cameras = [cid for cid, status in calibration_status.items() if status['is_calibrated']]
                        logger.info(f"Coordinate mapping now enabled for cameras: {calibrated_cameras}")
                    else:
                        logger.warning("Calibration failed or was cancelled")
                    
                    # Recreate camera windows
                    for i, cam_id in enumerate(camera_ids):
                        cv2.namedWindow(f"Camera {cam_id}", cv2.WINDOW_NORMAL)
                        cv2.resizeWindow(f"Camera {cam_id}", 640, 480)
                        cv2.moveWindow(f"Camera {cam_id}", i * 200, i * 150)
                
                elif key == ord('v'):
                    # Toggle calibration visualization overlay (dev mode only)
                    if args.dev_mode:
                        show_calibration_overlay = not show_calibration_overlay
                        if show_calibration_overlay:
                            logger.info("Calibration overlay ENABLED")
                        else:
                            logger.info("Calibration overlay DISABLED")
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
