---
inclusion: always
---

# Python Best Practices for ARU-DART

## Code Style

- Follow PEP 8 conventions
- Use type hints for function signatures
- Write docstrings for classes and public methods
- Keep functions focused and single-purpose
- Use meaningful variable names (avoid single letters except in loops)

## OpenCV Patterns

### Image Reading/Writing
```python
# Always check if image loaded successfully
image = cv2.imread(path)
if image is None:
    logger.error(f"Failed to load image: {path}")
    return None

# Use absolute paths or Path objects
from pathlib import Path
image_path = Path("data/throws") / f"cam{camera_id}_annotated.jpg"
cv2.imwrite(str(image_path), image)
```

### Color Space Conversions
```python
# OpenCV uses BGR by default, not RGB
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# For display with matplotlib, convert to RGB
rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
```

### Contour Operations
```python
# Find contours (returns contours, hierarchy)
contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# Always check if contours found
if not contours:
    return None

# Sort by area
contours = sorted(contours, key=cv2.contourArea, reverse=True)
```

### Morphological Operations
```python
# Use appropriate kernel shapes
kernel_ellipse = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
kernel_rect = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

# Progressive closing for gap filling
for kernel_size in [15, 21, 27, 35]:
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
```

## Threading & Concurrency

### Camera Capture Threads
```python
import threading

class CameraStream:
    def __init__(self, camera_id):
        self.camera_id = camera_id
        self.frame = None
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
    
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
    
    def _capture_loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame
    
    def get_latest_frame(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None
```

## Configuration Management

### TOML Loading
```python
import tomli  # Python 3.11+ has tomllib built-in

def load_config(config_path: str) -> dict:
    """Load configuration from TOML file."""
    with open(config_path, 'rb') as f:
        config = tomli.load(f)
    return config

# Access nested config
exposure = config['camera_control']['per_camera']['cam0']['exposure_time_ms']
```

## Logging

### Structured Logging
```python
import logging

# Setup in logging_setup.py
def setup_logging(log_level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/arudart.log'),
            logging.StreamHandler()
        ]
    )

# Usage in modules
logger = logging.getLogger(__name__)
logger.info(f"Camera {camera_id} detected dart at ({tip_x}, {tip_y})")
logger.warning(f"Low confidence detection: {confidence:.2f}")
logger.error(f"Failed to detect dart in camera {camera_id}")
```

## Error Handling

### Graceful Degradation
```python
def detect_dart(pre_frame, post_frame):
    """Detect dart with graceful error handling."""
    try:
        # Detection logic
        tip_x, tip_y, confidence = _detect_dart_internal(pre_frame, post_frame)
        return tip_x, tip_y, confidence
    except cv2.error as e:
        logger.error(f"OpenCV error during detection: {e}")
        return None, None, 0.0
    except Exception as e:
        logger.exception(f"Unexpected error during detection: {e}")
        return None, None, 0.0
```

## Performance Optimization

### Avoid Unnecessary Copies
```python
# BAD: Creates unnecessary copy
gray = cv2.cvtColor(image.copy(), cv2.COLOR_BGR2GRAY)

# GOOD: Operates on original
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
```

### Downscale for Motion Detection
```python
# Downscale by factor of 4 for motion detection
downscale_factor = 4
small_frame = cv2.resize(frame, 
                        (frame.shape[1] // downscale_factor, 
                         frame.shape[0] // downscale_factor))
```

### Reuse Buffers
```python
# Reuse mask buffer instead of creating new ones
if self.mask is None:
    self.mask = np.zeros(image.shape[:2], dtype=np.uint8)
else:
    self.mask.fill(0)  # Clear existing mask
```

## Testing

### Unit Tests with pytest
```python
import pytest
import cv2
import numpy as np

def test_dart_detection_basic():
    """Test basic dart detection on synthetic image."""
    # Create synthetic pre/post frames
    pre_frame = np.zeros((600, 800, 3), dtype=np.uint8)
    post_frame = pre_frame.copy()
    
    # Draw synthetic dart (white line)
    cv2.line(post_frame, (400, 200), (400, 350), (255, 255, 255), 5)
    
    # Run detection
    detector = DartDetector(config)
    tip_x, tip_y, confidence, _ = detector.detect(pre_frame, post_frame)
    
    # Verify detection
    assert tip_x is not None
    assert 390 < tip_x < 410  # Within tolerance
    assert confidence > 0.5
```

## Documentation

### Docstring Format
```python
def detect_dart(self, pre_frame: np.ndarray, post_frame: np.ndarray, 
                mask_previous: bool = False) -> tuple[int, int, float, dict]:
    """
    Detect dart tip position using image differencing.
    
    Args:
        pre_frame: Image before dart impact (BGR, 8-bit)
        post_frame: Image after dart impact (BGR, 8-bit)
        mask_previous: Whether to mask previously detected darts
    
    Returns:
        Tuple of (tip_x, tip_y, confidence, debug_info)
        Returns (None, None, 0.0, {}) if no dart detected
    
    Raises:
        ValueError: If frames have different shapes
    """
    pass
```
