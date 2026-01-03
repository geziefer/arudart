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
        
        # Add edge detection to catch metallic darts and flight outlines
        edges = cv2.Canny(post_gray, 50, 150)
        
        # Threshold
        _, thresh = cv2.threshold(diff, self.diff_threshold, 255, cv2.THRESH_BINARY)
        
        # Combine diff-based and edge-based detection
        thresh = cv2.bitwise_or(thresh, edges)
        
        # Morphological operations to remove small noise and bridge gaps
        # Use smaller opening to preserve thin tip, but still remove scattered noise
        kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_small)  # Remove small noise while preserving tip
        
        # Use progressively larger kernels for closing to bridge gaps and fill flight interior
        # This handles flights with irregular shapes, gaps, or holes
        kernel_medium = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_medium)  # Fill medium gaps
        
        kernel_large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_large)  # Fill large gaps in flight
        
        kernel_xlarge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_xlarge)  # Connect fragmented flight pieces
        
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
        
        # Take best candidate: prefer elongated shapes (high aspect ratio) over just large area
        # This helps when flight fragments into multiple contours
        dart = max(dart_candidates, key=lambda c: c['aspect_ratio'] * (c['area'] ** 0.5))
        
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
        Find dart tip by identifying the flight (widest part) and taking the opposite end.
        Flight = widest, most bulky part
        Tip = opposite end from flight
        """
        # Fit line to contour
        [vx, vy, x0, y0] = cv2.fitLine(contour, cv2.DIST_L2, 0, 0.01, 0.01)
        
        # Get contour extent
        contour_points = contour.reshape(-1, 2)
        
        # Project all points onto the fitted line to find endpoints
        t_values = []
        for point in contour_points:
            t = (point[0] - x0) * vx + (point[1] - y0) * vy
            t_values.append(t)
        
        t_min = min(t_values)
        t_max = max(t_values)
        t_values = np.array(t_values)
        
        # Find the widest part of the dart (the flight)
        # Divide dart into segments and measure width of each
        dart_length = t_max - t_min
        num_segments = 10
        segment_size = dart_length / num_segments
        
        max_width = 0
        flight_position = 0  # 0 = near end1, 1 = near end2
        
        for i in range(num_segments):
            segment_start = t_min + i * segment_size
            segment_end = segment_start + segment_size
            segment_mask = (t_values >= segment_start) & (t_values < segment_end)
            
            if np.sum(segment_mask) < 2:
                continue
            
            # Index using the 1D mask (contour_points is Nx2, mask is N)
            segment_points = contour_points[segment_mask.flatten()]
            # Width = standard deviation of points in this segment
            width = np.std(segment_points, axis=0).mean()
            
            if width > max_width:
                max_width = width
                flight_position = i / num_segments  # 0 to 1
        
        # Calculate endpoints
        end1 = (int(x0 + t_min * vx), int(y0 + t_min * vy))
        end2 = (int(x0 + t_max * vx), int(y0 + t_max * vy))
        
        # Tip is the end opposite to the flight
        if flight_position < 0.5:
            # Flight is near end1, so tip is end2
            tip = end2
        else:
            # Flight is near end2, so tip is end1
            tip = end1
        
        # Confidence based on how distinct the flight is
        confidence = min(max_width / 20.0, 1.0)  # Normalize by expected flight width
        
        self.logger.debug(f"Flight at position {flight_position:.2f}, max_width={max_width:.1f}, tip at {tip}")
        
        return tip[0], tip[1], confidence
    
    def _measure_contour_width(self, contour_points, endpoint):
        """
        Measure contour width near an endpoint.
        Returns average distance of nearby contour points from the endpoint.
        """
        endpoint = np.array(endpoint)
        
        # Find points within 10 pixels of endpoint (reduced from 20 for more localized measurement)
        distances = np.linalg.norm(contour_points - endpoint, axis=1)
        nearby_mask = distances < 10
        
        if not np.any(nearby_mask):
            return 0.0
        
        nearby_points = contour_points[nearby_mask]
        
        # Measure spread of nearby points (width)
        if len(nearby_points) < 2:
            return 0.0
        
        # Use standard deviation as width measure
        width = np.std(nearby_points, axis=0).mean()
        
        return float(width)
