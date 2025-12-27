import time


class FPSCounter:
    """Track FPS over a rolling window."""
    
    def __init__(self, window_size=30):
        self.window_size = window_size
        self.timestamps = []
    
    def tick(self):
        """Record a frame timestamp."""
        now = time.time()
        self.timestamps.append(now)
        if len(self.timestamps) > self.window_size:
            self.timestamps.pop(0)
    
    def get_fps(self):
        """Calculate current FPS."""
        if len(self.timestamps) < 2:
            return 0.0
        elapsed = self.timestamps[-1] - self.timestamps[0]
        return (len(self.timestamps) - 1) / elapsed if elapsed > 0 else 0.0
