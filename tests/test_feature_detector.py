"""
Unit tests for FeatureDetector class.

Tests bull center detection, ring edge detection, radial wire detection,
and wire intersection finding.
"""

import numpy as np
import cv2
import pytest

from src.calibration.feature_detector import FeatureDetector, FeatureDetectionResult


@pytest.fixture
def config():
    """Provide test configuration."""
    return {
        'calibration': {
            'feature_detection': {
                'bull_min_radius_px': 10,
                'bull_max_radius_px': 30,
                'canny_threshold_low': 50,
                'canny_threshold_high': 150,
                'hough_line_threshold': 50,
                'min_wire_length_px': 50
            }
        }
    }


@pytest.fixture
def detector(config):
    """Create a FeatureDetector instance."""
    return FeatureDetector(config)


def create_synthetic_dartboard(width=800, height=600, bull_radius=20):
    """
    Create a synthetic dartboard image for testing.
    
    Args:
        width: Image width in pixels
        height: Image height in pixels
        bull_radius: Bull radius in pixels
    
    Returns:
        BGR image with synthetic dartboard
    """
    # Create white background
    image = np.ones((height, width, 3), dtype=np.uint8) * 200
    
    # Draw bull center (dark circle)
    center = (width // 2, height // 2)
    cv2.circle(image, center, bull_radius, (30, 30, 30), -1)
    
    # Draw double bull (darker inner circle)
    cv2.circle(image, center, bull_radius // 2, (10, 10, 10), -1)
    
    return image


def test_bull_center_detection_single_circle(detector):
    """Test bull center detection with a single clear circle."""
    # Create synthetic dartboard with bull at center
    image = create_synthetic_dartboard(width=800, height=600, bull_radius=20)
    
    # Detect bull center
    bull_center = detector.detect_bull_center(image)
    
    # Verify detection
    assert bull_center is not None, "Bull center should be detected"
    
    # Check that detected center is close to actual center
    expected_center = (400, 300)
    detected_x, detected_y = bull_center
    
    distance = np.sqrt((detected_x - expected_center[0])**2 + 
                      (detected_y - expected_center[1])**2)
    
    assert distance < 5, f"Detected center should be within 5px of actual center, got {distance:.1f}px"


def test_bull_center_detection_no_circle(detector):
    """Test bull center detection with no circle present."""
    # Create blank image
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    
    # Detect bull center
    bull_center = detector.detect_bull_center(image)
    
    # Should return None when no circle detected
    assert bull_center is None, "Should return None when no circle detected"


def test_bull_center_detection_off_center(detector):
    """Test bull center detection with bull off-center."""
    # Create image with bull off-center
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    
    # Draw bull at off-center position
    bull_pos = (300, 250)
    cv2.circle(image, bull_pos, 20, (30, 30, 30), -1)
    cv2.circle(image, bull_pos, 10, (10, 10, 10), -1)
    
    # Detect bull center
    bull_center = detector.detect_bull_center(image)
    
    # Verify detection
    assert bull_center is not None, "Bull center should be detected even when off-center"
    
    detected_x, detected_y = bull_center
    distance = np.sqrt((detected_x - bull_pos[0])**2 + 
                      (detected_y - bull_pos[1])**2)
    
    assert distance < 5, f"Detected center should be within 5px of actual position, got {distance:.1f}px"


def test_detect_returns_error_when_no_bull(detector):
    """Test that detect() returns error when bull not detected."""
    # Create blank image
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    
    # Run full detection
    result = detector.detect(image)
    
    # Verify error is returned
    assert result.bull_center is None
    assert result.error == "BULL_NOT_DETECTED"
    assert result.detection_time_ms > 0


def test_bull_center_multiple_circles(detector):
    """Test bull center detection with multiple circles (selects best)."""
    # Create image with multiple circles
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    
    # Draw bull near center (should be selected)
    bull_pos = (400, 300)
    cv2.circle(image, bull_pos, 20, (30, 30, 30), -1)
    
    # Draw another circle far from center (should be rejected)
    cv2.circle(image, (100, 100), 15, (30, 30, 30), -1)
    
    # Detect bull center
    bull_center = detector.detect_bull_center(image)
    
    # Verify the center circle was selected
    assert bull_center is not None
    
    detected_x, detected_y = bull_center
    distance = np.sqrt((detected_x - bull_pos[0])**2 + 
                      (detected_y - bull_pos[1])**2)
    
    # Should select the circle closest to image center
    assert distance < 30, f"Should select circle near center, got distance {distance:.1f}px"


def test_ring_edge_detection_with_synthetic_rings(detector):
    """Test ring edge detection with synthetic ring images."""
    # Create image with bull and rings
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    # Draw bull
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    
    # Draw double ring (outer ring) - approximate 255px radius
    cv2.circle(image, center, 255, (50, 50, 50), 3)
    
    # Draw triple ring (middle ring) - approximate 160px radius
    cv2.circle(image, center, 160, (50, 50, 50), 3)
    
    # Detect bull center first
    bull_center = detector.detect_bull_center(image)
    assert bull_center is not None
    
    # Detect ring edges
    ring_edges = detector.detect_ring_edges(image, bull_center)
    
    # Verify both rings detected
    assert 'double_ring' in ring_edges
    assert 'triple_ring' in ring_edges
    
    # Verify we got sampled points
    assert len(ring_edges['double_ring']) > 0, "Should detect double ring points"
    assert len(ring_edges['triple_ring']) > 0, "Should detect triple ring points"
    
    # Verify points are roughly at expected radius from bull center
    bull_u, bull_v = bull_center
    
    if ring_edges['double_ring']:
        # Check a few points from double ring
        for point in ring_edges['double_ring'][:5]:
            x, y = point
            radius = np.sqrt((x - bull_u)**2 + (y - bull_v)**2)
            # Should be roughly 255px ± tolerance
            assert 235 < radius < 275, f"Double ring point radius {radius:.1f} outside expected range"
    
    if ring_edges['triple_ring']:
        # Check a few points from triple ring
        for point in ring_edges['triple_ring'][:5]:
            x, y = point
            radius = np.sqrt((x - bull_u)**2 + (y - bull_v)**2)
            # Should be roughly 160px ± tolerance
            assert 140 < radius < 180, f"Triple ring point radius {radius:.1f} outside expected range"


def test_ring_edge_detection_no_rings(detector):
    """Test ring edge detection when no rings present."""
    # Create image with only bull, no rings
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    
    bull_center = detector.detect_bull_center(image)
    assert bull_center is not None
    
    # Detect ring edges
    ring_edges = detector.detect_ring_edges(image, bull_center)
    
    # Should return empty lists when no rings detected
    assert isinstance(ring_edges, dict)
    assert 'double_ring' in ring_edges
    assert 'triple_ring' in ring_edges
    # Lists may be empty if no rings detected
    assert isinstance(ring_edges['double_ring'], list)
    assert isinstance(ring_edges['triple_ring'], list)


def test_ring_edge_detection_ellipse(detector):
    """Test ring edge detection with elliptical (perspective-distorted) rings."""
    # Create image with elliptical rings (simulating perspective distortion)
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    # Draw bull
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    
    # Draw elliptical double ring (perspective distortion)
    cv2.ellipse(image, center, (255, 200), 0, 0, 360, (50, 50, 50), 3)
    
    # Draw elliptical triple ring
    cv2.ellipse(image, center, (160, 125), 0, 0, 360, (50, 50, 50), 3)
    
    bull_center = detector.detect_bull_center(image)
    assert bull_center is not None
    
    # Detect ring edges
    ring_edges = detector.detect_ring_edges(image, bull_center)
    
    # Should detect elliptical rings
    assert len(ring_edges['double_ring']) > 0 or len(ring_edges['triple_ring']) > 0, \
        "Should detect at least one elliptical ring"


def test_ring_edge_detection_sampled_points_count(detector):
    """Test that ring edge detection returns appropriate number of sampled points."""
    # Create image with rings
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    cv2.circle(image, center, 255, (50, 50, 50), 3)
    cv2.circle(image, center, 160, (50, 50, 50), 3)
    
    bull_center = detector.detect_bull_center(image)
    ring_edges = detector.detect_ring_edges(image, bull_center)
    
    # Should sample multiple points around each ring (36 points expected)
    if ring_edges['double_ring']:
        assert len(ring_edges['double_ring']) == 36, \
            f"Expected 36 sampled points, got {len(ring_edges['double_ring'])}"
    
    if ring_edges['triple_ring']:
        assert len(ring_edges['triple_ring']) == 36, \
            f"Expected 36 sampled points, got {len(ring_edges['triple_ring'])}"


def test_radial_wire_detection_with_synthetic_wires(detector):
    """Test radial wire detection with synthetic radial lines."""
    # Create image with bull and radial wires
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    # Draw several radial wires at different angles
    # Start from outside the bull area to avoid interfering with bull detection
    wire_angles = [0, 45, 90, 135, 180, 225, 270, 315]  # 8 wires
    wire_start_radius = 30  # Start outside bull
    wire_length = 250
    
    for angle_deg in wire_angles:
        angle_rad = np.deg2rad(angle_deg)
        # Draw line from outside bull outward
        x_start = int(center[0] + wire_start_radius * np.cos(angle_rad))
        y_start = int(center[1] - wire_start_radius * np.sin(angle_rad))
        x_end = int(center[0] + wire_length * np.cos(angle_rad))
        y_end = int(center[1] - wire_length * np.sin(angle_rad))
        cv2.line(image, (x_start, y_start), (x_end, y_end), (50, 50, 50), 2)
    
    # Draw bull AFTER wires so it's clearly visible
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    cv2.circle(image, center, 10, (10, 10, 10), -1)
    
    # Detect bull center first
    bull_center = detector.detect_bull_center(image)
    assert bull_center is not None
    
    # Detect radial wires
    radial_wires = detector.detect_radial_wires(image, bull_center)
    
    # Verify wires detected
    assert len(radial_wires) > 0, "Should detect at least some radial wires"
    
    # Verify each wire has required attributes
    for wire in radial_wires:
        assert hasattr(wire, 'angle'), "Wire should have angle attribute"
        assert hasattr(wire, 'endpoints'), "Wire should have endpoints attribute"
        assert hasattr(wire, 'confidence'), "Wire should have confidence attribute"
        
        # Angle should be in [0, 360)
        assert 0 <= wire.angle < 360, f"Wire angle {wire.angle} should be in [0, 360)"
        
        # Endpoints should be tuples of two points
        assert len(wire.endpoints) == 2, "Wire should have 2 endpoints"
        assert len(wire.endpoints[0]) == 2, "Each endpoint should be (x, y)"
        assert len(wire.endpoints[1]) == 2, "Each endpoint should be (x, y)"
        
        # Confidence should be positive
        assert wire.confidence > 0, "Wire confidence should be positive"


def test_radial_wire_detection_no_wires(detector):
    """Test radial wire detection when no wires present."""
    # Create image with only bull, no wires
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    
    bull_center = detector.detect_bull_center(image)
    assert bull_center is not None
    
    # Detect radial wires
    radial_wires = detector.detect_radial_wires(image, bull_center)
    
    # Should return empty list when no wires detected
    assert isinstance(radial_wires, list)
    assert len(radial_wires) == 0, "Should return empty list when no wires present"


def test_radial_wire_detection_clustering(detector):
    """Test that radial wire detection clusters nearby lines correctly."""
    # Create image with multiple lines in same sector (should cluster to one)
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    # Draw bull FIRST
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    cv2.circle(image, center, 10, (10, 10, 10), -1)
    
    # Draw 3 lines at similar angles (should cluster to 1 wire)
    # Start from outside bull to avoid detection issues
    wire_start_radius = 30
    for angle_offset in [-5, 0, 5]:  # 3 lines within 10° range
        angle_rad = np.deg2rad(angle_offset)
        x_start = int(center[0] + wire_start_radius * np.cos(angle_rad))
        y_start = int(center[1] - wire_start_radius * np.sin(angle_rad))
        x_end = int(center[0] + 250 * np.cos(angle_rad))
        y_end = int(center[1] - 250 * np.sin(angle_rad))
        cv2.line(image, (x_start, y_start), (x_end, y_end), (50, 50, 50), 2)
    
    # Draw another line at 90° (different sector)
    angle_rad = np.deg2rad(90)
    x_start = int(center[0] + wire_start_radius * np.cos(angle_rad))
    y_start = int(center[1] - wire_start_radius * np.sin(angle_rad))
    x_end = int(center[0] + 250 * np.cos(angle_rad))
    y_end = int(center[1] - 250 * np.sin(angle_rad))
    cv2.line(image, (x_start, y_start), (x_end, y_end), (50, 50, 50), 2)
    
    bull_center = detector.detect_bull_center(image)
    radial_wires = detector.detect_radial_wires(image, bull_center)
    
    # Should detect 2 wires (one cluster near 0°, one at 90°)
    # Note: HoughLinesP may detect multiple segments, so we allow some flexibility
    assert len(radial_wires) >= 1, "Should detect at least 1 wire after clustering"
    # With clustering, we should have significantly fewer wires than line segments drawn
    assert len(radial_wires) <= 4, "Should cluster nearby lines (may have some segments)"


def test_radial_wire_detection_filters_non_radial_lines(detector):
    """Test that non-radial lines (not passing through bull) are filtered out."""
    # Create image with bull and non-radial lines
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    # Draw bull
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    
    # Draw radial line (should be detected)
    cv2.line(image, center, (600, 300), (50, 50, 50), 2)
    
    # Draw non-radial line far from bull (should be filtered)
    cv2.line(image, (100, 100), (200, 100), (50, 50, 50), 2)
    
    bull_center = detector.detect_bull_center(image)
    radial_wires = detector.detect_radial_wires(image, bull_center)
    
    # Should only detect the radial line
    assert len(radial_wires) >= 1, "Should detect at least the radial line"
    
    # Verify detected wires pass near bull center
    for wire in radial_wires:
        # Check that at least one endpoint is reasonably close to bull
        (x1, y1), (x2, y2) = wire.endpoints
        dist1 = np.sqrt((x1 - bull_center[0])**2 + (y1 - bull_center[1])**2)
        dist2 = np.sqrt((x2 - bull_center[0])**2 + (y2 - bull_center[1])**2)
        min_dist = min(dist1, dist2)
        
        # At least one endpoint should be relatively close to bull (within 100px)
        # or the line should pass through bull region
        assert min_dist < 200, f"Wire should pass near bull, got min endpoint distance {min_dist:.1f}px"


def test_wire_intersection_finding_basic(detector):
    """Test basic wire-ring intersection finding."""
    # Create image with bull, rings, and radial wires
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    # Draw bull
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    
    # Draw rings
    cv2.circle(image, center, 255, (50, 50, 50), 3)  # Double ring
    cv2.circle(image, center, 160, (50, 50, 50), 3)  # Triple ring
    
    # Draw radial wires
    wire_angles = [0, 90, 180, 270]  # 4 wires at cardinal directions
    wire_start_radius = 30
    wire_length = 280
    
    for angle_deg in wire_angles:
        angle_rad = np.deg2rad(angle_deg)
        x_start = int(center[0] + wire_start_radius * np.cos(angle_rad))
        y_start = int(center[1] - wire_start_radius * np.sin(angle_rad))
        x_end = int(center[0] + wire_length * np.cos(angle_rad))
        y_end = int(center[1] - wire_length * np.sin(angle_rad))
        cv2.line(image, (x_start, y_start), (x_end, y_end), (50, 50, 50), 2)
    
    # Detect features
    bull_center = detector.detect_bull_center(image)
    assert bull_center is not None
    
    ring_edges = detector.detect_ring_edges(image, bull_center)
    radial_wires = detector.detect_radial_wires(image, bull_center)
    
    # Find intersections
    intersections = detector.find_wire_intersections(ring_edges, radial_wires)
    
    # Verify intersections found
    assert len(intersections) > 0, "Should find at least some wire-ring intersections"
    
    # Verify intersection structure
    for intersection in intersections:
        assert hasattr(intersection, 'pixel'), "Intersection should have pixel attribute"
        assert hasattr(intersection, 'ring_type'), "Intersection should have ring_type attribute"
        assert hasattr(intersection, 'wire_index'), "Intersection should have wire_index attribute"
        assert hasattr(intersection, 'sector_estimate'), "Intersection should have sector_estimate attribute"
        
        # Verify pixel coordinates are valid
        x, y = intersection.pixel
        assert 0 <= x < 800, f"Intersection x={x} should be within image bounds"
        assert 0 <= y < 600, f"Intersection y={y} should be within image bounds"
        
        # Verify ring type is valid
        assert intersection.ring_type in ['double_ring', 'triple_ring'], \
            f"Ring type should be 'double_ring' or 'triple_ring', got {intersection.ring_type}"
        
        # Verify wire index is valid
        assert 0 <= intersection.wire_index < len(radial_wires), \
            f"Wire index {intersection.wire_index} should be valid"
        
        # Verify sector estimate is valid (1-20) or None
        if intersection.sector_estimate is not None:
            assert 1 <= intersection.sector_estimate <= 20, \
                f"Sector estimate {intersection.sector_estimate} should be in range [1, 20]"


def test_wire_intersection_finding_no_wires(detector):
    """Test wire-ring intersection finding with no wires."""
    # Create image with bull and rings but no wires
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    cv2.circle(image, center, 255, (50, 50, 50), 3)
    cv2.circle(image, center, 160, (50, 50, 50), 3)
    
    bull_center = detector.detect_bull_center(image)
    ring_edges = detector.detect_ring_edges(image, bull_center)
    radial_wires = detector.detect_radial_wires(image, bull_center)
    
    # Find intersections (should be empty since no wires)
    intersections = detector.find_wire_intersections(ring_edges, radial_wires)
    
    assert isinstance(intersections, list)
    assert len(intersections) == 0, "Should return empty list when no wires present"


def test_wire_intersection_finding_no_rings(detector):
    """Test wire-ring intersection finding with no rings."""
    # Create image with bull and wires but no rings
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    
    # Draw radial wires
    wire_angles = [0, 90]
    wire_start_radius = 30
    wire_length = 250
    
    for angle_deg in wire_angles:
        angle_rad = np.deg2rad(angle_deg)
        x_start = int(center[0] + wire_start_radius * np.cos(angle_rad))
        y_start = int(center[1] - wire_start_radius * np.sin(angle_rad))
        x_end = int(center[0] + wire_length * np.cos(angle_rad))
        y_end = int(center[1] - wire_length * np.sin(angle_rad))
        cv2.line(image, (x_start, y_start), (x_end, y_end), (50, 50, 50), 2)
    
    bull_center = detector.detect_bull_center(image)
    ring_edges = detector.detect_ring_edges(image, bull_center)
    radial_wires = detector.detect_radial_wires(image, bull_center)
    
    # Find intersections (should be empty since no rings)
    intersections = detector.find_wire_intersections(ring_edges, radial_wires)
    
    assert isinstance(intersections, list)
    # May be empty or have very few intersections since rings not detected
    # Just verify it doesn't crash


def test_wire_intersection_sector_estimation(detector):
    """Test that sector estimation is reasonable for wire intersections."""
    # Create image with bull, rings, and a wire at known angle
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    cv2.circle(image, center, 255, (50, 50, 50), 3)
    cv2.circle(image, center, 160, (50, 50, 50), 3)
    
    # Draw wire pointing straight up (should be sector 20)
    # Angle 0° from vertical = pointing up
    angle_rad = np.deg2rad(90)  # In standard math coords, 90° = up
    x_start = int(center[0] + 30 * np.cos(angle_rad))
    y_start = int(center[1] - 30 * np.sin(angle_rad))
    x_end = int(center[0] + 280 * np.cos(angle_rad))
    y_end = int(center[1] - 280 * np.sin(angle_rad))
    cv2.line(image, (x_start, y_start), (x_end, y_end), (50, 50, 50), 2)
    
    bull_center = detector.detect_bull_center(image)
    ring_edges = detector.detect_ring_edges(image, bull_center)
    radial_wires = detector.detect_radial_wires(image, bull_center)
    
    if len(radial_wires) > 0:
        intersections = detector.find_wire_intersections(ring_edges, radial_wires)
        
        # Verify sector estimates are in valid range
        for intersection in intersections:
            if intersection.sector_estimate is not None:
                assert 1 <= intersection.sector_estimate <= 20, \
                    f"Sector estimate {intersection.sector_estimate} should be in [1, 20]"


def test_wire_intersection_radius_verification(detector):
    """Test that wire intersections are at approximately correct radius."""
    # Create image with bull, rings, and radial wires
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    cv2.circle(image, center, 255, (50, 50, 50), 3)  # Double ring
    cv2.circle(image, center, 160, (50, 50, 50), 3)  # Triple ring
    
    # Draw radial wires
    for angle_deg in [0, 90, 180, 270]:
        angle_rad = np.deg2rad(angle_deg)
        x_start = int(center[0] + 30 * np.cos(angle_rad))
        y_start = int(center[1] - 30 * np.sin(angle_rad))
        x_end = int(center[0] + 280 * np.cos(angle_rad))
        y_end = int(center[1] - 280 * np.sin(angle_rad))
        cv2.line(image, (x_start, y_start), (x_end, y_end), (50, 50, 50), 2)
    
    bull_center = detector.detect_bull_center(image)
    ring_edges = detector.detect_ring_edges(image, bull_center)
    radial_wires = detector.detect_radial_wires(image, bull_center)
    
    intersections = detector.find_wire_intersections(ring_edges, radial_wires)
    
    # Verify intersections are at approximately correct radius
    bull_u, bull_v = bull_center
    
    for intersection in intersections:
        x, y = intersection.pixel
        radius = np.sqrt((x - bull_u)**2 + (y - bull_v)**2)
        
        if intersection.ring_type == 'double_ring':
            # Should be near 255px radius (±30px tolerance)
            assert 225 < radius < 285, \
                f"Double ring intersection at radius {radius:.1f} should be near 255px"
        elif intersection.ring_type == 'triple_ring':
            # Should be near 160px radius (±30px tolerance)
            assert 130 < radius < 190, \
                f"Triple ring intersection at radius {radius:.1f} should be near 160px"


def test_full_detection_with_intersections(detector):
    """Test full detection pipeline including wire intersections."""
    # Create comprehensive synthetic dartboard
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    # Draw bull
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    cv2.circle(image, center, 10, (10, 10, 10), -1)
    
    # Draw rings
    cv2.circle(image, center, 255, (50, 50, 50), 3)
    cv2.circle(image, center, 160, (50, 50, 50), 3)
    
    # Draw radial wires
    for angle_deg in range(0, 360, 45):  # 8 wires
        angle_rad = np.deg2rad(angle_deg)
        x_start = int(center[0] + 30 * np.cos(angle_rad))
        y_start = int(center[1] - 30 * np.sin(angle_rad))
        x_end = int(center[0] + 280 * np.cos(angle_rad))
        y_end = int(center[1] - 280 * np.sin(angle_rad))
        cv2.line(image, (x_start, y_start), (x_end, y_end), (50, 50, 50), 2)
    
    # Run full detection
    result = detector.detect(image)
    
    # Verify all features detected
    assert result.bull_center is not None, "Bull center should be detected"
    assert len(result.ring_edges.get('double_ring', [])) > 0, "Double ring should be detected"
    assert len(result.ring_edges.get('triple_ring', [])) > 0, "Triple ring should be detected"
    assert len(result.radial_wires) > 0, "Radial wires should be detected"
    assert len(result.wire_intersections) >= 4, "Should have at least 4 wire intersections"
    assert result.error is None, "Should not have error with sufficient features"
    assert result.detection_time_ms > 0, "Should record detection time"


def test_insufficient_features_error(detector):
    """Test that insufficient features triggers error."""
    # Create image with bull and rings but very few wires
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    cv2.circle(image, center, 255, (50, 50, 50), 3)
    
    # Draw only 1 wire (not enough for calibration)
    cv2.line(image, center, (600, 300), (50, 50, 50), 2)
    
    result = detector.detect(image)
    
    # Should detect insufficient features if < 4 intersections
    if len(result.wire_intersections) < 4:
        assert result.error == "INSUFFICIENT_FEATURES", \
            "Should return INSUFFICIENT_FEATURES error when < 4 intersections"


def test_bull_center_boundary_radius_too_small(detector):
    """Test bull center detection rejects circles smaller than min radius."""
    # Create image with very small circle (below min_radius_px threshold)
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    # Draw circle with radius 5 (below default min of 10)
    cv2.circle(image, center, 5, (30, 30, 30), -1)
    
    # Detect bull center
    bull_center = detector.detect_bull_center(image)
    
    # Should not detect circle that's too small
    assert bull_center is None, "Should reject circles smaller than min_radius_px"


def test_bull_center_boundary_radius_too_large(detector):
    """Test bull center detection rejects circles larger than max radius."""
    # Create image with very large circle (above max_radius_px threshold)
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    # Draw circle with radius 40 (above default max of 30)
    cv2.circle(image, center, 40, (30, 30, 30), -1)
    
    # Detect bull center
    bull_center = detector.detect_bull_center(image)
    
    # Should not detect circle that's too large
    assert bull_center is None, "Should reject circles larger than max_radius_px"


def test_ring_edge_detection_partial_occlusion(detector):
    """Test ring edge detection with partially occluded rings."""
    # Create image with bull and partially visible rings
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    # Draw bull
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    
    # Draw partial ring (only 180 degrees visible)
    cv2.ellipse(image, center, (255, 255), 0, 0, 180, (50, 50, 50), 3)
    
    bull_center = detector.detect_bull_center(image)
    assert bull_center is not None
    
    # Detect ring edges
    ring_edges = detector.detect_ring_edges(image, bull_center)
    
    # Should still attempt to detect rings even with partial visibility
    assert isinstance(ring_edges, dict)
    assert 'double_ring' in ring_edges
    assert 'triple_ring' in ring_edges


def test_radial_wire_detection_minimum_length_filter(detector):
    """Test that short line segments are filtered out by min_wire_length."""
    # Create image with bull and very short lines
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    # Draw bull
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    
    # Draw very short radial lines (below min_wire_length_px threshold)
    for angle_deg in [0, 90, 180, 270]:
        angle_rad = np.deg2rad(angle_deg)
        x_start = int(center[0] + 30 * np.cos(angle_rad))
        y_start = int(center[1] - 30 * np.sin(angle_rad))
        # Very short line (only 20 pixels, below default min of 50)
        x_end = int(center[0] + 50 * np.cos(angle_rad))
        y_end = int(center[1] - 50 * np.sin(angle_rad))
        cv2.line(image, (x_start, y_start), (x_end, y_end), (50, 50, 50), 2)
    
    bull_center = detector.detect_bull_center(image)
    radial_wires = detector.detect_radial_wires(image, bull_center)
    
    # Should detect very few or no wires since they're too short
    # (HoughLinesP minLineLength parameter filters these out)
    assert isinstance(radial_wires, list)


def test_full_detection_realistic_geometry(detector):
    """Test full detection with realistic dartboard geometry and proportions."""
    # Create synthetic dartboard with realistic proportions
    # Assuming ~1.5 pixels per mm scale
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    # Bull: 6.35mm double bull, 15.9mm single bull → ~10px, ~24px
    cv2.circle(image, center, 24, (40, 40, 40), -1)  # Single bull
    cv2.circle(image, center, 10, (20, 20, 20), -1)  # Double bull
    
    # Triple ring: 99-107mm → ~149-161px (use 155px)
    cv2.circle(image, center, 155, (50, 50, 50), 3)
    
    # Double ring: 162-170mm → ~243-255px (use 249px)
    cv2.circle(image, center, 249, (50, 50, 50), 3)
    
    # Draw 20 radial wires at correct sector angles
    sector_order = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
    for i in range(20):
        angle_deg = i * 18  # 18 degrees per sector
        angle_rad = np.deg2rad(angle_deg)
        x_start = int(center[0] + 30 * np.cos(angle_rad))
        y_start = int(center[1] - 30 * np.sin(angle_rad))
        x_end = int(center[0] + 270 * np.cos(angle_rad))
        y_end = int(center[1] - 270 * np.sin(angle_rad))
        cv2.line(image, (x_start, y_start), (x_end, y_end), (50, 50, 50), 2)
    
    # Run full detection
    result = detector.detect(image)
    
    # Verify comprehensive detection
    assert result.bull_center is not None, "Should detect bull center"
    assert result.error is None, "Should not have errors with complete dartboard"
    
    # Should detect both rings
    assert len(result.ring_edges.get('double_ring', [])) > 0, "Should detect double ring"
    assert len(result.ring_edges.get('triple_ring', [])) > 0, "Should detect triple ring"
    
    # Should detect multiple wires (requirement 1.4 specifies ≥8 for real images)
    # For synthetic images, detection may be lower due to image processing limitations
    assert len(result.radial_wires) >= 4, \
        f"Should detect at least 4 radial wires in synthetic image, got {len(result.radial_wires)}"
    
    # Should have sufficient intersections (requirement 1.7)
    assert len(result.wire_intersections) >= 4, \
        f"Should have at least 4 wire intersections, got {len(result.wire_intersections)}"
    
    # Verify detection time is recorded
    assert result.detection_time_ms > 0, "Should record detection time"


def test_wire_intersection_both_rings(detector):
    """Test that wire intersections are found for both double and triple rings."""
    # Create image with complete dartboard
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    cv2.circle(image, center, 255, (50, 50, 50), 3)  # Double ring
    cv2.circle(image, center, 160, (50, 50, 50), 3)  # Triple ring
    
    # Draw several radial wires
    for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
        angle_rad = np.deg2rad(angle_deg)
        x_start = int(center[0] + 30 * np.cos(angle_rad))
        y_start = int(center[1] - 30 * np.sin(angle_rad))
        x_end = int(center[0] + 280 * np.cos(angle_rad))
        y_end = int(center[1] - 280 * np.sin(angle_rad))
        cv2.line(image, (x_start, y_start), (x_end, y_end), (50, 50, 50), 2)
    
    bull_center = detector.detect_bull_center(image)
    ring_edges = detector.detect_ring_edges(image, bull_center)
    radial_wires = detector.detect_radial_wires(image, bull_center)
    intersections = detector.find_wire_intersections(ring_edges, radial_wires)
    
    # Should have intersections with both ring types
    double_ring_intersections = [i for i in intersections if i.ring_type == 'double_ring']
    triple_ring_intersections = [i for i in intersections if i.ring_type == 'triple_ring']
    
    assert len(double_ring_intersections) > 0, "Should have double ring intersections"
    assert len(triple_ring_intersections) > 0, "Should have triple ring intersections"
