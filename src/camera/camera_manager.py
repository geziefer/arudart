import logging
from .camera_stream import CameraStream


class CameraManager:
    """Manage camera streams."""
    
    def __init__(self, config):
        self.logger = logging.getLogger('arudart.camera_manager')
        self.cameras = {}
        
        # Initialize single camera from config
        cam_config = config['camera']
        camera_id = cam_config['device_index']
        
        self.cameras[camera_id] = CameraStream(
            device_index=camera_id,
            width=cam_config['width'],
            height=cam_config['height'],
            fps=cam_config['fps'],
            fourcc=cam_config['fourcc'],
            auto_exposure=cam_config.get('auto_exposure', False),
            exposure=cam_config.get('exposure', -6)
        )
        
        self.logger.info(f"Initialized camera {camera_id}")
    
    def start_all(self):
        """Start all camera streams."""
        for camera_id, camera in self.cameras.items():
            camera.start()
        self.logger.info("All cameras started")
    
    def get_latest_frame(self, camera_id):
        """Get latest frame from specified camera."""
        if camera_id not in self.cameras:
            return None
        return self.cameras[camera_id].get_frame()
    
    def stop_all(self):
        """Stop all camera streams."""
        for camera in self.cameras.values():
            camera.stop()
        self.logger.info("All cameras stopped")
