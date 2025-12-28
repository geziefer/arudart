import cv2
import numpy as np
import logging


class MotionDetector:
    """Detect motion via frame differencing on downscaled frames."""
    
    def __init__(self, downscale_factor=4, motion_threshold=25, blur_kernel=21, settled_threshold=10):
        self.downscale_factor = downscale_factor
        self.motion_threshold = motion_threshold
        self.blur_kernel = blur_kernel
        self.settled_threshold = settled_threshold
        self.logger = logging.getLogger('arudart.motion_detector')
        
        # Background frames per camera
        self.background_frames = {}
        
    def update_background(self, camera_id, frame):
        """Update background frame for a camera."""
        if frame is None:
            return
        
        # Downscale and convert to grayscale
        small = cv2.resize(frame, (frame.shape[1] // self.downscale_factor, 
                                   frame.shape[0] // self.downscale_factor))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur
        blurred = cv2.GaussianBlur(gray, (self.blur_kernel, self.blur_kernel), 0)
        
        self.background_frames[camera_id] = blurred
        self.logger.debug(f"Updated background for camera {camera_id}")
    
    def detect_motion(self, camera_id, frame):
        """
        Detect motion in frame compared to background.
        Returns: (motion_detected, motion_amount, diff_frame)
        """
        if frame is None or camera_id not in self.background_frames:
            return False, 0, None
        
        # Downscale and convert to grayscale
        small = cv2.resize(frame, (frame.shape[1] // self.downscale_factor, 
                                   frame.shape[0] // self.downscale_factor))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur
        blurred = cv2.GaussianBlur(gray, (self.blur_kernel, self.blur_kernel), 0)
        
        # Compute absolute difference
        diff = cv2.absdiff(self.background_frames[camera_id], blurred)
        
        # Threshold
        _, thresh = cv2.threshold(diff, self.motion_threshold, 255, cv2.THRESH_BINARY)
        
        # Calculate motion amount (percentage of pixels above threshold)
        motion_amount = np.sum(thresh > 0) / thresh.size * 100
        
        # Motion detected if above settled threshold
        motion_detected = motion_amount > self.settled_threshold
        
        return motion_detected, motion_amount, thresh
    
    def detect_combined_motion(self, camera_frames):
        """
        Detect motion across multiple cameras.
        Returns: (any_motion, per_camera_motion, max_motion_amount)
        """
        per_camera_motion = {}
        max_motion = 0
        
        for camera_id, frame in camera_frames.items():
            motion_detected, motion_amount, _ = self.detect_motion(camera_id, frame)
            per_camera_motion[camera_id] = (motion_detected, motion_amount)
            max_motion = max(max_motion, motion_amount)
        
        any_motion = any(detected for detected, _ in per_camera_motion.values())
        
        return any_motion, per_camera_motion, max_motion
