#!/usr/bin/env python3
import argparse
import time
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
import json
from src.config import load_config
from src.camera.camera_manager import CameraManager
from src.processing.motion_detection import MotionDetector
from src.processing.background_model import BackgroundModel
from src.processing.dart_detection import DartDetector
from src.calibration import CoordinateMapper, CalibrationManager, BoardGeometry
from src.fusion import ScoreCalculator
from src.diagnostics import DiagnosticLogger, AccuracyTestRunner
from src.diagnostics.known_positions import build_known_positions
from src.feedback.feedback_collector import FeedbackCollector, score_to_display_string, score_to_parsed_score
from src.feedback.feedback_storage import FeedbackStorage
from src.feedback.score_parser import ScoreParser
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


def run_single_dart_test(camera_ids, camera_manager, motion_detector, background_model,
                         dart_detectors, coordinate_mapper, calibration_manager,
                         score_calculator, session_dir, config, logger, diagnostic_logger=None,
                         feedback_collector=None, feedback_storage=None):
    """Timed single-dart test loop.

    Cycle:
      1. Capture background, show "READY - throw dart" with 3s countdown
      2. Wait for motion detection, run detection + fusion
      3. Display result for 5s countdown, then repeat
    Press 'q' or ESC to quit.
    """
    motion_config = config['motion_detection']
    throw_count = 0
    fps_counters = {cam_id: FPSCounter() for cam_id in camera_ids}

    # States: "stabilize", "countdown_throw", "waiting", "detected", "feedback", "countdown_result"
    state = "stabilize"
    state_start = time.time()
    last_score_text = ""
    last_detail_text = ""
    last_cameras_text = ""
    last_event = None
    last_image_paths = {}

    # Create windows
    for i, camera_id in enumerate(camera_ids):
        cv2.namedWindow(f"Camera {camera_id}", cv2.WINDOW_NORMAL)
        cv2.resizeWindow(f"Camera {camera_id}", 640, 480)
        cv2.moveWindow(f"Camera {camera_id}", i * 200, i * 150)

    logger.info("=== SINGLE DART TEST MODE ===")
    logger.info("Stabilizing cameras...")

    while True:
        current_time = time.time()
        elapsed = current_time - state_start

        # Get frames
        frames = {}
        for camera_id in camera_ids:
            frame = camera_manager.get_latest_frame(camera_id)
            if frame is not None:
                frames[camera_id] = frame
                fps_counters[camera_id].tick()

        if not frames:
            time.sleep(0.01)
            continue

        # --- State machine ---
        if state == "stabilize":
            # Wait 2s for cameras to settle, then capture background
            if elapsed >= 2.0:
                for camera_id, frame in frames.items():
                    motion_detector.update_background(camera_id, frame)
                    background_model.update_pre_impact(camera_id, frame)
                for det in dart_detectors.values():
                    det.reset_previous_darts()
                # Reset persistent change tracker
                for camera_id in camera_ids:
                    motion_detector.persistent_change_start[camera_id] = None
                logger.info("Background captured - starting throw countdown")
                state = "countdown_throw"
                state_start = current_time

        elif state == "countdown_throw":
            # 3s countdown, then start listening for motion
            if elapsed >= 3.0:
                state = "waiting"
                state_start = current_time
                logger.info("Waiting for dart throw...")

        elif state == "waiting":
            # Check for persistent change (dart landed)
            persistent_change, per_camera_motion, max_motion = motion_detector.detect_persistent_change(
                frames, current_time, persistence_time=0.3
            )
            if persistent_change:
                state = "detected"
                state_start = current_time
                logger.info(f"=== DART THROW DETECTED (motion {max_motion:.2f}%) ===")

        elif state == "detected":
            # Capture post frames and run detection
            time.sleep(0.3)  # Brief settle
            for camera_id in camera_ids:
                frame = camera_manager.get_latest_frame(camera_id)
                if frame is not None:
                    background_model.add_post_impact_candidate(camera_id, frame)

            throw_count += 1
            throw_timestamp = datetime.now().strftime("%H-%M-%S")
            throw_dir = session_dir / f"Throw_{throw_count:03d}_{throw_timestamp}"
            throw_dir.mkdir(parents=True, exist_ok=True)

            detections = {}
            for camera_id in camera_ids:
                if not background_model.has_pre_impact(camera_id):
                    continue
                pre_frame = background_model.get_pre_impact(camera_id)
                post_frame = background_model.get_best_post_impact(camera_id)
                if post_frame is None:
                    continue

                tip_x, tip_y, confidence, debug_info = dart_detectors[camera_id].detect(
                    pre_frame, post_frame, mask_previous=False
                )
                detections[camera_id] = {
                    'tip_x': tip_x, 'tip_y': tip_y,
                    'confidence': confidence, 'debug_info': debug_info,
                }

                board_x, board_y = None, None
                if tip_x is not None and coordinate_mapper.is_calibrated(camera_id):
                    board_result = coordinate_mapper.map_to_board(camera_id, float(tip_x), float(tip_y))
                    if board_result is not None:
                        board_x, board_y = board_result
                detections[camera_id]['board_x'] = board_x
                detections[camera_id]['board_y'] = board_y

                # Save images
                if tip_x is not None:
                    annotated = post_frame.copy()
                    cv2.circle(annotated, (tip_x, tip_y), 10, (0, 0, 255), 2)
                    cv2.circle(annotated, (tip_x, tip_y), 3, (0, 255, 0), -1)
                    cv2.putText(annotated, f"({tip_x},{tip_y})", (tip_x + 15, tip_y - 15),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    if debug_info and 'contour' in debug_info:
                        cv2.drawContours(annotated, [debug_info['contour']], -1, (255, 0, 0), 2)
                    cv2.imwrite(str(throw_dir / f"cam{camera_id}_annotated.jpg"), annotated)
                else:
                    cv2.imwrite(str(throw_dir / f"cam{camera_id}_annotated.jpg"), post_frame)
                cv2.imwrite(str(throw_dir / f"cam{camera_id}_pre.jpg"), pre_frame)
                cv2.imwrite(str(throw_dir / f"cam{camera_id}_post.jpg"), post_frame)

            # Fusion + scoring
            detected_cameras = [cid for cid, d in detections.items() if d['tip_x'] is not None]
            last_score_text = "No detection"
            last_detail_text = ""
            last_cameras_text = f"Detected: {len(detected_cameras)}/{len(camera_ids)} cams"

            if detected_cameras:
                fusion_detections = []
                image_paths = {}
                for cam_id in detected_cameras:
                    det = detections[cam_id]
                    if det.get('board_x') is not None:
                        fusion_detections.append({
                            'camera_id': cam_id,
                            'pixel': (det['tip_x'], det['tip_y']),
                            'board': (det['board_x'], det['board_y']),
                            'confidence': det['confidence'],
                        })
                        image_paths[str(cam_id)] = str(throw_dir / f"cam{cam_id}_annotated.jpg")

                if fusion_detections:
                    event = score_calculator.process_detections(fusion_detections, image_paths=image_paths)
                    if event is not None:
                        s = event.score
                        if s.ring == "bull":
                            last_score_text = "BULL (50)"
                        elif s.ring == "single_bull":
                            last_score_text = "Single Bull (25)"
                        elif s.ring == "out_of_bounds":
                            last_score_text = "MISS (0)"
                        else:
                            ring_prefix = {"triple": "T", "double": "D", "single": "S"}.get(s.ring, "")
                            last_score_text = f"{ring_prefix}{s.sector} = {s.total}"
                        last_detail_text = f"r={event.radius:.1f}mm  angle={event.angle_deg:.0f}deg  conf={event.fusion_confidence:.2f}"
                        last_cameras_text = f"Cameras: {event.cameras_used} ({event.num_cameras} used)"
                        logger.info(f"Throw {throw_count}: {last_score_text} | {last_detail_text}")

                        event_path = throw_dir / f"event_{throw_timestamp}.json"
                        with open(event_path, 'w') as f:
                            json.dump(event.to_dict(), f, indent=2)

                        # Log to diagnostics if enabled
                        if diagnostic_logger is not None:
                            diagnostic_logger.log_detection(event)

                        # Collect feedback if feedback mode is enabled
                        if feedback_collector is not None:
                            last_event = event
                            last_image_paths = image_paths
                    else:
                        last_score_text = "Fusion failed"
                else:
                    last_score_text = "No board coords"

            if feedback_collector is not None and last_event is not None:
                state = "feedback"
            else:
                state = "countdown_result"
            state_start = current_time

        elif state == "feedback":
            # Wait for y/n keypress — handled in key section below
            pass

        elif state == "countdown_result":
            # Show result for 5s, then restart cycle
            if elapsed >= 5.0:
                state = "stabilize"
                state_start = current_time
                logger.info("Resetting for next throw...")

        # --- Display ---
        for camera_id in camera_ids:
            if camera_id not in frames:
                continue
            display = frames[camera_id].copy()
            h, w = display.shape[:2]

            if state == "stabilize":
                cv2.putText(display, "Stabilizing...", (w // 2 - 120, h // 2),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)

            elif state == "countdown_throw":
                remaining = max(0, 3.0 - elapsed)
                cv2.putText(display, f"Throw in {remaining:.0f}s", (w // 2 - 130, h // 2 - 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
                cv2.putText(display, "Remove dart from board", (w // 2 - 180, h // 2 + 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

            elif state == "waiting":
                cv2.putText(display, "THROW NOW", (w // 2 - 120, h // 2),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)

            elif state == "feedback":
                # Show score and ask for confirmation
                cv2.putText(display, last_score_text, (w // 2 - 150, h // 2 - 40),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
                cv2.putText(display, last_detail_text, (20, h - 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cv2.putText(display, "Correct? (y)es / (n)o", (w // 2 - 160, h // 2 + 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)

            elif state in ("detected", "countdown_result"):
                remaining = max(0, 5.0 - elapsed) if state == "countdown_result" else 0
                # Score in large text
                cv2.putText(display, last_score_text, (w // 2 - 150, h // 2 - 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
                cv2.putText(display, last_detail_text, (20, h - 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cv2.putText(display, last_cameras_text, (20, h - 35),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                if state == "countdown_result":
                    cv2.putText(display, f"Next in {remaining:.0f}s", (20, h - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            # Throw counter top-right
            cv2.putText(display, f"Throw #{throw_count}", (w - 160, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow(f"Camera {camera_id}", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

        # Handle feedback keypresses
        if state == "feedback" and last_event is not None:
            if key == ord('y') or key == ord('n'):
                detected_parsed = score_to_parsed_score(last_event.score)
                is_correct = (key == ord('y'))
                feedback_data = {
                    "detected_score": detected_parsed,
                    "actual_score": detected_parsed,
                    "is_correct": is_correct,
                    "user_response": "y" if is_correct else "n",
                    "dart_hit_event": last_event,
                    "image_paths": last_image_paths,
                }
                if feedback_storage is not None:
                    feedback_id = feedback_storage.save_feedback(feedback_data)
                    logger.info(f"Feedback saved: {feedback_id} ({'correct' if is_correct else 'incorrect'})")
                last_event = None
                last_image_paths = {}
                state = "countdown_result"
                state_start = time.time()

    cv2.destroyAllWindows()


def run_manual_dart_test(camera_ids, camera_manager, background_model,
                         dart_detectors, coordinate_mapper, calibration_manager,
                         score_calculator, session_dir, config, logger, diagnostic_logger=None,
                         feedback_collector=None, feedback_storage=None):
    """Manual single-dart test loop with fixed countdown (no motion detection).

    Cycle:
      1. Show result for 5s
      2. "REMOVE DART" with 3s countdown
      3. Stabilize background (2s, hands clear)
      4. "PUT IN NOW" with 5s countdown for placing dart by hand
      5. Capture post frame, run detection + fusion
      6. Back to 1
    Press 'q' or ESC to quit.
    """
    remove_time = 3.0   # Seconds to remove dart
    stabilize_time = 2.0  # Seconds to stabilize (hands clear)
    place_time = 7.0    # Seconds to place dart
    result_time = 5.0   # Seconds to show result
    throw_count = 0

    # States: "stabilize", "placing", "detecting", "feedback", "result", "removing"
    # First run starts at "stabilize" (no dart to remove yet)
    state = "stabilize"
    state_start = time.time()
    last_score_text = ""
    last_detail_text = ""
    last_event = None
    last_image_paths = {}
    last_cameras_text = ""

    for i, camera_id in enumerate(camera_ids):
        cv2.namedWindow(f"Camera {camera_id}", cv2.WINDOW_NORMAL)
        cv2.resizeWindow(f"Camera {camera_id}", 640, 480)
        cv2.moveWindow(f"Camera {camera_id}", i * 200, i * 150)

    logger.info("=== MANUAL DART TEST MODE ===")
    logger.info("Stabilizing cameras...")

    while True:
        current_time = time.time()
        elapsed = current_time - state_start

        frames = {}
        for camera_id in camera_ids:
            frame = camera_manager.get_latest_frame(camera_id)
            if frame is not None:
                frames[camera_id] = frame

        if not frames:
            time.sleep(0.01)
            continue

        # --- State machine ---
        if state == "stabilize":
            if elapsed >= stabilize_time:
                for camera_id, frame in frames.items():
                    background_model.update_pre_impact(camera_id, frame)
                for det in dart_detectors.values():
                    det.reset_previous_darts()
                logger.info("Background captured - place your dart")
                state = "placing"
                state_start = current_time

        elif state == "placing":
            if elapsed >= place_time:
                state = "detecting"
                state_start = current_time

        elif state == "detecting":
            # Clear previous result immediately
            last_score_text = ""
            last_detail_text = ""
            last_cameras_text = ""
            # Capture post frames
            for camera_id in camera_ids:
                frame = camera_manager.get_latest_frame(camera_id)
                if frame is not None:
                    background_model.add_post_impact_candidate(camera_id, frame)

            throw_count += 1
            throw_timestamp = datetime.now().strftime("%H-%M-%S")
            throw_dir = session_dir / f"Throw_{throw_count:03d}_{throw_timestamp}"
            throw_dir.mkdir(parents=True, exist_ok=True)

            detections = {}
            for camera_id in camera_ids:
                if not background_model.has_pre_impact(camera_id):
                    continue
                pre_frame = background_model.get_pre_impact(camera_id)
                post_frame = background_model.get_best_post_impact(camera_id)
                if post_frame is None:
                    continue

                tip_x, tip_y, confidence, debug_info = dart_detectors[camera_id].detect(
                    pre_frame, post_frame, mask_previous=False
                )
                detections[camera_id] = {
                    'tip_x': tip_x, 'tip_y': tip_y,
                    'confidence': confidence, 'debug_info': debug_info,
                }

                board_x, board_y = None, None
                if tip_x is not None and coordinate_mapper.is_calibrated(camera_id):
                    board_result = coordinate_mapper.map_to_board(camera_id, float(tip_x), float(tip_y))
                    if board_result is not None:
                        board_x, board_y = board_result
                detections[camera_id]['board_x'] = board_x
                detections[camera_id]['board_y'] = board_y

                if tip_x is not None:
                    annotated = post_frame.copy()
                    cv2.circle(annotated, (tip_x, tip_y), 10, (0, 0, 255), 2)
                    cv2.circle(annotated, (tip_x, tip_y), 3, (0, 255, 0), -1)
                    cv2.putText(annotated, f"({tip_x},{tip_y})", (tip_x + 15, tip_y - 15),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    if debug_info and 'contour' in debug_info:
                        cv2.drawContours(annotated, [debug_info['contour']], -1, (255, 0, 0), 2)
                    cv2.imwrite(str(throw_dir / f"cam{camera_id}_annotated.jpg"), annotated)
                else:
                    cv2.imwrite(str(throw_dir / f"cam{camera_id}_annotated.jpg"), post_frame)
                cv2.imwrite(str(throw_dir / f"cam{camera_id}_pre.jpg"), pre_frame)
                cv2.imwrite(str(throw_dir / f"cam{camera_id}_post.jpg"), post_frame)

            detected_cameras = [cid for cid, d in detections.items() if d['tip_x'] is not None]
            last_score_text = "No detection"
            last_detail_text = ""
            last_cameras_text = f"Detected: {len(detected_cameras)}/{len(camera_ids)} cams"

            if detected_cameras:
                fusion_detections = []
                image_paths = {}
                for cam_id in detected_cameras:
                    det = detections[cam_id]
                    if det.get('board_x') is not None:
                        fusion_detections.append({
                            'camera_id': cam_id,
                            'pixel': (det['tip_x'], det['tip_y']),
                            'board': (det['board_x'], det['board_y']),
                            'confidence': det['confidence'],
                        })
                        image_paths[str(cam_id)] = str(throw_dir / f"cam{cam_id}_annotated.jpg")

                if fusion_detections:
                    event = score_calculator.process_detections(fusion_detections, image_paths=image_paths)
                    if event is not None:
                        s = event.score
                        if s.ring == "bull":
                            last_score_text = "BULL (50)"
                        elif s.ring == "single_bull":
                            last_score_text = "Single Bull (25)"
                        elif s.ring == "out_of_bounds":
                            last_score_text = "MISS (0)"
                        else:
                            ring_prefix = {"triple": "T", "double": "D", "single": "S"}.get(s.ring, "")
                            last_score_text = f"{ring_prefix}{s.sector} = {s.total}"
                        last_detail_text = f"r={event.radius:.1f}mm  angle={event.angle_deg:.0f}deg  conf={event.fusion_confidence:.2f}"
                        last_cameras_text = f"Cameras: {event.cameras_used} ({event.num_cameras} used)"
                        logger.info(f"Throw {throw_count}: {last_score_text} | {last_detail_text}")

                        event_path = throw_dir / f"event_{throw_timestamp}.json"
                        with open(event_path, 'w') as f:
                            json.dump(event.to_dict(), f, indent=2)

                        # Log to diagnostics if enabled
                        if diagnostic_logger is not None:
                            diagnostic_logger.log_detection(event)

                        # Collect feedback if feedback mode is enabled
                        if feedback_collector is not None:
                            last_event = event
                            last_image_paths = image_paths
                    else:
                        last_score_text = "Fusion failed"
                else:
                    last_score_text = "No board coords"

            if feedback_collector is not None and last_event is not None:
                state = "feedback"
            else:
                state = "result"
            state_start = current_time

        elif state == "feedback":
            # Wait for y/n keypress — handled in key section below
            pass

        elif state == "result":
            if elapsed >= result_time:
                state = "removing"
                state_start = current_time
                logger.info("Remove dart now...")

        elif state == "removing":
            if elapsed >= remove_time:
                state = "stabilize"
                state_start = current_time
                logger.info("Stabilizing background...")

        # --- Display ---
        for camera_id in camera_ids:
            if camera_id not in frames:
                continue
            display = frames[camera_id].copy()
            h, w = display.shape[:2]

            if state == "stabilize":
                remaining = max(0, stabilize_time - elapsed)
                cv2.putText(display, "Stabilizing...", (w // 2 - 120, h // 2 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
                cv2.putText(display, "Keep hands clear", (w // 2 - 130, h // 2 + 25),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)

            elif state == "removing":
                remaining = max(0, remove_time - elapsed)
                cv2.putText(display, "REMOVE DART", (w // 2 - 140, h // 2 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 165, 255), 3)
                cv2.putText(display, f"{remaining:.0f}s", (w // 2 - 20, h // 2 + 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

            elif state == "placing":
                remaining = max(0, place_time - elapsed)
                cv2.putText(display, "PUT IN NOW", (w // 2 - 130, h // 2 - 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
                cv2.putText(display, f"Detecting in {remaining:.0f}s", (w // 2 - 130, h // 2 + 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

            elif state == "detecting":
                cv2.putText(display, "Detecting...", (w // 2 - 120, h // 2),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)

            elif state == "feedback":
                # Show score and ask for confirmation
                cv2.putText(display, last_score_text, (w // 2 - 150, h // 2 - 40),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
                cv2.putText(display, last_detail_text, (20, h - 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cv2.putText(display, "Correct? (y)es / (n)o", (w // 2 - 160, h // 2 + 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)

            elif state == "result":
                remaining = max(0, result_time - elapsed)
                cv2.putText(display, last_score_text, (w // 2 - 150, h // 2 - 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
                cv2.putText(display, last_detail_text, (20, h - 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cv2.putText(display, last_cameras_text, (20, h - 35),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cv2.putText(display, f"Next in {remaining:.0f}s", (20, h - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            cv2.putText(display, f"Throw #{throw_count}", (w - 160, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow(f"Camera {camera_id}", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

        # Handle feedback keypresses
        if state == "feedback" and last_event is not None:
            if key == ord('y') or key == ord('n'):
                detected_parsed = score_to_parsed_score(last_event.score)
                is_correct = (key == ord('y'))
                feedback_data = {
                    "detected_score": detected_parsed,
                    "actual_score": detected_parsed,
                    "is_correct": is_correct,
                    "user_response": "y" if is_correct else "n",
                    "dart_hit_event": last_event,
                    "image_paths": last_image_paths,
                }
                if feedback_storage is not None:
                    feedback_id = feedback_storage.save_feedback(feedback_data)
                    logger.info(f"Feedback saved: {feedback_id} ({'correct' if is_correct else 'incorrect'})")
                last_event = None
                last_image_paths = {}
                state = "result"
                state_start = time.time()


def run_accuracy_test(camera_ids, camera_manager, background_model,
                      dart_detectors, coordinate_mapper, calibration_manager,
                      score_calculator, config, logger, accuracy_runner):
    """Accuracy test loop using manual-dart-test state machine.

    Guides the user through placing darts at known board positions,
    detects each placement, and records results via AccuracyTestRunner.

    Cycle:
      1. Stabilize background (2s, hands clear)
      2. "Place dart at: T20" with 5s countdown
      3. Capture post frame, run detection + fusion, record result
      4. Show comparison results for 5s
      5. "REMOVE DART" with 3s countdown
      6. Back to 1 (or finish if all positions tested)
    Press 'q' or ESC to quit.
    """
    remove_time = 3.0
    stabilize_time = 2.0
    place_time = 7.0
    result_time = 5.0

    state = "stabilize"
    state_start = time.time()
    last_score_text = ""
    last_detail_text = ""
    last_cameras_text = ""
    last_comparison_text = ""

    for i, camera_id in enumerate(camera_ids):
        cv2.namedWindow(f"Camera {camera_id}", cv2.WINDOW_NORMAL)
        cv2.resizeWindow(f"Camera {camera_id}", 640, 480)
        cv2.moveWindow(f"Camera {camera_id}", i * 200, i * 150)

    total_positions = len(accuracy_runner.positions)
    logger.info("=== ACCURACY TEST MODE ===")
    logger.info(f"Testing {total_positions} known positions")
    logger.info("Stabilizing cameras...")

    while True:
        current_time = time.time()
        elapsed = current_time - state_start

        frames = {}
        for camera_id in camera_ids:
            frame = camera_manager.get_latest_frame(camera_id)
            if frame is not None:
                frames[camera_id] = frame

        if not frames:
            time.sleep(0.01)
            continue

        # Check if all positions tested
        if accuracy_runner.is_complete():
            logger.info("All positions tested!")
            break

        target = accuracy_runner.get_current_target()
        target_num = accuracy_runner.current_index + 1
        target_label = f"Target {target_num}/{total_positions}: {target.name}" if target else "Complete"

        # --- State machine ---
        if state == "stabilize":
            if elapsed >= stabilize_time:
                for camera_id, frame in frames.items():
                    background_model.update_pre_impact(camera_id, frame)
                for det in dart_detectors.values():
                    det.reset_previous_darts()
                logger.info(f"Background captured - place dart at: {target.name}")
                state = "placing"
                state_start = current_time

        elif state == "placing":
            if elapsed >= place_time:
                state = "detecting"
                state_start = current_time

        elif state == "detecting":
            last_score_text = ""
            last_detail_text = ""
            last_cameras_text = ""
            last_comparison_text = ""

            for camera_id in camera_ids:
                frame = camera_manager.get_latest_frame(camera_id)
                if frame is not None:
                    background_model.add_post_impact_candidate(camera_id, frame)

            detections = {}
            for camera_id in camera_ids:
                if not background_model.has_pre_impact(camera_id):
                    continue
                pre_frame = background_model.get_pre_impact(camera_id)
                post_frame = background_model.get_best_post_impact(camera_id)
                if post_frame is None:
                    continue

                tip_x, tip_y, confidence, debug_info = dart_detectors[camera_id].detect(
                    pre_frame, post_frame, mask_previous=False
                )
                detections[camera_id] = {
                    'tip_x': tip_x, 'tip_y': tip_y,
                    'confidence': confidence, 'debug_info': debug_info,
                }

                board_x, board_y = None, None
                if tip_x is not None and coordinate_mapper.is_calibrated(camera_id):
                    board_result = coordinate_mapper.map_to_board(camera_id, float(tip_x), float(tip_y))
                    if board_result is not None:
                        board_x, board_y = board_result
                detections[camera_id]['board_x'] = board_x
                detections[camera_id]['board_y'] = board_y

            detected_cameras = [cid for cid, d in detections.items() if d['tip_x'] is not None]
            last_score_text = "No detection"
            last_detail_text = ""
            last_cameras_text = f"Detected: {len(detected_cameras)}/{len(camera_ids)} cams"
            last_comparison_text = ""

            if detected_cameras:
                fusion_detections = []
                image_paths = {}
                for cam_id in detected_cameras:
                    det = detections[cam_id]
                    if det.get('board_x') is not None:
                        fusion_detections.append({
                            'camera_id': cam_id,
                            'pixel': (det['tip_x'], det['tip_y']),
                            'board': (det['board_x'], det['board_y']),
                            'confidence': det['confidence'],
                        })

                if fusion_detections:
                    event = score_calculator.process_detections(fusion_detections, image_paths=image_paths)
                    if event is not None:
                        # Record result via accuracy runner
                        accuracy_runner.record_result(event)
                        result = accuracy_runner.results[-1]

                        s = event.score
                        if s.ring == "bull":
                            last_score_text = "BULL (50)"
                        elif s.ring == "single_bull":
                            last_score_text = "Single Bull (25)"
                        elif s.ring == "out_of_bounds":
                            last_score_text = "MISS (0)"
                        else:
                            ring_prefix = {"triple": "T", "double": "D", "single": "S"}.get(s.ring, "")
                            last_score_text = f"{ring_prefix}{s.sector} = {s.total}"
                        last_detail_text = f"r={event.radius:.1f}mm  angle={event.angle_deg:.0f}deg  conf={event.fusion_confidence:.2f}"
                        last_cameras_text = f"Cameras: {event.cameras_used} ({event.num_cameras} used)"

                        # Build comparison text
                        ring_ok = "Y" if result["ring_match"] else "N"
                        sector_ok = "Y" if result["sector_match"] else "N"
                        last_comparison_text = (
                            f"Expected: {target.expected_score}  Detected: {result['detected_score']}  "
                            f"PosErr: {result['position_error_mm']:.1f}mm  "
                            f"Ring:{ring_ok} Sector:{sector_ok}"
                        )
                        logger.info(
                            f"{target.name}: detected={last_score_text} expected={target.expected_score} "
                            f"pos_err={result['position_error_mm']:.1f}mm "
                            f"ring={ring_ok} sector={sector_ok}"
                        )
                    else:
                        last_score_text = "Fusion failed"
                else:
                    last_score_text = "No board coords"

            state = "result"
            state_start = current_time

        elif state == "result":
            if elapsed >= result_time:
                if accuracy_runner.is_complete():
                    logger.info("All positions tested!")
                    break
                state = "removing"
                state_start = current_time
                logger.info("Remove dart now...")

        elif state == "removing":
            if elapsed >= remove_time:
                state = "stabilize"
                state_start = current_time
                logger.info("Stabilizing background...")

        # --- Display ---
        for camera_id in camera_ids:
            if camera_id not in frames:
                continue
            display = frames[camera_id].copy()
            h, w = display.shape[:2]

            if state == "stabilize":
                cv2.putText(display, "Stabilizing...", (w // 2 - 120, h // 2 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
                cv2.putText(display, "Keep hands clear", (w // 2 - 130, h // 2 + 25),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)

            elif state == "removing":
                remaining = max(0, remove_time - elapsed)
                cv2.putText(display, "REMOVE DART", (w // 2 - 140, h // 2 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 165, 255), 3)
                cv2.putText(display, f"{remaining:.0f}s", (w // 2 - 20, h // 2 + 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

            elif state == "placing":
                remaining = max(0, place_time - elapsed)
                cv2.putText(display, f"Place dart at: {target.name}", (w // 2 - 180, h // 2 - 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 3)
                cv2.putText(display, f"Detecting in {remaining:.0f}s", (w // 2 - 130, h // 2 + 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

            elif state == "detecting":
                cv2.putText(display, "Detecting...", (w // 2 - 120, h // 2),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)

            elif state == "result":
                remaining = max(0, result_time - elapsed)
                cv2.putText(display, last_score_text, (w // 2 - 150, h // 2 - 40),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
                if last_comparison_text:
                    cv2.putText(display, last_comparison_text, (20, h - 80),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
                cv2.putText(display, last_detail_text, (20, h - 55),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cv2.putText(display, last_cameras_text, (20, h - 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cv2.putText(display, f"Next in {remaining:.0f}s", (20, h - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            # Progress counter top-right
            cv2.putText(display, target_label, (w - 280, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow(f"Camera {camera_id}", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description='ARU-DART Camera Capture')
    parser.add_argument('--config', default='config.toml', help='Path to config file')
    parser.add_argument('--dev-mode', action='store_true', help='Enable development mode with preview')
    parser.add_argument('--show-histogram', action='store_true', help='Show histogram overlay (dev mode only)')
    parser.add_argument('--manual-test', action='store_true', help='Enable manual testing mode (pause/place dart/detect)')
    parser.add_argument('--record-mode', action='store_true', help='Enable recording mode (capture images for regression tests)')
    parser.add_argument('--single-camera', type=int, choices=[0, 1, 2], help='Test single camera only (0, 1, or 2)')
    parser.add_argument('--calibrate', action='store_true', help='Run manual calibration at startup')
    parser.add_argument('--calibrate-intrinsic', action='store_true', help='Run intrinsic calibration at startup')
    parser.add_argument('--verify-calibration', action='store_true', help='Run calibration verification at startup')
    parser.add_argument('--single-dart-test', action='store_true', help='Timed single dart test loop (auto background/detect/display)')
    parser.add_argument('--manual-dart-test', action='store_true', help='Manual single dart test loop (place by hand with countdown)')
    parser.add_argument('--diagnostics', action='store_true', help='Enable diagnostic logging (requires --manual-dart-test or --single-dart-test)')
    parser.add_argument('--accuracy-test', action='store_true', help='Run accuracy test mode (implies --diagnostics)')
    parser.add_argument('--ring', type=str, choices=['T', 'D', 'BS', 'SS'],
                        help='Ring filter for accuracy test: T=triple, D=double, BS=big single, SS=small single. Tests all 20 sectors for that ring.')
    parser.add_argument('--feedback-mode', action='store_true', help='Enable feedback collection mode')
    args = parser.parse_args()

    # --accuracy-test implies --diagnostics
    if args.accuracy_test:
        args.diagnostics = True

    # --diagnostics requires a test mode
    if args.diagnostics and not (args.manual_dart_test or args.single_dart_test or args.accuracy_test):
        parser.error("--diagnostics requires --manual-dart-test, --single-dart-test, or --accuracy-test")

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
    
    # Run calibration scripts if requested (before main loop)
    if args.calibrate or args.calibrate_intrinsic or args.verify_calibration:
        import subprocess
        import sys as _sys
        python = _sys.executable
        
        if args.calibrate_intrinsic:
            logger.info("Running intrinsic calibration...")
            cmd = [python, "calibration/calibrate_intrinsic.py", "--config", args.config]
            if args.single_camera is not None:
                cmd += ["--camera", str(args.single_camera)]
            result = subprocess.run(cmd)
            if result.returncode != 0:
                logger.error("Intrinsic calibration failed")
                camera_manager.stop_all()
                return
        
        if args.calibrate:
            logger.info("Running manual calibration...")
            cmd = [python, "calibration/calibrate_manual.py", "--config", args.config]
            if args.single_camera is not None:
                cmd += ["--camera", str(args.single_camera)]
            result = subprocess.run(cmd)
            if result.returncode != 0:
                logger.error("Manual calibration failed")
                camera_manager.stop_all()
                return
        
        if args.verify_calibration:
            logger.info("Running calibration verification...")
            for cam_idx in ([args.single_camera] if args.single_camera is not None else [0, 1, 2]):
                cmd = [python, "calibration/verify_calibration.py", "--camera", str(cam_idx), "--config", args.config]
                result = subprocess.run(cmd)
                if result.returncode != 0:
                    logger.warning(f"Verification failed for camera {cam_idx}")
    
    # Initialize coordinate mapper
    coordinate_mapper = CoordinateMapper(config)
    calibrated_cameras = coordinate_mapper.get_calibrated_cameras()
    if calibrated_cameras:
        logger.info(f"Coordinate mapping active for cameras: {calibrated_cameras}")
    else:
        logger.warning("No cameras calibrated - board coordinates will not be available")
    
    # Initialize score calculator for multi-camera fusion
    score_calculator = ScoreCalculator(config)
    logger.info("Score calculator initialized")

    # Initialize feedback system if --feedback-mode is enabled
    feedback_collector = None
    feedback_storage = None
    if args.feedback_mode:
        feedback_storage = FeedbackStorage()
        feedback_collector = FeedbackCollector()
        logger.info("Feedback mode enabled")

    # Initialize calibration manager
    calibration_manager = CalibrationManager(config, coordinate_mapper)
    board_geometry = BoardGeometry()

    # --- Accuracy test mode ---
    if args.accuracy_test:
        dart_config = config['dart_detection']
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
        background_model = BackgroundModel()

        # Build known positions and create accuracy test runner
        diagnostic_logger = DiagnosticLogger()
        logger.info(f"Accuracy test diagnostics: {diagnostic_logger.session_dir}")
        known_positions = build_known_positions(board_geometry, ring_filter=args.ring)
        accuracy_runner = AccuracyTestRunner(
            known_positions=known_positions,
            diagnostic_logger=diagnostic_logger,
            score_calculator=score_calculator,
        )
        logger.info(f"Accuracy test: {len(known_positions)} positions to test")

        try:
            run_accuracy_test(
                camera_ids, camera_manager, background_model,
                dart_detectors, coordinate_mapper, calibration_manager,
                score_calculator, config, logger, accuracy_runner
            )
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            # Generate and save report
            report = accuracy_runner.generate_report()
            report_path = diagnostic_logger.session_dir / "accuracy_report.json"
            with open(report_path, 'w') as f:
                json.dump(report.to_dict(), f, indent=2)
            report.print_summary()
            diagnostic_logger.write_session_summary()
            logger.info(f"Report saved to: {report_path}")
            camera_manager.stop_all()
            logger.info("Shutdown complete")
        return

    # --- Single dart test mode: run dedicated loop and exit ---
    if args.single_dart_test:
        dart_config = config['dart_detection']
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
        motion_config = config['motion_detection']
        motion_detector = MotionDetector(
            downscale_factor=motion_config['downscale_factor'],
            motion_threshold=motion_config['motion_threshold'],
            blur_kernel=motion_config['blur_kernel'],
            settled_threshold=motion_config['settled_threshold']
        )
        background_model = BackgroundModel()
        session_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        throws_dir = Path("data/throws")
        throws_dir.mkdir(parents=True, exist_ok=True)
        existing_sessions = list(throws_dir.glob("Session_*"))
        session_number = len(existing_sessions) + 1
        session_dir = throws_dir / f"Session_{session_number:03d}_{session_timestamp}"
        session_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Session folder: {session_dir}")
        diagnostic_logger = None
        if args.diagnostics:
            diagnostic_logger = DiagnosticLogger()
            logger.info(f"Diagnostics enabled: {diagnostic_logger.session_dir}")
        try:
            run_single_dart_test(
                camera_ids, camera_manager, motion_detector, background_model,
                dart_detectors, coordinate_mapper, calibration_manager,
                score_calculator, session_dir, config, logger,
                diagnostic_logger=diagnostic_logger,
                feedback_collector=feedback_collector,
                feedback_storage=feedback_storage
            )
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            if diagnostic_logger is not None:
                diagnostic_logger.write_session_summary()
                logger.info(f"Diagnostics saved to: {diagnostic_logger.session_dir}")
            camera_manager.stop_all()
            logger.info("Shutdown complete")
        return

    # --- Manual dart test mode: fixed countdown, no motion detection ---
    if args.manual_dart_test:
        dart_config = config['dart_detection']
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
        background_model = BackgroundModel()
        session_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        throws_dir = Path("data/throws")
        throws_dir.mkdir(parents=True, exist_ok=True)
        existing_sessions = list(throws_dir.glob("Session_*"))
        session_number = len(existing_sessions) + 1
        session_dir = throws_dir / f"Session_{session_number:03d}_{session_timestamp}"
        session_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Session folder: {session_dir}")
        diagnostic_logger = None
        if args.diagnostics:
            diagnostic_logger = DiagnosticLogger()
            logger.info(f"Diagnostics enabled: {diagnostic_logger.session_dir}")
        try:
            run_manual_dart_test(
                camera_ids, camera_manager, background_model,
                dart_detectors, coordinate_mapper, calibration_manager,
                score_calculator, session_dir, config, logger,
                diagnostic_logger=diagnostic_logger,
                feedback_collector=feedback_collector,
                feedback_storage=feedback_storage
            )
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            if diagnostic_logger is not None:
                diagnostic_logger.write_session_summary()
                logger.info(f"Diagnostics saved to: {diagnostic_logger.session_dir}")
            camera_manager.stop_all()
            logger.info("Shutdown complete")
        return
    
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
    show_spiderweb = False  # Toggle spiderweb overlay with 'v' key
    spiderweb_cache = {}  # Cache generated spiderwebs per camera
    
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
                    # Check calibration state - skip scoring if calibrating
                    cal_status = calibration_manager.get_status()
                    if cal_status.state == "calibrating":
                        logger.info("Calibration in progress - skipping scoring")
                    
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
                                'debug_info': debug_info
                            }
                            
                            # Transform pixel to board coordinates if calibrated
                            board_x, board_y = None, None
                            if tip_x is not None and coordinate_mapper.is_calibrated(camera_id):
                                board_result = coordinate_mapper.map_to_board(camera_id, float(tip_x), float(tip_y))
                                if board_result is not None:
                                    board_x, board_y = board_result
                                    logger.info(f"  Camera {camera_id}: Board coords ({board_x:.1f}, {board_y:.1f}) mm")
                            
                            detections[camera_id]['board_x'] = board_x
                            detections[camera_id]['board_y'] = board_y
                            
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
                            board_str = ""
                            if det.get('board_x') is not None:
                                board_str = f", board=({det['board_x']:.1f}, {det['board_y']:.1f})mm"
                            logger.info(f"  Camera {cam_id}: Tip at ({det['tip_x']}, {det['tip_y']}), confidence: {det['confidence']:.2f}{board_str}")
                    else:
                        logger.warning("No dart detected in any camera - saving images for analysis")
                    
                    logger.info(f"Saved images to {throw_dir}")
                    
                    # --- Multi-camera fusion and scoring ---
                    if cal_status.state != "calibrating" and detected_cameras:
                        # Collect detections with board coordinates for fusion
                        fusion_detections = []
                        image_paths = {}
                        for cam_id in detected_cameras:
                            det = detections[cam_id]
                            if det.get('board_x') is not None and det.get('board_y') is not None:
                                fusion_detections.append({
                                    'camera_id': cam_id,
                                    'pixel': (det['tip_x'], det['tip_y']),
                                    'board': (det['board_x'], det['board_y']),
                                    'confidence': det['confidence'],
                                })
                                annotated_path = str(throw_dir / f"cam{cam_id}_annotated.jpg")
                                image_paths[str(cam_id)] = annotated_path
                        
                        if fusion_detections:
                            dart_hit_event = score_calculator.process_detections(
                                fusion_detections, image_paths=image_paths
                            )
                            
                            if dart_hit_event is not None:
                                # Log fusion results
                                score = dart_hit_event.score
                                logger.info(
                                    f"Score: {score.total} "
                                    f"(base={score.base}, multiplier={score.multiplier}, "
                                    f"ring={score.ring}, sector={score.sector})"
                                )
                                logger.info(
                                    f"Position: board=({dart_hit_event.board_x:.1f}, {dart_hit_event.board_y:.1f})mm, "
                                    f"r={dart_hit_event.radius:.1f}mm, theta={dart_hit_event.angle_deg:.1f}deg"
                                )
                                logger.info(
                                    f"Fusion: cameras={dart_hit_event.cameras_used}, "
                                    f"confidence={dart_hit_event.fusion_confidence:.2f}"
                                )
                                
                                # Save DartHitEvent to JSON
                                event_path = throw_dir / f"event_{throw_timestamp}.json"
                                with open(event_path, 'w') as f:
                                    json.dump(dart_hit_event.to_dict(), f, indent=2)
                                logger.info(f"Saved event to {event_path}")
                            else:
                                logger.warning("No valid detections after fusion")
                        else:
                            logger.warning("No detections with board coordinates for fusion")
                    
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
                    
                    # Draw spiderweb overlay if enabled and camera is calibrated
                    if show_spiderweb and coordinate_mapper.is_calibrated(camera_id):
                        if camera_id not in spiderweb_cache:
                            with coordinate_mapper._lock:
                                H = coordinate_mapper._homographies[camera_id].copy()
                            spiderweb_cache[camera_id] = board_geometry.generate_spiderweb(H)
                        display_frame = board_geometry.draw_spiderweb(
                            display_frame, spiderweb_cache[camera_id],
                            color=(0, 255, 255), thickness=1
                        )
                        # Show calibration status
                        cal_status = calibration_manager.get_status()
                        cal_text = f"Cal: {cal_status.state}"
                        if cal_status.drift_mm is not None:
                            cal_text += f" drift={cal_status.drift_mm:.1f}mm"
                        cv2.putText(display_frame, cal_text, (10, 120),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    
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
                elif key == ord('v'):
                    show_spiderweb = not show_spiderweb
                    spiderweb_cache.clear()  # Force regeneration
                    logger.info(f"Spiderweb overlay: {'ON' if show_spiderweb else 'OFF'}")
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
                    # In record mode: capture POST frame
                    # In dev mode (non-record): trigger manual calibration
                    if not args.record_mode:
                        if args.dev_mode:
                            logger.info("=== Running manual calibration (press q/ESC in calibration window to abort) ===")
                            import subprocess
                            import sys as _sys
                            cmd = [_sys.executable, "calibration/calibrate_manual.py", "--config", args.config]
                            result = subprocess.run(cmd)
                            if result.returncode == 0:
                                logger.info("Calibration complete - reloading coordinate mapper")
                                coordinate_mapper.reload_calibration()
                                spiderweb_cache.clear()
                                calibrated_cameras = coordinate_mapper.get_calibrated_cameras()
                                logger.info(f"Coordinate mapping active for cameras: {calibrated_cameras}")
                            else:
                                logger.warning("Calibration failed or was aborted")
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
