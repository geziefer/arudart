import logging
from .camera_stream import CameraStream
from .camera_control import apply_camera_settings
import cv2


class CameraManager:
    """Manage multiple camera streams."""
    
    def __init__(self, config):
        self.logger = logging.getLogger('arudart.camera_manager')
        self.cameras = {}
        
        # Check if auto-detection is enabled
        if 'camera_detection' in config and config['camera_detection'].get('auto_detect', False):
            self._auto_detect_cameras(config)
        else:
            self._init_from_config(config)
        
        if not self.cameras:
            self.logger.error("No cameras available - check connections")
        else:
            self.logger.info(f"Initialized {len(self.cameras)} camera(s)")
    
    def _auto_detect_cameras(self, config):
        """Auto-detect cameras based on criteria.
        
        Camera position mapping (clockwise from top):
        - cam0 = upper right (near 18, ~1 o'clock)
        - cam1 = lower right (near 17, ~5 o'clock)
        - cam2 = left (near 11, ~9 o'clock)
        """
        detection_config = config['camera_detection']
        camera_settings = config['camera_settings']
        
        num_cameras = detection_config.get('num_cameras', 3)
        min_width = detection_config.get('min_width', 800)
        min_height = detection_config.get('min_height', 600)
        exclude_builtin = detection_config.get('exclude_builtin', True)
        max_index = detection_config.get('max_index', 10)
        
        self.logger.info(f"Auto-detecting up to {num_cameras} cameras (indices 0-{max_index})...")
        
        found_cameras = []
        
        for idx in range(max_index + 1):
            if len(found_cameras) >= num_cameras:
                break
            
            # Try to open camera
            cap = cv2.VideoCapture(idx)
            if not cap.isOpened():
                continue
            
            # Check resolution capability
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, min_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, min_height)
            actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # Check if camera name suggests built-in camera
            is_builtin = False
            if exclude_builtin:
                # Built-in Mac cameras typically have high default resolution (>1280x720)
                # OV9732 cameras are 1280x720 max
                if actual_width > 1280 or actual_height > 720:
                    is_builtin = True
                    self.logger.info(f"Camera {idx} appears to be built-in (resolution {actual_width}x{actual_height} > 1280x720) - skipping")
            
            cap.release()
            
            if is_builtin:
                continue
            
            if actual_width >= min_width and actual_height >= min_height:
                found_cameras.append(idx)
                self.logger.info(f"Detected camera {idx}: {actual_width}x{actual_height}")
            else:
                self.logger.debug(f"Camera {idx} resolution too low: {actual_width}x{actual_height}")
        
        # Initialize detected cameras
        for cam_idx, camera_id in enumerate(found_cameras):
            cam_key = f'cam{cam_idx}'
            
            # Apply platform-specific camera control if enabled
            if 'camera_control' in config and config['camera_control'].get('enabled', False):
                control_config = config['camera_control'].get('per_camera', {}).get(cam_key, {})
                if control_config:
                    self.logger.info(f"Applying camera control to {cam_key} (device {camera_id})")
                    apply_camera_settings(
                        device_index=camera_id,
                        exposure_time_ms=control_config.get('exposure_time_ms', 3),
                        contrast=control_config.get('contrast', 30),
                        gamma=control_config.get('gamma', 200),
                        auto_exposure=control_config.get('auto_exposure', False),
                        auto_white_balance=control_config.get('auto_white_balance', False),
                        auto_focus=control_config.get('auto_focus', False)
                    )
            
            camera = CameraStream(
                device_index=camera_id,
                width=camera_settings['width'],
                height=camera_settings['height'],
                fps=camera_settings['fps'],
                fourcc=camera_settings['fourcc']
            )
            
            if camera.opened:
                self.cameras[camera_id] = camera
                self.logger.info(f"Initialized camera {camera_id} (cam{cam_idx})")
    
    def _init_from_config(self, config):
        """Initialize cameras from explicit config (legacy)."""
        for cam_config in config['cameras']:
            camera_id = cam_config['device_index']
            
            camera = CameraStream(
                device_index=camera_id,
                width=cam_config['width'],
                height=cam_config['height'],
                fps=cam_config['fps'],
                fourcc=cam_config['fourcc'],
                auto_exposure=cam_config.get('auto_exposure', False),
                exposure=cam_config.get('exposure', -6)
            )
            
            if camera.opened:
                self.cameras[camera_id] = camera
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
    
    def get_camera_ids(self):
        """Get list of all camera IDs."""
        return list(self.cameras.keys())
    
    def stop_all(self):
        """Stop all camera streams."""
        for camera in self.cameras.values():
            camera.stop()
        self.logger.info("All cameras stopped")
