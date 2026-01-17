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
        
        # Mask for previously detected darts (for multi-dart scenarios)
        self.previous_darts_mask = None
    
    def reset_previous_darts(self):
        """Reset the mask of previously detected darts (call when starting new round)."""
        self.previous_darts_mask = None
        self.logger.info("Reset previous darts mask")
    
    def detect(self, pre_frame, post_frame, mask_previous=True):
        """
        Detect dart in post_frame compared to pre_frame.
        
        Args:
            pre_frame: Frame before dart
            post_frame: Frame after dart
            mask_previous: If True, mask out previously detected darts
            
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
        # Increased kernel sizes to bridge larger gaps between flight and shaft
        kernel_medium = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_medium)
        
        kernel_large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_large)
        
        kernel_xlarge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (27, 27))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_xlarge)
        
        kernel_xxlarge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (35, 35))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_xxlarge)  # Bridge large gaps between flight and shaft
        
        # Create spatial mask on first use (exclude outer numbers only)
        if self.board_mask is None:
            h, w = thresh.shape
            center = (w // 2, h // 2)
            # Create mask: white = valid area, black = excluded
            self.board_mask = np.zeros((h, w), dtype=np.uint8)
            # Valid area: include entire board except far outer edge (numbers)
            # Use 85% of image radius to include all scoring areas
            valid_radius = int(min(w, h) * 0.425)  # 85% of half-width
            cv2.circle(self.board_mask, center, valid_radius, 255, -1)
            # Bull is included (no inner exclusion)
            self.logger.info(f"Created board mask: valid_radius={valid_radius} (excludes outer numbers only)")
        
        # Apply spatial mask to exclude board features
        thresh = cv2.bitwise_and(thresh, thresh, mask=self.board_mask)
        
        # Apply previous darts mask if enabled and available
        if mask_previous and self.previous_darts_mask is not None:
            thresh = cv2.bitwise_and(thresh, thresh, mask=cv2.bitwise_not(self.previous_darts_mask))
            self.logger.debug("Applied previous darts mask")
        
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
        
        # Score candidates: prioritize elongated, non-circular shapes
        # Score = area * aspect_ratio * (1 - circularity)
        # This heavily favors dart-like shapes (elongated, low circularity) over board blobs (compact, circular)
        for candidate in dart_candidates:
            candidate['score'] = (
                candidate['area'] * 
                candidate['aspect_ratio'] * 
                (1.0 - candidate['circularity'])
            )
            self.logger.info(f"  Score: {candidate['score']:.1f} (area={candidate['area']:.0f} * aspect={candidate['aspect_ratio']:.1f} * (1-circ={1-candidate['circularity']:.2f}))")
        
        # Take best candidate by score (not just largest area)
        dart = max(dart_candidates, key=lambda c: c['score'])
        
        # Fit line to contour to find orientation
        tip_x, tip_y, confidence = self._find_tip(dart['contour'], thresh, post_frame.shape)
        
        # If confidence is low or contour is suspiciously short, try multi-blob analysis
        # This handles cases where flight and shaft are disconnected
        x, y, w, h = dart['bbox']
        dart_length = max(w, h)
        
        # Always try multi-blob if we have multiple candidates (disconnected flight/shaft)
        if len(dart_candidates) > 1 and (confidence < 0.5 or dart_length < 60):
            self.logger.info(f"Multiple candidates ({len(dart_candidates)}), confidence={confidence:.2f}, length={dart_length}px - trying multi-blob analysis...")
            multi_tip_x, multi_tip_y, multi_conf = self._multi_blob_analysis(dart_candidates, thresh)
            
            if multi_tip_x is not None and multi_conf > confidence:
                self.logger.info(f"Multi-blob analysis improved: {confidence:.2f} -> {multi_conf:.2f}")
                tip_x, tip_y, confidence = multi_tip_x, multi_tip_y, multi_conf
        
        # Add detected dart to previous darts mask (for multi-dart scenarios)
        if mask_previous:
            self._add_to_previous_darts_mask(dart['contour'], thresh.shape)
        
        debug_info = {
            'diff': diff,
            'thresh': thresh,
            'contour': dart['contour'],
            'bbox': dart['bbox'],
            'area': dart['area'],
            'aspect_ratio': dart['aspect_ratio']
        }
        
        return tip_x, tip_y, confidence, debug_info
    
    def _multi_blob_analysis(self, candidates, thresh):
        """Analyze multiple blobs to find aligned dart parts (flight + shaft).
        
        Returns tip coordinates and confidence if successful, otherwise (None, None, 0.0).
        """
        if len(candidates) < 2:
            return None, None, 0.0
        
        # Sort by score (best first)
        sorted_candidates = sorted(candidates, key=lambda c: c['score'], reverse=True)
        
        # Take top 2-3 candidates (likely flight + shaft)
        top_blobs = sorted_candidates[:min(3, len(sorted_candidates))]
        
        # Find centroids and orientations
        blob_info = []
        for blob in top_blobs:
            M = cv2.moments(blob['contour'])
            if M['m00'] == 0:
                continue
            cx = int(M['m10'] / M['m00'])
            cy = int(M['m01'] / M['m00'])
            
            # Fit line to get orientation
            [vx, vy, x0, y0] = cv2.fitLine(blob['contour'], cv2.DIST_L2, 0, 0.01, 0.01)
            angle = np.arctan2(vy, vx) * 180 / np.pi
            
            blob_info.append({
                'centroid': (cx, cy),
                'angle': angle,
                'contour': blob['contour'],
                'bbox': blob['bbox']
            })
        
        # Check if blobs are aligned (similar orientation)
        if len(blob_info) >= 2:
            angle_diff = float(abs(blob_info[0]['angle'] - blob_info[1]['angle']))
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            
            if angle_diff < 30:  # Aligned within 30 degrees
                # Find furthest points from both blobs
                all_points = np.vstack([b['contour'].reshape(-1, 2) for b in blob_info])
                
                # Find two furthest points (likely tip and flight end)
                max_dist = 0
                tip_point = None
                far_point = None
                
                for i, p1 in enumerate(all_points):
                    for p2 in all_points[i+1:]:
                        dist = np.linalg.norm(p1 - p2)
                        if dist > max_dist:
                            max_dist = dist
                            tip_point = p1
                            far_point = p2
                
                if tip_point is not None:
                    # Use Y-coordinate heuristic: tip has larger Y (embedded in board)
                    if tip_point[1] > far_point[1]:  # tip_point has larger Y
                        tip_x, tip_y = int(tip_point[0]), int(tip_point[1])
                    else:  # far_point has larger Y
                        tip_x, tip_y = int(far_point[0]), int(far_point[1])
                    
                    confidence = min(max_dist / 100.0, 1.0)
                    self.logger.info(f"Multi-blob: aligned blobs (angle_diff={angle_diff:.1f}°, length={max_dist:.0f}px), Y-coordinate heuristic")
                    return tip_x, tip_y, confidence
        
        return None, None, 0.0
    
    def _add_to_previous_darts_mask(self, contour, image_shape):
        """Add detected dart contour to the mask of previous darts."""
        h, w = image_shape
        
        # Create mask for this dart (dilate to cover shadows/reflections)
        dart_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(dart_mask, [contour], -1, 255, -1)  # Fill contour
        
        # Dilate to cover shadows and reflections around the dart
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
        dart_mask = cv2.dilate(dart_mask, kernel)
        
        # Add to cumulative mask
        if self.previous_darts_mask is None:
            self.previous_darts_mask = dart_mask
        else:
            self.previous_darts_mask = cv2.bitwise_or(self.previous_darts_mask, dart_mask)
        
        self.logger.info("Added detected dart to previous darts mask")
    
    def _find_tip(self, contour, thresh_image, image_shape):
        """
        Find dart tip using Y-coordinate heuristic (primary) and widest-part (fallback).
        
        Primary: Tip has larger Y coordinate than flight (tip embedded, flight sticks out)
        Fallback: Widest part = flight, opposite end = tip
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
        
        # Calculate endpoints
        end1 = (int(x0 + t_min * vx), int(y0 + t_min * vy))
        end2 = (int(x0 + t_max * vx), int(y0 + t_max * vy))
        
        # PRIMARY METHOD: Y-coordinate heuristic
        # Tip has larger Y (lower in image, embedded in board)
        # Flight has smaller Y (higher in image, sticks out from board)
        if end1[1] > end2[1]:  # end1 has larger Y
            tip = end1
            confidence = 0.8  # High confidence for Y-coordinate method
            self.logger.debug(f"Y-coordinate: end1_y={end1[1]} > end2_y={end2[1]}, tip=end1")
        else:  # end2 has larger Y
            tip = end2
            confidence = 0.8
            self.logger.debug(f"Y-coordinate: end2_y={end2[1]} > end1_y={end1[1]}, tip=end2")
        
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
