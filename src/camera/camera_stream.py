import cv2
import threading
import logging


class CameraStream:
    """Threaded camera capture for continuous frame grabbing."""
    
    def __init__(self, device_index, width, height, fps, fourcc):
        self.device_index = device_index
        self.logger = logging.getLogger(f'arudart.camera.{device_index}')
        self.cap = None
        self.frame = None
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self.opened = False
        
        # Open camera
        self.cap = cv2.VideoCapture(device_index)
        if not self.cap.isOpened():
            self.logger.warning(f"Failed to open camera {device_index}")
            return
        
        # Set properties
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        
        # Log actual settings
        actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.logger.info(f"Camera {device_index} opened: {actual_width}x{actual_height} @ {actual_fps} FPS")
        self.opened = True
    
    def start(self):
        """Start capture thread."""
        if not self.opened or self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        self.logger.info(f"Camera {self.device_index} capture started")
    
    def _capture_loop(self):
        """Continuously grab frames."""
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame
    
    def get_frame(self):
        """Get latest frame (thread-safe)."""
        with self.lock:
            return self.frame.copy() if self.frame is not None else None
    
    def stop(self):
        """Stop capture and release camera."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()
        self.logger.info(f"Camera {self.device_index} stopped")
