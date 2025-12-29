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
        
        # Spatial mask to exclude board features (created on first detection)
        self.board_mask = None
    
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
        
        # Add edge detection to catch metallic darts (low contrast in diff)
        edges = cv2.Canny(post_gray, 50, 150)
        
        # Threshold
        _, thresh = cv2.threshold(diff, self.diff_threshold, 255, cv2.THRESH_BINARY)
        
        # Combine diff-based and edge-based detection
        thresh = cv2.bitwise_or(thresh, edges)
        
        # Morphological operations to remove small noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)  # Remove small white noise
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)  # Fill small holes
        
        # Create spatial mask on first use (exclude outer numbers only)
        if self.board_mask is None:
            h, w = thresh.shape
            center = (w // 2, h // 2)
            # Create mask: white = valid area, black = excluded
            self.board_mask = np.zeros((h, w), dtype=np.uint8)
            # Valid area: inside the double ring (approximately 85% of image radius)
            valid_radius = int(min(w, h) * 0.42)  # 84% of half-width
            cv2.circle(self.board_mask, center, valid_radius, 255, -1)
            # Bull is included (no inner exclusion)
            self.logger.info(f"Created board mask: valid_radius={valid_radius} (excludes outer numbers only)")
        
        # Apply spatial mask to exclude board features
        thresh = cv2.bitwise_and(thresh, thresh, mask=self.board_mask)
        
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
            
            # Enhanced filters: circularity and solidity
            perimeter = cv2.arcLength(contour, True)
            if perimeter == 0:
                continue
            
            # Circularity: 1.0 = perfect circle, 0.0 = line
            # Dart should be elongated (low circularity)
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            if circularity > 0.7:  # Relaxed from 0.5 - allow more circular shapes
                self.logger.debug(f"Rejected: too circular ({circularity:.2f})")
                continue
            
            # Solidity: ratio of contour area to convex hull area
            # Dart should be solid (high solidity), wires are hollow (low solidity)
            hull = cv2.convexHull(contour)
            hull_area = cv2.contourArea(hull)
            if hull_area == 0:
                continue
            solidity = area / hull_area
            if solidity < 0.5:  # Relaxed from 0.7 - allow more irregular shapes
                self.logger.debug(f"Rejected: too hollow (solidity={solidity:.2f})")
                continue
            
            dart_candidates.append({
                'contour': contour,
                'area': area,
                'bbox': (x, y, w, h),
                'aspect_ratio': aspect_ratio,
                'circularity': circularity,
                'solidity': solidity
            })
            self.logger.info(f"Dart candidate: area={area:.0f}, bbox={w}x{h}, aspect={aspect_ratio:.1f}, circ={circularity:.2f}, solid={solidity:.2f}")
        
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
        Find dart tip using contour taper analysis.
        Tip = narrow end (tapers to point)
        Flight = wide end (bulky)
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
        
        # Measure contour width at both ends (taper analysis)
        # Tip is narrow, flight is wide
        width1 = self._measure_contour_width(contour_points, end1)
        width2 = self._measure_contour_width(contour_points, end2)
        
        # Tip is the narrower end
        if width1 < width2:
            tip = end1
            confidence = (width2 - width1) / max(width2, 1)
        else:
            tip = end2
            confidence = (width1 - width2) / max(width1, 1)
        
        # Clamp confidence to [0, 1]
        confidence = min(max(confidence, 0.0), 1.0)
        
        self.logger.debug(f"Tip at {tip}, confidence: {confidence:.2f}, widths: {width1:.1f}, {width2:.1f}")
        
        return tip[0], tip[1], confidence
    
    def _measure_contour_width(self, contour_points, endpoint):
        """
        Measure contour width near an endpoint.
        Returns average distance of nearby contour points from the endpoint.
        """
        endpoint = np.array(endpoint)
        
        # Find points within 20 pixels of endpoint
        distances = np.linalg.norm(contour_points - endpoint, axis=1)
        nearby_mask = distances < 20
        
        if not np.any(nearby_mask):
            return 0.0
        
        nearby_points = contour_points[nearby_mask]
        
        # Measure spread of nearby points (width)
        if len(nearby_points) < 2:
            return 0.0
        
        # Use standard deviation as width measure
        width = np.std(nearby_points, axis=0).mean()
        
        return float(width)
