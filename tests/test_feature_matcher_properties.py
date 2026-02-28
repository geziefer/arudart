"""
Property-based tests for FeatureMatcher class using Hypothesis.

These tests verify universal properties that should hold across all valid inputs.
"""

import numpy as np
import pytest
from hypothesis import given, strategies as st, settings

from src.calibration.feature_detector import FeatureDetectionResult, RadialWire, WireIntersection
from src.calibration.feature_matcher import FeatureMatcher


def get_test_config():
    """Get test configuration."""
    return {
        'calibration': {
            'feature_detection': {
                'bull_min_radius_px': 10,
                'bull_max_radius_px': 30,
            }
        }
    }


def create_matcher():
    """Create a FeatureMatcher instance."""
    return FeatureMatcher(get_test_config())


# Strategy for generating valid pixel coordinates
pixel_coordinates = st.tuples(
    st.floats(min_value=0.0, max_value=1920.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=1080.0, allow_nan=False, allow_infinity=False)
)


# Feature: step-6-coordinate-mapping, Property 1: Bull Center Maps to Origin
@settings(max_examples=100)
@given(bull_center=pixel_coordinates)
def test_property_bull_center_maps_to_origin(bull_center):
    """
    Property 1: Bull Center Maps to Origin
    
    For any detected bull center pixel coordinate (u, v), when matched by the
    Feature_Matcher, the resulting board coordinate should be (0, 0).
    
    Validates: Requirements 2.1
    """
    matcher = create_matcher()
    
    # Create detection result with only bull center
    detection_result = FeatureDetectionResult(
        bull_center=bull_center,
        ring_edges={},
        radial_wires=[],
        wire_intersections=[],
        detection_time_ms=10.0,
        error=None
    )
    
    # Match features
    point_pairs = matcher.match(detection_result)
    
    # Property: Bull center should always map to (0, 0)
    assert len(point_pairs) >= 1, "Should have at least one point pair (bull center)"
    
    # First point pair should be the bull center
    bull_pair = point_pairs[0]
    assert bull_pair.pixel == bull_center, "First point should be bull center"
    assert bull_pair.board == (0.0, 0.0), \
        f"Bull center at {bull_center} should map to (0, 0), got {bull_pair.board}"


# Feature: step-6-coordinate-mapping, Property 2: Ring Points Map to Correct Radius
@settings(max_examples=100)
@given(
    bull_center=pixel_coordinates,
    angle=st.floats(min_value=0.0, max_value=360.0, allow_nan=False, allow_infinity=False),
    pixel_radius=st.floats(min_value=50.0, max_value=200.0, allow_nan=False, allow_infinity=False)
)
def test_property_double_ring_points_map_to_170mm_radius(bull_center, angle, pixel_radius):
    """
    Property 2: Ring Points Map to Correct Radius (Double Ring)
    
    For any point detected on the double ring edge, the matched board coordinate
    should have radius 170mm (±1mm).
    
    Validates: Requirements 2.2
    """
    matcher = create_matcher()
    bull_u, bull_v = bull_center
    
    # Generate a point on the double ring at the given angle
    angle_rad = np.deg2rad(angle)
    ring_point_u = bull_u + pixel_radius * np.cos(angle_rad)
    ring_point_v = bull_v + pixel_radius * np.sin(angle_rad)
    
    # Create detection result with bull center and double ring point
    detection_result = FeatureDetectionResult(
        bull_center=bull_center,
        ring_edges={'double_ring': [(ring_point_u, ring_point_v)]},
        radial_wires=[],
        wire_intersections=[],
        detection_time_ms=10.0,
        error=None
    )
    
    # Match features
    point_pairs = matcher.match(detection_result)
    
    # Property: Double ring points should map to 170mm radius (±1mm)
    assert len(point_pairs) >= 2, "Should have bull center + ring point"
    
    # Second point should be the ring point
    ring_pair = point_pairs[1]
    x, y = ring_pair.board
    radius = np.sqrt(x**2 + y**2)
    
    assert abs(radius - 170.0) <= 1.0, \
        f"Double ring point should map to 170mm radius (±1mm), got {radius:.2f}mm"


@settings(max_examples=100)
@given(
    bull_center=pixel_coordinates,
    angle=st.floats(min_value=0.0, max_value=360.0, allow_nan=False, allow_infinity=False),
    pixel_radius=st.floats(min_value=30.0, max_value=150.0, allow_nan=False, allow_infinity=False)
)
def test_property_triple_ring_points_map_to_107mm_radius(bull_center, angle, pixel_radius):
    """
    Property 2: Ring Points Map to Correct Radius (Triple Ring)
    
    For any point detected on the triple ring edge, the matched board coordinate
    should have radius 107mm (±1mm).
    
    Validates: Requirements 2.3
    """
    matcher = create_matcher()
    bull_u, bull_v = bull_center
    
    # Generate a point on the triple ring at the given angle
    angle_rad = np.deg2rad(angle)
    ring_point_u = bull_u + pixel_radius * np.cos(angle_rad)
    ring_point_v = bull_v + pixel_radius * np.sin(angle_rad)
    
    # Create detection result with bull center and triple ring point
    detection_result = FeatureDetectionResult(
        bull_center=bull_center,
        ring_edges={'triple_ring': [(ring_point_u, ring_point_v)]},
        radial_wires=[],
        wire_intersections=[],
        detection_time_ms=10.0,
        error=None
    )
    
    # Match features
    point_pairs = matcher.match(detection_result)
    
    # Property: Triple ring points should map to 107mm radius (±1mm)
    assert len(point_pairs) >= 2, "Should have bull center + ring point"
    
    # Second point should be the ring point
    ring_pair = point_pairs[1]
    x, y = ring_pair.board
    radius = np.sqrt(x**2 + y**2)
    
    assert abs(radius - 107.0) <= 1.0, \
        f"Triple ring point should map to 107mm radius (±1mm), got {radius:.2f}mm"


@settings(max_examples=100)
@given(
    bull_center=pixel_coordinates,
    num_double_points=st.integers(min_value=1, max_value=10),
    num_triple_points=st.integers(min_value=1, max_value=10),
    seed=st.integers(min_value=0, max_value=10000)
)
def test_property_multiple_ring_points_all_map_to_correct_radii(
    bull_center, num_double_points, num_triple_points, seed
):
    """
    Property 2: Ring Points Map to Correct Radius (Multiple Points)
    
    For any set of points detected on ring edges, all double ring points should
    map to 170mm radius and all triple ring points should map to 107mm radius.
    
    Validates: Requirements 2.2, 2.3
    """
    matcher = create_matcher()
    np.random.seed(seed)
    bull_u, bull_v = bull_center
    
    # Generate random double ring points
    double_ring_points = []
    for _ in range(num_double_points):
        angle = np.random.uniform(0, 2 * np.pi)
        pixel_radius = np.random.uniform(50.0, 200.0)
        point_u = bull_u + pixel_radius * np.cos(angle)
        point_v = bull_v + pixel_radius * np.sin(angle)
        double_ring_points.append((point_u, point_v))
    
    # Generate random triple ring points
    triple_ring_points = []
    for _ in range(num_triple_points):
        angle = np.random.uniform(0, 2 * np.pi)
        pixel_radius = np.random.uniform(30.0, 150.0)
        point_u = bull_u + pixel_radius * np.cos(angle)
        point_v = bull_v + pixel_radius * np.sin(angle)
        triple_ring_points.append((point_u, point_v))
    
    # Create detection result
    detection_result = FeatureDetectionResult(
        bull_center=bull_center,
        ring_edges={
            'double_ring': double_ring_points,
            'triple_ring': triple_ring_points
        },
        radial_wires=[],
        wire_intersections=[],
        detection_time_ms=10.0,
        error=None
    )
    
    # Match features
    point_pairs = matcher.match(detection_result)
    
    # Property: All ring points should map to correct radii
    # Expected: bull center + double points + triple points
    expected_count = 1 + num_double_points + num_triple_points
    assert len(point_pairs) == expected_count, \
        f"Should have {expected_count} points, got {len(point_pairs)}"
    
    # First point is bull center
    assert point_pairs[0].board == (0.0, 0.0)
    
    # Next num_double_points should be at 170mm radius
    for i in range(1, 1 + num_double_points):
        x, y = point_pairs[i].board
        radius = np.sqrt(x**2 + y**2)
        assert abs(radius - 170.0) <= 1.0, \
            f"Double ring point {i} should be at 170mm radius, got {radius:.2f}mm"
    
    # Next num_triple_points should be at 107mm radius
    for i in range(1 + num_double_points, expected_count):
        x, y = point_pairs[i].board
        radius = np.sqrt(x**2 + y**2)
        assert abs(radius - 107.0) <= 1.0, \
            f"Triple ring point {i} should be at 107mm radius, got {radius:.2f}mm"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
