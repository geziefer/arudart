"""
Unit tests for SectorDetector class.

Tests specific angles and boundary cases for sector classification.

**Validates: Requirements AC-7.4.1, AC-7.4.2, AC-7.4.3, AC-7.4.4, AC-7.4.5**
"""

import math

import pytest

from src.fusion.sector_detector import SectorDetector

DEFAULT_CONFIG = {
    "board": {
        "sectors": {
            "sector_order": [
                20, 1, 18, 4, 13, 6, 10, 15, 2, 17,
                3, 19, 7, 16, 8, 11, 14, 9, 12, 5,
            ],
            "sector_width_deg": 18.0,
            "wire_gap_deg": 2.0,
            "sector_offset_deg": 0.0,
        }
    }
}

# Sector center angles in Cartesian degrees (counter-clockwise from +X axis)
SECTOR_CENTERS_DEG = {
    20: 90.0,
    1: 72.0,
    18: 54.0,
    4: 36.0,
    13: 18.0,
    6: 0.0,
    10: 342.0,
    15: 324.0,
    2: 306.0,
    17: 288.0,
    3: 270.0,
    19: 252.0,
    7: 234.0,
    16: 216.0,
    8: 198.0,
    11: 180.0,
    14: 162.0,
    9: 144.0,
    12: 126.0,
    5: 108.0,
}


class TestSector20AtTop:
    """Test that sector 20 is centered at the top (theta=90 deg Cartesian).

    **Validates: Requirements AC-7.4.1, AC-7.4.3**
    """

    def test_sector_20_at_90_degrees(self) -> None:
        """theta=90 deg (pi/2 rad) should map to sector 20."""
        detector = SectorDetector(DEFAULT_CONFIG)
        assert detector.determine_sector(math.radians(90.0)) == 20

    def test_sector_20_slightly_ccw_of_center(self) -> None:
        """theta=95 deg is counter-clockwise from 90 deg, still within sector 20.
        With half-wedge offset, sector 20 spans [81, 99) Cartesian.
        95 deg is inside that range → sector 20."""
        detector = SectorDetector(DEFAULT_CONFIG)
        assert detector.determine_sector(math.radians(95.0)) == 20

    def test_sector_20_slightly_cw_of_center(self) -> None:
        """theta=85 deg is clockwise from 90 deg, still in sector 20 wedge.
        rotated = (90 - 85) % 360 = 5 → wedge 0 → sector 20."""
        detector = SectorDetector(DEFAULT_CONFIG)
        assert detector.determine_sector(math.radians(85.0)) == 20


class TestAllSectorCenters:
    """Test all 20 sectors at their center angles.

    **Validates: Requirements AC-7.4.1, AC-7.4.2**
    """

    @pytest.mark.parametrize(
        "expected_sector,center_deg",
        list(SECTOR_CENTERS_DEG.items()),
        ids=[f"sector_{s}" for s in SECTOR_CENTERS_DEG],
    )
    def test_sector_center(self, expected_sector: int, center_deg: float) -> None:
        """Each sector's center angle should map to that sector."""
        detector = SectorDetector(DEFAULT_CONFIG)
        theta_rad = math.radians(center_deg)
        result = detector.determine_sector(theta_rad)
        assert result == expected_sector, (
            f"Angle {center_deg} deg should be sector {expected_sector}, got {result}"
        )


class TestSectorBoundaries:
    """Test sector boundary angles.

    Each wedge is 18 deg wide. In rotated space, wedge N spans [N*18, (N+1)*18).
    In Cartesian: theta = 90 - rotated, so boundaries are at 90 - N*18.

    Boundary between sector 20 (wedge 0) and sector 1 (wedge 1) is at
    Cartesian 72 deg (rotated = 18 deg).

    **Validates: Requirements AC-7.4.2, AC-7.4.5**
    """

    def test_boundary_between_20_and_1(self) -> None:
        """Boundary between sector 20 and sector 1 is at Cartesian 81 deg.
        Sector 20 center at 90, sector 1 center at 72, boundary at (90+72)/2 = 81.
        Just above 81 → sector 20. Just below 81 → sector 1."""
        detector = SectorDetector(DEFAULT_CONFIG)
        assert detector.determine_sector(math.radians(81.1)) == 20
        assert detector.determine_sector(math.radians(80.9)) == 1

    def test_boundary_between_20_and_5(self) -> None:
        """Boundary between sector 20 and sector 5 is at Cartesian 99 deg.
        Sector 20 center at 90, sector 5 center at 108, boundary at (90+108)/2 = 99.
        Just below 99 → sector 20. Just above 99 → sector 5."""
        detector = SectorDetector(DEFAULT_CONFIG)
        assert detector.determine_sector(math.radians(98.9)) == 20
        assert detector.determine_sector(math.radians(99.1)) == 5

    def test_boundary_between_6_and_13(self) -> None:
        """Sector 6 center at 0 deg, sector 13 center at 18 deg.
        Boundary at 9 deg Cartesian.
        Just below 9 → sector 6. Just above 9 → sector 13."""
        detector = SectorDetector(DEFAULT_CONFIG)
        assert detector.determine_sector(math.radians(8.9)) == 6
        assert detector.determine_sector(math.radians(9.1)) == 13

    def test_boundary_between_6_and_10(self) -> None:
        """Sector 6 center at 0 deg, sector 10 center at 342 deg.
        Boundary at 351 deg Cartesian.
        Just above 351 → sector 6. Just below 351 → sector 10."""
        detector = SectorDetector(DEFAULT_CONFIG)
        assert detector.determine_sector(math.radians(351.1)) == 6
        assert detector.determine_sector(math.radians(350.9)) == 10


class TestWireDetection:
    """Test wire detection (dart near sector boundary).

    Wire gap is 2 deg, so the last 1 deg on each side of a boundary is wire.
    Wire hits should be assigned to the nearest sector (not return None).

    **Validates: Requirements AC-7.4.2**
    """

    def test_wire_hit_still_returns_sector(self) -> None:
        """A dart exactly on a boundary still returns a valid sector."""
        detector = SectorDetector(DEFAULT_CONFIG)
        # Exactly at the boundary between sector 20 and sector 1 (81 deg)
        sector = detector.determine_sector(math.radians(81.0))
        assert 1 <= sector <= 20

    def test_wire_near_boundary_returns_valid(self) -> None:
        """Dart very close to boundary returns a valid sector."""
        detector = SectorDetector(DEFAULT_CONFIG)
        # 0.5 deg from boundary
        sector = detector.determine_sector(math.radians(81.5))
        assert 1 <= sector <= 20


class TestAngleWraparound:
    """Test angle wraparound (359 deg -> 0 deg).

    **Validates: Requirements AC-7.4.5**
    """

    def test_near_360_degrees(self) -> None:
        """359 deg should map to a valid sector (near sector 6 at 0 deg)."""
        detector = SectorDetector(DEFAULT_CONFIG)
        sector = detector.determine_sector(math.radians(359.0))
        assert sector == 6

    def test_near_0_degrees(self) -> None:
        """1 deg is within sector 6 (center at 0 deg, spans [-9, 9) = [351, 9))."""
        detector = SectorDetector(DEFAULT_CONFIG)
        sector = detector.determine_sector(math.radians(1.0))
        assert sector == 6

    def test_zero_radians(self) -> None:
        """theta=0 rad (0 deg, +X axis) should be sector 6."""
        detector = SectorDetector(DEFAULT_CONFIG)
        assert detector.determine_sector(0.0) == 6

    def test_almost_2pi(self) -> None:
        """theta just below 2*pi should still be valid."""
        detector = SectorDetector(DEFAULT_CONFIG)
        sector = detector.determine_sector(2 * math.pi - 0.001)
        assert 1 <= sector <= 20


class TestSectorOffset:
    """Test sector offset application.

    **Validates: Requirements AC-7.4.4**
    """

    def test_zero_offset_sector_20_at_top(self) -> None:
        """With zero offset, sector 20 is at 90 deg."""
        detector = SectorDetector(DEFAULT_CONFIG)
        assert detector.determine_sector(math.radians(90.0)) == 20

    def test_positive_offset_shifts_sectors(self) -> None:
        """A +5 deg offset shifts the mapping: 90 deg now maps to sector 20 still
        (5 deg is within the 9 deg half-width of sector 20's wedge)."""
        config = {
            "board": {
                "sectors": {
                    **DEFAULT_CONFIG["board"]["sectors"],
                    "sector_offset_deg": 5.0,
                }
            }
        }
        detector = SectorDetector(config)
        # With +5 offset, effective angle = 95 deg.
        # Sector 20 spans [81, 99) so 95 is still sector 20.
        assert detector.determine_sector(math.radians(90.0)) == 20

    def test_negative_offset_shifts_sectors(self) -> None:
        """A -5 deg offset shifts the mapping."""
        config = {
            "board": {
                "sectors": {
                    **DEFAULT_CONFIG["board"]["sectors"],
                    "sector_offset_deg": -5.0,
                }
            }
        }
        detector = SectorDetector(config)
        # With -5 offset, theta_deg becomes 85 deg.
        # rotated = (90 - 85) % 360 = 5 deg → wedge 0 → sector 20
        assert detector.determine_sector(math.radians(90.0)) == 20

    def test_offset_preserves_relative_order(self) -> None:
        """Offset shifts all sectors equally; relative order is preserved."""
        config_offset = {
            "board": {
                "sectors": {
                    **DEFAULT_CONFIG["board"]["sectors"],
                    "sector_offset_deg": 18.0,
                }
            }
        }
        detector_default = SectorDetector(DEFAULT_CONFIG)
        detector_offset = SectorDetector(config_offset)

        # With 18 deg offset, sector at 90 deg should be same as
        # default sector at 90+18=108 deg
        sector_offset = detector_offset.determine_sector(math.radians(90.0))
        sector_default = detector_default.determine_sector(math.radians(108.0))
        assert sector_offset == sector_default
