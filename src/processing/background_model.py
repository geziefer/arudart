import logging


class BackgroundModel:
    """Manage background frames for dart detection."""
    
    def __init__(self):
        self.logger = logging.getLogger('arudart.background_model')
        self.pre_impact_frames = {}
    
    def update_pre_impact(self, camera_id, frame):
        """Store pre-impact frame for a camera."""
        if frame is not None:
            self.pre_impact_frames[camera_id] = frame.copy()
            self.logger.debug(f"Updated pre-impact frame for camera {camera_id}")
    
    def get_pre_impact(self, camera_id):
        """Get pre-impact frame for a camera."""
        return self.pre_impact_frames.get(camera_id)
    
    def has_pre_impact(self, camera_id):
        """Check if pre-impact frame exists for a camera."""
        return camera_id in self.pre_impact_frames
