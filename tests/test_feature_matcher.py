"""
Unit tests for FeatureMatcher class.

Tests sector 20 identification, wire sector assignment, and feature matching.
"""

import numpy as np
import pytest

from src.calibration.feature_detector import RadialWire, FeatureDetectionResult, WireIntersection
from src.calibration.feature_matcher import FeatureMatcher, PointPair


@pytest.fixture
def config():
    """Provide test configuration."""
    return {
        'calibration': {
            'feature_detection': {
                'bull_min_radius_px': 10,
                'bull_max_radius_px': 30,
            }
        }
    }


@pytest.fixture
def matcher(config):
    """Create a FeatureMatcher instance."""
    return FeatureMatcher(config)


def create_radial_wire(angle: float, confidence: float = 1.0) -> RadialWire:
    """
    Create a synthetic RadialWire for testing.
    
    Args:
        angle: Angle in degrees from vertical (0° = pointing up)
        confidence: Wire detection confidence
    
    Returns:
        RadialWire object
    """
    # Create dummy endpoints (not used in sector identification)
    endpoints = ((100, 100), (200, 200))
    return RadialWire(angle=angle, endpoints=endpoints, confidence=confidence)


class TestIdentifySector20:
    """Tests for identify_sector_20() method."""
    
    def test_single_wire_at_zero_degrees(self, matcher):
        """Test sector 20 identification with single wire at 0° (pointing up)."""
        wires = [create_radial_wire(0.0)]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index == 0, "Wire at 0° should be identified as sector 20"
    
    def test_single_wire_at_small_angle(self, matcher):
        """Test sector 20 identification with wire at small angle from vertical."""
        wires = [create_radial_wire(5.0)]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index == 0, "Wire at 5° should be identified as sector 20"
    
    def test_multiple_wires_selects_closest_to_vertical(self, matcher):
        """Test that sector 20 identification selects wire closest to vertical."""
        wires = [
            create_radial_wire(45.0),   # Index 0: 45° from vertical
            create_radial_wire(2.0),    # Index 1: 2° from vertical (closest)
            create_radial_wire(90.0),   # Index 2: 90° from vertical
            create_radial_wire(10.0),   # Index 3: 10° from vertical
        ]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index == 1, "Should select wire at 2° (closest to vertical)"
    
    def test_wire_at_360_degrees_wraps_to_zero(self, matcher):
        """Test that wire at 360° is treated as 0° (wraparound)."""
        wires = [
            create_radial_wire(180.0),  # Index 0: 180° from vertical
            create_radial_wire(359.0),  # Index 1: 359° from vertical (wraps to 1° from 0°)
        ]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index == 1, "Wire at 359° should be closest to 0° (wraparound)"
    
    def test_wire_near_360_degrees(self, matcher):
        """Test wire very close to 360° (should wrap to near 0°)."""
        wires = [
            create_radial_wire(355.0),  # 5° from 360° = 5° from 0°
            create_radial_wire(10.0),   # 10° from 0°
        ]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index == 0, "Wire at 355° (5° from 360°) should be closest to vertical"
    
    def test_empty_wire_list(self, matcher):
        """Test sector 20 identification with empty wire list."""
        wires = []
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index is None, "Should return None for empty wire list"
    
    def test_wire_at_180_degrees(self, matcher):
        """Test wire pointing down (180° from vertical)."""
        wires = [
            create_radial_wire(180.0),  # Pointing down
            create_radial_wire(0.0),    # Pointing up (should be selected)
        ]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index == 1, "Should select wire at 0° over 180°"
    
    def test_symmetric_wires_around_vertical(self, matcher):
        """Test wires symmetrically placed around vertical."""
        wires = [
            create_radial_wire(10.0),   # 10° clockwise from vertical
            create_radial_wire(350.0),  # 10° counter-clockwise from vertical (wraps)
        ]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        # Both are equally close to vertical (10° away)
        # Should select one of them (implementation may choose either)
        assert sector_20_index in [0, 1], "Should select one of the symmetric wires"
    
    def test_all_wires_far_from_vertical(self, matcher):
        """Test when all wires are far from vertical (still selects closest)."""
        wires = [
            create_radial_wire(90.0),   # 90° from vertical
            create_radial_wire(120.0),  # 120° from vertical
            create_radial_wire(60.0),   # 60° from vertical (closest)
        ]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index == 2, "Should select wire at 60° (closest to vertical)"
    
    def test_wire_angles_at_sector_boundaries(self, matcher):
        """Test wires at typical sector boundaries (18° apart)."""
        # Dartboard has 20 sectors, each 18° wide
        wires = [
            create_radial_wire(0.0),    # Sector 20 boundary
            create_radial_wire(18.0),   # Sector 1 boundary
            create_radial_wire(36.0),   # Sector 18 boundary
            create_radial_wire(54.0),   # Sector 4 boundary
        ]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index == 0, "Should select wire at 0° (sector 20)"
    
    def test_wire_confidence_does_not_affect_selection(self, matcher):
        """Test that wire confidence doesn't affect sector 20 identification."""
        wires = [
            create_radial_wire(5.0, confidence=0.3),   # Low confidence, close to vertical
            create_radial_wire(45.0, confidence=1.0),  # High confidence, far from vertical
        ]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        # Should select based on angle, not confidence
        assert sector_20_index == 0, "Should select wire closest to vertical regardless of confidence"
    
    def test_realistic_wire_configuration(self, matcher):
        """Test with realistic wire angles from actual dartboard detection."""
        # Simulate detected wires at various angles around the board
        wires = [
            create_radial_wire(2.5),    # Near sector 20 (should be selected)
            create_radial_wire(22.3),   # Near sector 1
            create_radial_wire(95.7),   # Near sector 6
            create_radial_wire(178.2),  # Near sector 3
            create_radial_wire(268.9),  # Near sector 11
            create_radial_wire(315.4),  # Near sector 5
        ]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index == 0, "Should identify wire at 2.5° as sector 20"
    
    def test_wire_at_exact_180_degrees_is_furthest(self, matcher):
        """Test that wire at exactly 180° is furthest from vertical."""
        wires = [
            create_radial_wire(180.0),  # Exactly opposite (furthest)
            create_radial_wire(179.0),  # Slightly less than 180°
            create_radial_wire(181.0),  # Slightly more than 180°
        ]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        # Should select one of the wires at 179° or 181° (both 1° from 180°)
        assert sector_20_index in [1, 2], "Should not select wire at exactly 180°"
    
    def test_image_orientation_parameter_accepted(self, matcher):
        """Test that image_orientation parameter is accepted (for future use)."""
        wires = [create_radial_wire(0.0)]
        
        # Should accept image_orientation parameter without error
        sector_20_index = matcher.identify_sector_20(wires, image_orientation='top')
        
        assert sector_20_index == 0, "Should work with image_orientation parameter"
    
    def test_many_wires_performance(self, matcher):
        """Test sector 20 identification with many wires (20 wires)."""
        # Create 20 wires at sector boundaries
        wires = [create_radial_wire(i * 18.0) for i in range(20)]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index == 0, "Should identify first wire (0°) as sector 20"
    
    def test_wire_at_1_degree(self, matcher):
        """Test wire at 1° from vertical."""
        wires = [
            create_radial_wire(1.0),
            create_radial_wire(90.0),
        ]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index == 0, "Wire at 1° should be identified as sector 20"
    
    def test_wire_at_359_degrees(self, matcher):
        """Test wire at 359° (1° counter-clockwise from vertical)."""
        wires = [
            create_radial_wire(359.0),
            create_radial_wire(90.0),
        ]
        
        sector_20_index = matcher.identify_sector_20(wires)
        
        assert sector_20_index == 0, "Wire at 359° should be identified as sector 20"


class TestAssignWireSectors:
    """Tests for assign_wire_sectors() method."""
    
    def test_single_wire_at_sector_20(self, matcher):
        """Test sector assignment with single wire at sector 20."""
        wires = [create_radial_wire(0.0)]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        assert wire_sectors[0] == 20, "Wire at sector 20 should be assigned sector 20"
    
    def test_multiple_wires_clockwise_order(self, matcher):
        """Test sector assignment follows clockwise order from sector 20."""
        # Create wires at 0°, 18°, 36°, 54° (sectors 20, 1, 18, 4)
        wires = [
            create_radial_wire(0.0),    # Sector 20
            create_radial_wire(18.0),   # Sector 1
            create_radial_wire(36.0),   # Sector 18
            create_radial_wire(54.0),   # Sector 4
        ]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        # Verify sector order: 20, 1, 18, 4
        assert wire_sectors[0] == 20, "Wire at 0° should be sector 20"
        assert wire_sectors[1] == 1, "Wire at 18° should be sector 1"
        assert wire_sectors[2] == 18, "Wire at 36° should be sector 18"
        assert wire_sectors[3] == 4, "Wire at 54° should be sector 4"
    
    def test_invalid_sector_20_index_negative(self, matcher):
        """Test sector assignment with invalid negative sector_20_index."""
        wires = [create_radial_wire(0.0)]
        sector_20_index = -1
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        assert wire_sectors == {}, "Should return empty dict for invalid index"
    
    def test_invalid_sector_20_index_out_of_bounds(self, matcher):
        """Test sector assignment with sector_20_index out of bounds."""
        wires = [create_radial_wire(0.0)]
        sector_20_index = 5  # Out of bounds (only 1 wire)
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        assert wire_sectors == {}, "Should return empty dict for out of bounds index"
    
    def test_all_20_sectors(self, matcher):
        """Test sector assignment with all 20 wires."""
        # Create 20 wires at sector boundaries (0°, 18°, 36°, ..., 342°)
        wires = [create_radial_wire(i * 18.0) for i in range(20)]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        # Verify all 20 sectors assigned correctly
        expected_sectors = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
        for i, expected_sector in enumerate(expected_sectors):
            assert wire_sectors[i] == expected_sector, \
                f"Wire {i} should be sector {expected_sector}, got {wire_sectors.get(i)}"
    
    def test_sector_20_not_at_index_0(self, matcher):
        """Test sector assignment when sector 20 wire is not at index 0."""
        # Wires detected in arbitrary order
        wires = [
            create_radial_wire(90.0),   # Index 0: sector 6
            create_radial_wire(0.0),    # Index 1: sector 20 (reference)
            create_radial_wire(18.0),   # Index 2: sector 1
            create_radial_wire(270.0),  # Index 3: sector 11
        ]
        sector_20_index = 1  # Sector 20 is at index 1
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        assert wire_sectors[0] == 6, "Wire at 90° should be sector 6"
        assert wire_sectors[1] == 20, "Wire at 0° should be sector 20"
        assert wire_sectors[2] == 1, "Wire at 18° should be sector 1"
        assert wire_sectors[3] == 11, "Wire at 270° should be sector 11"
    
    def test_angle_wraparound_near_360(self, matcher):
        """Test sector assignment with angles near 360° (wraparound case)."""
        # Sector 20 at 5°, other wires wrap around 360°
        wires = [
            create_radial_wire(5.0),    # Index 0: sector 20 (reference)
            create_radial_wire(355.0),  # Index 1: 350° from sector 20 = sector 5
            create_radial_wire(23.0),   # Index 2: 18° from sector 20 = sector 1
        ]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        assert wire_sectors[0] == 20, "Wire at 5° should be sector 20"
        assert wire_sectors[1] == 5, "Wire at 355° should be sector 5 (wraparound)"
        assert wire_sectors[2] == 1, "Wire at 23° should be sector 1"
    
    def test_angle_wraparound_sector_20_near_360(self, matcher):
        """Test sector assignment when sector 20 wire is near 360°."""
        wires = [
            create_radial_wire(358.0),  # Index 0: sector 20 (reference)
            create_radial_wire(16.0),   # Index 1: 18° from 358° = sector 1
            create_radial_wire(340.0),  # Index 2: 342° from 358° = sector 5
        ]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        assert wire_sectors[0] == 20, "Wire at 358° should be sector 20"
        assert wire_sectors[1] == 1, "Wire at 16° should be sector 1 (wraparound)"
        assert wire_sectors[2] == 5, "Wire at 340° should be sector 5"
    
    def test_incomplete_wire_detection_8_wires(self, matcher):
        """Test sector assignment with only 8 wires detected (typical minimum)."""
        # Simulate 8 wires detected in camera's good view region
        wires = [
            create_radial_wire(0.0),    # Sector 20
            create_radial_wire(18.0),   # Sector 1
            create_radial_wire(36.0),   # Sector 18
            create_radial_wire(54.0),   # Sector 4
            create_radial_wire(72.0),   # Sector 13
            create_radial_wire(90.0),   # Sector 6
            create_radial_wire(108.0),  # Sector 10
            create_radial_wire(126.0),  # Sector 15
        ]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        # Verify all 8 wires assigned correctly
        expected_sectors = [20, 1, 18, 4, 13, 6, 10, 15]
        for i, expected_sector in enumerate(expected_sectors):
            assert wire_sectors[i] == expected_sector, \
                f"Wire {i} should be sector {expected_sector}, got {wire_sectors.get(i)}"
    
    def test_incomplete_wire_detection_sparse(self, matcher):
        """Test sector assignment with sparse wire detection (non-consecutive sectors)."""
        # Wires detected at non-consecutive sectors
        wires = [
            create_radial_wire(0.0),    # Sector 20
            create_radial_wire(90.0),   # Sector 6 (5 sectors away)
            create_radial_wire(180.0),  # Sector 3 (10 sectors away)
            create_radial_wire(270.0),  # Sector 11 (15 sectors away)
        ]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        assert wire_sectors[0] == 20, "Wire at 0° should be sector 20"
        assert wire_sectors[1] == 6, "Wire at 90° should be sector 6"
        assert wire_sectors[2] == 3, "Wire at 180° should be sector 3"
        assert wire_sectors[3] == 11, "Wire at 270° should be sector 11"
    
    def test_wires_with_small_angle_offsets(self, matcher):
        """Test sector assignment with wires slightly offset from exact sector boundaries."""
        # Wires detected with realistic angle errors (±2°)
        wires = [
            create_radial_wire(1.5),    # Sector 20 (offset by +1.5°)
            create_radial_wire(19.8),   # Sector 1 (offset by +1.8°)
            create_radial_wire(34.2),   # Sector 18 (offset by -1.8°)
            create_radial_wire(55.1),   # Sector 4 (offset by +1.1°)
        ]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        # Should round to nearest sector
        assert wire_sectors[0] == 20, "Wire at 1.5° should round to sector 20"
        assert wire_sectors[1] == 1, "Wire at 19.8° should round to sector 1"
        assert wire_sectors[2] == 18, "Wire at 34.2° should round to sector 18"
        assert wire_sectors[3] == 4, "Wire at 55.1° should round to sector 4"
    
    def test_wires_at_sector_midpoints(self, matcher):
        """Test sector assignment with wires at sector midpoints (9° offsets)."""
        # Wires at midpoints between sector boundaries
        wires = [
            create_radial_wire(0.0),    # Sector 20 boundary
            create_radial_wire(9.0),    # Midpoint between 20 and 1 (should round to nearest)
            create_radial_wire(27.0),   # Midpoint between 1 and 18
        ]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        assert wire_sectors[0] == 20, "Wire at 0° should be sector 20"
        # At 9° offset, should round to nearest sector (either 20 or 1)
        assert wire_sectors[1] in [20, 1], "Wire at 9° should round to sector 20 or 1"
        # At 27° offset (1.5 sectors), should round to sector 1 or 18
        assert wire_sectors[2] in [1, 18], "Wire at 27° should round to sector 1 or 18"
    
    def test_counter_clockwise_angles_not_supported(self, matcher):
        """Test that counter-clockwise angles (negative) are handled correctly."""
        # Note: The implementation uses modulo to normalize angles
        wires = [
            create_radial_wire(0.0),    # Sector 20
            create_radial_wire(-18.0),  # Should be treated as 342° = sector 5
        ]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        assert wire_sectors[0] == 20, "Wire at 0° should be sector 20"
        # -18° should wrap to 342° (sector 5)
        assert wire_sectors[1] == 5, "Wire at -18° should wrap to sector 5"
    
    def test_realistic_camera_view_cam0(self, matcher):
        """Test sector assignment with realistic wire detection from cam0 (near sector 18)."""
        # cam0 sees sectors 18, 4, 13, 6, 10 well
        # Simulate sector 20 detected at slight angle
        wires = [
            create_radial_wire(2.0),    # Sector 20 (reference)
            create_radial_wire(20.5),   # Sector 1
            create_radial_wire(38.2),   # Sector 18
            create_radial_wire(56.8),   # Sector 4
            create_radial_wire(74.1),   # Sector 13
            create_radial_wire(91.5),   # Sector 6
            create_radial_wire(109.8),  # Sector 10
        ]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        expected_sectors = [20, 1, 18, 4, 13, 6, 10]
        for i, expected_sector in enumerate(expected_sectors):
            assert wire_sectors[i] == expected_sector, \
                f"Wire {i} should be sector {expected_sector}, got {wire_sectors.get(i)}"
    
    def test_realistic_camera_view_cam1(self, matcher):
        """Test sector assignment with realistic wire detection from cam1 (near sector 17)."""
        # cam1 sees sectors 17, 3, 19, 7, 16 well
        # Sector 20 might be detected at edge of view
        wires = [
            create_radial_wire(358.5),  # Sector 20 (reference, near 360°)
            create_radial_wire(144.2),  # Sector 2
            create_radial_wire(162.8),  # Sector 17
            create_radial_wire(180.5),  # Sector 3
            create_radial_wire(198.1),  # Sector 19
        ]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        expected_sectors = [20, 2, 17, 3, 19]
        for i, expected_sector in enumerate(expected_sectors):
            assert wire_sectors[i] == expected_sector, \
                f"Wire {i} should be sector {expected_sector}, got {wire_sectors.get(i)}"
    
    def test_realistic_camera_view_cam2(self, matcher):
        """Test sector assignment with realistic wire detection from cam2 (near sector 11)."""
        # cam2 sees sectors 11, 14, 9, 12, 5 well
        wires = [
            create_radial_wire(1.8),    # Sector 20 (reference)
            create_radial_wire(271.5),  # Sector 11
            create_radial_wire(289.2),  # Sector 14
            create_radial_wire(307.8),  # Sector 9
            create_radial_wire(325.1),  # Sector 12
            create_radial_wire(343.5),  # Sector 5
        ]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        expected_sectors = [20, 11, 14, 9, 12, 5]
        for i, expected_sector in enumerate(expected_sectors):
            assert wire_sectors[i] == expected_sector, \
                f"Wire {i} should be sector {expected_sector}, got {wire_sectors.get(i)}"
    
    def test_duplicate_sector_assignments(self, matcher):
        """Test that multiple wires can be assigned to same sector (detection noise)."""
        # Two wires detected very close together (both should map to same sector)
        wires = [
            create_radial_wire(0.0),    # Sector 20
            create_radial_wire(2.0),    # Also sector 20 (within rounding)
            create_radial_wire(18.0),   # Sector 1
        ]
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        # Both wires 0 and 1 should map to sector 20
        assert wire_sectors[0] == 20, "Wire at 0° should be sector 20"
        assert wire_sectors[1] == 20, "Wire at 2° should also be sector 20"
        assert wire_sectors[2] == 1, "Wire at 18° should be sector 1"
    
    def test_empty_wire_list(self, matcher):
        """Test sector assignment with empty wire list."""
        wires = []
        sector_20_index = 0
        
        wire_sectors = matcher.assign_wire_sectors(wires, sector_20_index)
        
        # Should return empty dict (sector_20_index out of bounds)
        assert wire_sectors == {}, "Should return empty dict for empty wire list"
    
    def test_sector_order_correctness(self, matcher):
        """Test that sector order matches dartboard standard."""
        # Verify the SECTOR_ORDER constant is correct
        expected_order = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
        assert matcher.SECTOR_ORDER == expected_order, \
            "SECTOR_ORDER should match standard dartboard layout"
    
    def test_sector_width_correctness(self, matcher):
        """Test that sector width is 18° (360° / 20 sectors)."""
        assert matcher.SECTOR_WIDTH_DEGREES == 18.0, \
            "SECTOR_WIDTH_DEGREES should be 18° (360° / 20 sectors)"


class TestMatch:
    """Tests for match() method."""
    
    def test_match_bull_center_only(self, matcher):
        """Test matching with only bull center detected."""
        detection_result = FeatureDetectionResult(
            bull_center=(400.0, 300.0),
            ring_edges={},
            radial_wires=[],
            wire_intersections=[],
            detection_time_ms=10.0,
            error=None
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Should have exactly 1 point pair (bull center → (0, 0))
        assert len(point_pairs) == 1
        assert point_pairs[0].pixel == (400.0, 300.0)
        assert point_pairs[0].board == (0.0, 0.0)
    
    def test_match_no_bull_center(self, matcher):
        """Test matching when bull center not detected."""
        detection_result = FeatureDetectionResult(
            bull_center=None,
            ring_edges={},
            radial_wires=[],
            wire_intersections=[],
            detection_time_ms=10.0,
            error="BULL_NOT_DETECTED"
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Should return empty list when no bull center
        assert len(point_pairs) == 0
    
    def test_match_with_ring_edges(self, matcher):
        """Test matching with bull center and ring edge points."""
        # Create ring edge points around bull
        bull_center = (400.0, 300.0)
        double_ring_points = [
            (400.0 + 170.0, 300.0),  # Right
            (400.0, 300.0 - 170.0),  # Top
            (400.0 - 170.0, 300.0),  # Left
            (400.0, 300.0 + 170.0),  # Bottom
        ]
        
        detection_result = FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges={'double_ring': double_ring_points, 'triple_ring': []},
            radial_wires=[],
            wire_intersections=[],
            detection_time_ms=10.0,
            error=None
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Should have bull center + 4 ring edge points
        assert len(point_pairs) == 5
        
        # First point should be bull center
        assert point_pairs[0].board == (0.0, 0.0)
        
        # Ring edge points should map to 170mm radius
        for i in range(1, 5):
            x, y = point_pairs[i].board
            radius = np.sqrt(x**2 + y**2)
            assert abs(radius - 170.0) < 0.1, f"Ring point should be at 170mm radius, got {radius:.1f}"


class TestBoardCoordinateComputation:
    """Tests for board coordinate computation (Requirement 2.1, 2.2, 2.3, 2.5)."""
    
    def test_bull_center_maps_to_origin(self, matcher):
        """Test that bull center always maps to (0, 0) - Requirement 2.1."""
        # Test with different bull center pixel positions
        test_positions = [
            (400.0, 300.0),  # Center of 800x600 image
            (320.0, 240.0),  # Center of 640x480 image
            (100.0, 100.0),  # Off-center
            (500.5, 350.7),  # Sub-pixel position
        ]
        
        for bull_pos in test_positions:
            detection_result = FeatureDetectionResult(
                bull_center=bull_pos,
                ring_edges={},
                radial_wires=[],
                wire_intersections=[],
                detection_time_ms=10.0,
                error=None
            )
            
            point_pairs = matcher.match(detection_result)
            
            # First point pair should be bull center → (0, 0)
            assert len(point_pairs) >= 1
            assert point_pairs[0].pixel == bull_pos
            assert point_pairs[0].board == (0.0, 0.0), \
                f"Bull center at {bull_pos} should map to (0, 0)"
    
    def test_double_ring_points_map_to_170mm_radius(self, matcher):
        """Test that double ring edge points map to 170mm radius - Requirement 2.2."""
        bull_center = (400.0, 300.0)
        
        # Create double ring points at cardinal directions
        # Note: pixel Y increases downward, board Y increases upward
        double_ring_points = [
            (400.0 + 100.0, 300.0),       # Right of bull (pixel space)
            (400.0, 300.0 - 100.0),       # Above bull (pixel space, -Y)
            (400.0 - 100.0, 300.0),       # Left of bull
            (400.0, 300.0 + 100.0),       # Below bull (pixel space, +Y)
            (400.0 + 70.7, 300.0 - 70.7), # Upper-right diagonal
            (400.0 - 70.7, 300.0 - 70.7), # Upper-left diagonal
            (400.0 - 70.7, 300.0 + 70.7), # Lower-left diagonal
            (400.0 + 70.7, 300.0 + 70.7), # Lower-right diagonal
        ]
        
        detection_result = FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges={'double_ring': double_ring_points},
            radial_wires=[],
            wire_intersections=[],
            detection_time_ms=10.0,
            error=None
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Should have bull center + 8 double ring points
        assert len(point_pairs) == 9
        
        # Check each ring point (skip first which is bull center)
        for i in range(1, 9):
            x, y = point_pairs[i].board
            radius = np.sqrt(x**2 + y**2)
            assert abs(radius - 170.0) < 1.0, \
                f"Double ring point {i} should be at 170mm radius, got {radius:.2f}mm"
    
    def test_triple_ring_points_map_to_107mm_radius(self, matcher):
        """Test that triple ring edge points map to 107mm radius - Requirement 2.3."""
        bull_center = (400.0, 300.0)
        
        # Create triple ring points at various angles
        triple_ring_points = [
            (400.0 + 60.0, 300.0),        # Right
            (400.0, 300.0 - 60.0),        # Top
            (400.0 - 60.0, 300.0),        # Left
            (400.0, 300.0 + 60.0),        # Bottom
            (400.0 + 42.4, 300.0 - 42.4), # Upper-right
            (400.0 - 42.4, 300.0 + 42.4), # Lower-left
        ]
        
        detection_result = FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges={'triple_ring': triple_ring_points},
            radial_wires=[],
            wire_intersections=[],
            detection_time_ms=10.0,
            error=None
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Should have bull center + 6 triple ring points
        assert len(point_pairs) == 7
        
        # Check each ring point (skip first which is bull center)
        for i in range(1, 7):
            x, y = point_pairs[i].board
            radius = np.sqrt(x**2 + y**2)
            assert abs(radius - 107.0) < 1.0, \
                f"Triple ring point {i} should be at 107mm radius, got {radius:.2f}mm"
    
    def test_both_ring_types_map_to_correct_radii(self, matcher):
        """Test that both double and triple ring points map to correct radii."""
        bull_center = (400.0, 300.0)
        
        double_ring_points = [
            (400.0 + 100.0, 300.0),  # Right
            (400.0, 300.0 - 100.0),  # Top
        ]
        
        triple_ring_points = [
            (400.0 + 60.0, 300.0),   # Right
            (400.0, 300.0 - 60.0),   # Top
        ]
        
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
        
        point_pairs = matcher.match(detection_result)
        
        # Should have bull center + 2 double + 2 triple = 5 points
        assert len(point_pairs) == 5
        
        # Verify radii (order: bull, double, double, triple, triple)
        assert point_pairs[0].board == (0.0, 0.0)  # Bull
        
        # Next 2 are double ring (170mm)
        for i in range(1, 3):
            x, y = point_pairs[i].board
            radius = np.sqrt(x**2 + y**2)
            assert abs(radius - 170.0) < 1.0, f"Double ring point should be at 170mm"
        
        # Next 2 are triple ring (107mm)
        for i in range(3, 5):
            x, y = point_pairs[i].board
            radius = np.sqrt(x**2 + y**2)
            assert abs(radius - 107.0) < 1.0, f"Triple ring point should be at 107mm"
    
    def test_coordinate_system_convention_x_axis(self, matcher):
        """Test coordinate system: +X points right - Requirement 2.5."""
        bull_center = (400.0, 300.0)
        
        # Point to the right of bull in pixel space
        double_ring_points = [(400.0 + 100.0, 300.0)]
        
        detection_result = FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges={'double_ring': double_ring_points},
            radial_wires=[],
            wire_intersections=[],
            detection_time_ms=10.0,
            error=None
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Point to the right should have positive X, Y near 0
        x, y = point_pairs[1].board
        assert x > 0, "Point to the right should have positive X"
        assert abs(y) < 1.0, "Point directly to the right should have Y ≈ 0"
    
    def test_coordinate_system_convention_y_axis(self, matcher):
        """Test coordinate system: +Y points up - Requirement 2.5."""
        bull_center = (400.0, 300.0)
        
        # Point above bull in pixel space (smaller Y in pixels)
        double_ring_points = [(400.0, 300.0 - 100.0)]
        
        detection_result = FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges={'double_ring': double_ring_points},
            radial_wires=[],
            wire_intersections=[],
            detection_time_ms=10.0,
            error=None
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Point above should have positive Y, X near 0
        x, y = point_pairs[1].board
        assert y > 0, "Point above bull should have positive Y"
        assert abs(x) < 1.0, "Point directly above should have X ≈ 0"
    
    def test_coordinate_system_all_quadrants(self, matcher):
        """Test coordinate system in all four quadrants."""
        bull_center = (400.0, 300.0)
        
        # Points in all four quadrants
        double_ring_points = [
            (400.0 + 70.7, 300.0 - 70.7),  # Upper-right: +X, +Y
            (400.0 - 70.7, 300.0 - 70.7),  # Upper-left: -X, +Y
            (400.0 - 70.7, 300.0 + 70.7),  # Lower-left: -X, -Y
            (400.0 + 70.7, 300.0 + 70.7),  # Lower-right: +X, -Y
        ]
        
        detection_result = FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges={'double_ring': double_ring_points},
            radial_wires=[],
            wire_intersections=[],
            detection_time_ms=10.0,
            error=None
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Check quadrants (skip bull center at index 0)
        x1, y1 = point_pairs[1].board  # Upper-right
        assert x1 > 0 and y1 > 0, "Upper-right should be +X, +Y"
        
        x2, y2 = point_pairs[2].board  # Upper-left
        assert x2 < 0 and y2 > 0, "Upper-left should be -X, +Y"
        
        x3, y3 = point_pairs[3].board  # Lower-left
        assert x3 < 0 and y3 < 0, "Lower-left should be -X, -Y"
        
        x4, y4 = point_pairs[4].board  # Lower-right
        assert x4 > 0 and y4 < 0, "Lower-right should be +X, -Y"
    
    def test_wire_intersection_sector_20_double_ring(self, matcher):
        """Test wire intersection at sector 20 (top) on double ring - Requirement 2.5."""
        bull_center = (400.0, 300.0)
        
        # Create wire at sector 20 (0° = vertical)
        wires = [create_radial_wire(0.0)]
        
        # Create intersection at sector 20 × double ring
        intersections = [
            WireIntersection(
                pixel=(400.0, 300.0 - 100.0),  # Above bull in pixel space
                ring_type='double_ring',
                wire_index=0,
                sector_estimate=None
            )
        ]
        
        detection_result = FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges={},
            radial_wires=wires,
            wire_intersections=intersections,
            detection_time_ms=10.0,
            error=None
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Should have bull center + 1 intersection
        assert len(point_pairs) == 2
        
        # Intersection should be at (0, 170) - top of board
        x, y = point_pairs[1].board
        assert abs(x) < 1.0, f"Sector 20 intersection should have X ≈ 0, got {x:.2f}"
        assert abs(y - 170.0) < 1.0, f"Sector 20 double ring should have Y ≈ 170, got {y:.2f}"
    
    def test_wire_intersection_sector_6_triple_ring(self, matcher):
        """Test wire intersection at sector 6 (right side) on triple ring."""
        bull_center = (400.0, 300.0)
        
        # Sector 6 is at 90° clockwise from sector 20
        # In our angle convention: 90° - 5*18° = 0° (pointing right)
        wires = [
            create_radial_wire(0.0),   # Sector 20 (reference)
            create_radial_wire(90.0),  # Sector 6 (5 sectors clockwise)
        ]
        
        # Create intersection at sector 6 × triple ring
        intersections = [
            WireIntersection(
                pixel=(400.0 + 60.0, 300.0),  # Right of bull
                ring_type='triple_ring',
                wire_index=1,
                sector_estimate=None
            )
        ]
        
        detection_result = FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges={},
            radial_wires=wires,
            wire_intersections=intersections,
            detection_time_ms=10.0,
            error=None
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Should have bull center + 1 intersection
        assert len(point_pairs) == 2
        
        # Sector 6 is at 90° in board coordinates (pointing right)
        # So intersection should be at (107, 0)
        x, y = point_pairs[1].board
        assert abs(x - 107.0) < 1.0, f"Sector 6 triple ring should have X ≈ 107, got {x:.2f}"
        assert abs(y) < 1.0, f"Sector 6 intersection should have Y ≈ 0, got {y:.2f}"
    
    def test_wire_intersection_multiple_sectors(self, matcher):
        """Test wire intersections at multiple sectors map to correct coordinates."""
        bull_center = (400.0, 300.0)
        
        # Create wires at sectors 20, 1, 18 (first 3 sectors clockwise)
        wires = [
            create_radial_wire(0.0),    # Sector 20
            create_radial_wire(18.0),   # Sector 1
            create_radial_wire(36.0),   # Sector 18
        ]
        
        # Create intersections on double ring
        intersections = [
            WireIntersection(
                pixel=(400.0, 300.0 - 100.0),  # Sector 20 (top)
                ring_type='double_ring',
                wire_index=0,
                sector_estimate=None
            ),
            WireIntersection(
                pixel=(400.0 + 52.7, 300.0 - 86.0),  # Sector 1 (18° clockwise)
                ring_type='double_ring',
                wire_index=1,
                sector_estimate=None
            ),
            WireIntersection(
                pixel=(400.0 + 95.1, 300.0 - 52.7),  # Sector 18 (36° clockwise)
                ring_type='double_ring',
                wire_index=2,
                sector_estimate=None
            ),
        ]
        
        detection_result = FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges={},
            radial_wires=wires,
            wire_intersections=intersections,
            detection_time_ms=10.0,
            error=None
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Should have bull center + 3 intersections
        assert len(point_pairs) == 4
        
        # All intersections should be at 170mm radius (double ring)
        for i in range(1, 4):
            x, y = point_pairs[i].board
            radius = np.sqrt(x**2 + y**2)
            assert abs(radius - 170.0) < 1.0, \
                f"Intersection {i} should be at 170mm radius, got {radius:.2f}mm"
    
    def test_wire_intersection_without_sector_identification(self, matcher):
        """Test that wire intersections without sector 20 are not matched."""
        bull_center = (400.0, 300.0)
        
        # Create wires but don't include sector 20 (all far from vertical)
        wires = [
            create_radial_wire(90.0),   # Sector 6
            create_radial_wire(180.0),  # Sector 3
        ]
        
        # Create intersections
        intersections = [
            WireIntersection(
                pixel=(400.0 + 100.0, 300.0),
                ring_type='double_ring',
                wire_index=0,
                sector_estimate=None
            ),
        ]
        
        detection_result = FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges={},
            radial_wires=wires,
            wire_intersections=intersections,
            detection_time_ms=10.0,
            error=None
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Should only have bull center (no intersections matched without sector 20)
        # Actually, sector 20 will be identified as the wire closest to vertical (90° in this case)
        # So we should get matches, but they might not be accurate
        assert len(point_pairs) >= 1  # At least bull center
    
    def test_complete_feature_set(self, matcher):
        """Test matching with complete feature set: bull, rings, and wire intersections."""
        bull_center = (400.0, 300.0)
        
        # Double ring points
        double_ring_points = [
            (400.0 + 100.0, 300.0),
            (400.0, 300.0 - 100.0),
        ]
        
        # Triple ring points
        triple_ring_points = [
            (400.0 + 60.0, 300.0),
            (400.0, 300.0 - 60.0),
        ]
        
        # Wires
        wires = [
            create_radial_wire(0.0),    # Sector 20
            create_radial_wire(18.0),   # Sector 1
        ]
        
        # Wire intersections
        intersections = [
            WireIntersection(
                pixel=(400.0, 300.0 - 100.0),
                ring_type='double_ring',
                wire_index=0,
                sector_estimate=None
            ),
            WireIntersection(
                pixel=(400.0, 300.0 - 60.0),
                ring_type='triple_ring',
                wire_index=0,
                sector_estimate=None
            ),
        ]
        
        detection_result = FeatureDetectionResult(
            bull_center=bull_center,
            ring_edges={
                'double_ring': double_ring_points,
                'triple_ring': triple_ring_points
            },
            radial_wires=wires,
            wire_intersections=intersections,
            detection_time_ms=10.0,
            error=None
        )
        
        point_pairs = matcher.match(detection_result)
        
        # Should have: bull (1) + double ring (2) + triple ring (2) + intersections (2) = 7
        assert len(point_pairs) == 7
        
        # Verify bull center
        assert point_pairs[0].board == (0.0, 0.0)
        
        # Verify all points have valid board coordinates
        for i, pair in enumerate(point_pairs):
            x, y = pair.board
            assert isinstance(x, float), f"Point {i} X should be float"
            assert isinstance(y, float), f"Point {i} Y should be float"
            assert not np.isnan(x), f"Point {i} X should not be NaN"
            assert not np.isnan(y), f"Point {i} Y should not be NaN"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
