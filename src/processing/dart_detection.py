import cv2
import numpy as np
import logging


class DartDetector:
    """Detect dart tip in frame via image differencing."""
    
    def __init__(self, diff_threshold=30, blur_kernel=5, min_dart_area=100, 
                 max_dart_area=5000, min_shaft_length=30, aspect_ratio_min=2.0):
        self.diff_threshold = diff_threshold
        self.blur_kernel = blur_kernel
        self.min_dart_area = min_dart_area
        self.max_dart_area = max_dart_area
        self.min_shaft_length = min_shaft_length
        self.aspect_ratio_min = aspect_ratio_min
        self.logger = logging.getLogger('arudart.dart_detector')
    
    def detect(self, pre_frame, post_frame):
        """
        Detect dart in post_frame compared to pre_frame.
        Returns: (tip_x, tip_y, confidence, debug_info)
        """
        if pre_frame is None or post_frame is None:
            return None, None, 0.0, None
        
        # Convert to grayscale
        pre_gray = cv2.cvtColor(pre_frame, cv2.COLOR_BGR2GRAY)
        post_gray = cv2.cvtColor(post_frame, cv2.COLOR_BGR2GRAY)
        
        # Compute absolute difference
        diff = cv2.absdiff(pre_gray, post_gray)
        
        # Apply Gaussian blur to reduce noise
        if self.blur_kernel > 0:
            diff = cv2.GaussianBlur(diff, (self.blur_kernel, self.blur_kernel), 0)
        
        # Threshold
        _, thresh = cv2.threshold(diff, self.diff_threshold, 255, cv2.THRESH_BINARY)
        
        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        self.logger.info(f"Found {len(contours)} contours in diff image")
        
        if not contours:
            self.logger.debug("No contours found")
            return None, None, 0.0, {'diff': diff, 'thresh': thresh}
        
        # Filter contours for dart-like shapes
        dart_candidates = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_dart_area or area > self.max_dart_area:
                continue
            
            # Check aspect ratio (elongated shape)
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = max(h, w) / max(min(h, w), 1)
            
            if aspect_ratio < self.aspect_ratio_min:
                continue
            
            # Check minimum length
            if max(h, w) < self.min_shaft_length:
                continue
            
            dart_candidates.append({
                'contour': contour,
                'area': area,
                'bbox': (x, y, w, h),
                'aspect_ratio': aspect_ratio
            })
            self.logger.info(f"Dart candidate: area={area:.0f}, bbox={w}x{h}, aspect={aspect_ratio:.1f}")
        
        if not dart_candidates:
            self.logger.info(f"No dart-like contours found (checked {len(contours)} contours)")
            return None, None, 0.0, {'diff': diff, 'thresh': thresh}
        
        # Take largest candidate (most likely the dart)
        dart = max(dart_candidates, key=lambda c: c['area'])
        
        # Fit line to contour to find orientation
        tip_x, tip_y, confidence = self._find_tip(dart['contour'], thresh, post_frame.shape)
        
        debug_info = {
            'diff': diff,
            'thresh': thresh,
            'contour': dart['contour'],
            'bbox': dart['bbox'],
            'area': dart['area'],
            'aspect_ratio': dart['aspect_ratio']
        }
        
        return tip_x, tip_y, confidence, debug_info
    
    def _find_tip(self, contour, thresh_image, image_shape):
        """
        Find dart tip using contour endpoint analysis.
        Tip = end with weaker contour (embedded in board)
        Flight = end with stronger contour (visible, sticking out)
        """
        # Fit line to contour
        [vx, vy, x0, y0] = cv2.fitLine(contour, cv2.DIST_L2, 0, 0.01, 0.01)
        
        # Get contour extent
        contour_points = contour.reshape(-1, 2)
        
        # Project all points onto the fitted line to find endpoints
        # Line parameter t: point = (x0, y0) + t * (vx, vy)
        t_values = []
        for point in contour_points:
            # t = dot(point - (x0,y0), (vx,vy))
            t = (point[0] - x0) * vx + (point[1] - y0) * vy
            t_values.append(t)
        
        t_min = min(t_values)
        t_max = max(t_values)
        
        # Calculate endpoints
        end1 = (int(x0 + t_min * vx), int(y0 + t_min * vy))
        end2 = (int(x0 + t_max * vx), int(y0 + t_max * vy))
        
        # Measure contour strength at both ends
        # Tip (embedded) has weaker/thinner contour
        # Flight (visible) has stronger contour
        strength1 = self._measure_endpoint_strength(end1, thresh_image)
        strength2 = self._measure_endpoint_strength(end2, thresh_image)
        
        # Tip is the end with LOWER strength
        if strength1 < strength2:
            tip = end1
            confidence = (strength2 - strength1) / max(strength2, 1)
        else:
            tip = end2
            confidence = (strength1 - strength2) / max(strength1, 1)
        
        # Clamp confidence to [0, 1]
        confidence = min(max(confidence, 0.0), 1.0)
        
        self.logger.debug(f"Tip at {tip}, confidence: {confidence:.2f}, strengths: {strength1:.1f}, {strength2:.1f}")
        
        return tip[0], tip[1], confidence
    
    def _measure_endpoint_strength(self, point, thresh_image):
        """
        Measure contour strength around an endpoint.
        Higher value = stronger/more visible (flight end)
        Lower value = weaker/embedded (tip end)
        """
        x, y = point
        h, w = thresh_image.shape
        
        # Sample region around endpoint
        radius = 10
        x1 = max(0, x - radius)
        x2 = min(w, x + radius)
        y1 = max(0, y - radius)
        y2 = min(h, y + radius)
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        region = thresh_image[y1:y2, x1:x2]
        
        # Strength = sum of white pixels (contour intensity)
        strength = np.sum(region > 0)
        
        return float(strength)
