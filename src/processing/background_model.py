import logging
import numpy as np
import cv2


class BackgroundModel:
    """Manage background frames for dart detection."""
    
    def __init__(self):
        self.logger = logging.getLogger('arudart.background_model')
        self.pre_impact_frames = {}
        self.post_impact_candidates = {}  # Store multiple post frames per camera
    
    def update_pre_impact(self, camera_id, frame):
        """Store pre-impact frame for a camera."""
        if frame is not None:
            self.pre_impact_frames[camera_id] = frame.copy()
            self.post_impact_candidates[camera_id] = []  # Reset post candidates
            self.logger.debug(f"Updated pre-impact frame for camera {camera_id}")
    
    def add_post_impact_candidate(self, camera_id, frame):
        """Add a post-impact frame candidate for a camera."""
        if frame is not None:
            if camera_id not in self.post_impact_candidates:
                self.post_impact_candidates[camera_id] = []
            self.post_impact_candidates[camera_id].append(frame.copy())
            self.logger.debug(f"Added post-impact candidate {len(self.post_impact_candidates[camera_id])} for camera {camera_id}")
    
    def get_best_post_impact(self, camera_id):
        """Select best post-impact frame with lowest background noise.
        
        Strategy: Compute diff for each candidate, select frame with lowest
        total diff in outer regions (board area), indicating least noise.
        """
        if camera_id not in self.post_impact_candidates or not self.post_impact_candidates[camera_id]:
            return None
        
        candidates = self.post_impact_candidates[camera_id]
        if len(candidates) == 1:
            return candidates[0]
        
        pre_frame = self.pre_impact_frames.get(camera_id)
        if pre_frame is None:
            return candidates[0]
        
        # Evaluate each candidate
        best_frame = None
        min_noise = float('inf')
        
        for idx, post_frame in enumerate(candidates):
            # Compute diff
            pre_gray = cv2.cvtColor(pre_frame, cv2.COLOR_BGR2GRAY)
            post_gray = cv2.cvtColor(post_frame, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(pre_gray, post_gray)
            
            # Measure noise in outer regions (exclude center where dart likely is)
            h, w = diff.shape
            mask = np.ones_like(diff, dtype=np.uint8)
            cv2.circle(mask, (w//2, h//2), min(w, h)//3, 0, -1)  # Exclude center circle
            
            noise_level = np.sum(diff[mask > 0])
            
            if noise_level < min_noise:
                min_noise = noise_level
                best_frame = post_frame
        
        self.logger.info(f"Selected best post frame for camera {camera_id} from {len(candidates)} candidates (noise={min_noise:.0f})")
        return best_frame
    
    def get_pre_impact(self, camera_id):
        """Get pre-impact frame for a camera."""
        return self.pre_impact_frames.get(camera_id)
    
    def has_pre_impact(self, camera_id):
        """Check if pre-impact frame exists for a camera."""
        return camera_id in self.pre_impact_frames
    
    def clear_post_candidates(self, camera_id):
        """Clear post-impact candidates for a camera."""
        if camera_id in self.post_impact_candidates:
            self.post_impact_candidates[camera_id] = []
