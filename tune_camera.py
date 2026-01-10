#!/usr/bin/env python3
"""Camera tuning tool - adjust exposure, brightness, contrast, gamma in real-time."""

import cv2
import subprocess
import sys
import argparse
import time
import threading

# Global variables for slider values
exposure_val = 3000
brightness_val = 0
contrast_val = 30
gamma_val = 200
last_change_time = 0
apply_delay = 0.5  # Wait 500ms after last slider change before applying
apply_thread = None
camera_id = 0

def apply_settings_delayed():
    """Wait for delay, then apply settings if no new changes."""
    global last_change_time
    time.sleep(apply_delay)
    
    # Check if another change happened during sleep
    if time.time() - last_change_time >= apply_delay:
        apply_settings(camera_id)

def trigger_apply():
    """Trigger delayed application of settings."""
    global last_change_time, apply_thread
    last_change_time = time.time()
    
    # Start new thread if none running
    if apply_thread is None or not apply_thread.is_alive():
        apply_thread = threading.Thread(target=apply_settings_delayed, daemon=True)
        apply_thread.start()

def apply_settings(cam_id):
    """Apply current slider values to camera using uvc-util."""
    try:
        cmd = ['./uvc-util', '-I', str(cam_id),
               '-s', 'auto-exposure-mode=1',  # Manual mode
               '-s', f'exposure-time-abs={exposure_val}',
               '-s', f'brightness={brightness_val / 100.0:.2f}',  # Normalized 0-1
               '-s', f'contrast={contrast_val}',
               '-s', f'gamma={gamma_val}']
        
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"Applied: exposure={exposure_val}µs, brightness={brightness_val}, contrast={contrast_val}, gamma={gamma_val}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.stderr.decode()}")
        return False

def on_exposure_change(val):
    global exposure_val
    exposure_val = val
    trigger_apply()

def on_brightness_change(val):
    global brightness_val
    brightness_val = val - 64  # Slider 0-64 -> actual -64 to 0
    trigger_apply()

def on_contrast_change(val):
    global contrast_val
    contrast_val = val
    trigger_apply()

def on_gamma_change(val):
    global gamma_val
    gamma_val = val
    trigger_apply()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Camera tuning tool')
    parser.add_argument('camera_id', type=int, help='Camera ID (0, 1, or 2)')
    args = parser.parse_args()
    
    camera_id = args.camera_id
    
    # Open camera
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        print(f"Failed to open camera {camera_id}")
        sys.exit(1)
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 800)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 600)
    
    # Create window and sliders
    window_name = f'Camera {camera_id} Tuning'
    cv2.namedWindow(window_name)
    
    cv2.createTrackbar('Exposure (µs)', window_name, 3000, 4000, on_exposure_change)
    cv2.setTrackbarMin('Exposure (µs)', window_name, 2000)
    
    cv2.createTrackbar('Brightness', window_name, 64, 64, on_brightness_change)  # 0-64 on slider = -64 to 0 actual
    
    cv2.createTrackbar('Contrast', window_name, 30, 50, on_contrast_change)
    cv2.setTrackbarMin('Contrast', window_name, 10)
    
    cv2.createTrackbar('Gamma', window_name, 200, 400, on_gamma_change)
    cv2.setTrackbarMin('Gamma', window_name, 100)
    
    # Apply initial settings
    apply_settings(camera_id)
    
    print(f"Camera {camera_id} tuning tool")
    print("Adjust sliders to tune camera settings")
    print("Settings applied 500ms after you stop moving slider")
    print("Press 'q' to quit, 'p' to print current values")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Add text overlay with current values
        cv2.putText(frame, f"Camera {camera_id}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"Exposure: {exposure_val}us", (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"Brightness: {brightness_val}", (10, 90), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"Contrast: {contrast_val}", (10, 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"Gamma: {gamma_val}", (10, 150), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        cv2.imshow(window_name, frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('p'):
            print(f"\nCurrent settings for camera {camera_id}:")
            print(f"  exposure_time_ms = {exposure_val / 1000:.1f}")
            print(f"  brightness = {brightness_val}")
            print(f"  contrast = {contrast_val}")
            print(f"  gamma = {gamma_val}")
            print()
    
    cap.release()
    cv2.destroyAllWindows()
