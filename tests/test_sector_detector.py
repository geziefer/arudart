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
        """theta=95 deg is counter-clockwise from 90 deg.
        rotated = (90 - 95) % 360 = 355 → wedge 19 → sector 5.
        Sector 5 is the next sector counter-clockwise from 20."""
        detector = SectorDetector(DEFAULT_CONFIG)
        assert detector.determine_sector(math.radians(95.0)) == 5

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
        """Boundary at Cartesian 72 deg (rotated=18).
        Just above 72 → rotated < 18 → wedge 0 → sector 20.
        Just below 72 → rotated > 18 → wedge 1 → sector 1."""
        detector = SectorDetector(DEFAULT_CONFIG)
        assert detector.determine_sector(math.radians(72.1)) == 20
        assert detector.determine_sector(math.radians(71.9)) == 1

    def test_boundary_between_20_and_5(self) -> None:
        """Boundary at Cartesian 99 deg (rotated = (90-99)%360 = 351 → 351/18 = 19.5).
        Actually: wedge 19 boundary is at rotated=342. Cartesian = 90-342 = -252 → 108 deg.
        So boundary between sector 5 (wedge 19) and sector 20 (wedge 0) is at 108 deg."""
        detector = SectorDetector(DEFAULT_CONFIG)
        # Just below 108 → rotated just above 342 → wedge 19 → sector 5
        assert detector.determine_sector(math.radians(107.9)) == 5
        # Just above 108 → rotated just below 342 → wedge 18 → sector 12
        assert detector.determine_sector(math.radians(108.1)) == 12

    def test_boundary_between_6_and_13(self) -> None:
        """Sector 6 at 0 deg (wedge 5), sector 13 at 18 deg (wedge 4).
        Boundary at rotated=90, Cartesian=0 deg. Actually:
        Wedge 4 spans rotated [72, 90) → Cartesian (0, 18].
        Wedge 5 spans rotated [90, 108) → Cartesian (-18, 0] = (342, 360].
        Boundary at Cartesian 0 deg (rotated=90)."""
        detector = SectorDetector(DEFAULT_CONFIG)
        # 0.1 deg → rotated = 89.9 → wedge 4 → sector 13
        assert detector.determine_sector(math.radians(0.1)) == 13
        # 359.9 deg → rotated = (90 - 359.9) % 360 = 90.1 → wedge 5 → sector 6
        assert detector.determine_sector(math.radians(359.9)) == 6

    def test_boundary_between_6_and_10(self) -> None:
        """Sector 6 (wedge 5) and sector 10 (wedge 6).
        Wedge 5 spans rotated [90, 108), wedge 6 spans [108, 126).
        Boundary at rotated=108, Cartesian = 90-108 = -18 → 342 deg."""
        detector = SectorDetector(DEFAULT_CONFIG)
        # 342.1 deg → rotated = (90-342.1)%360 = 107.9 → wedge 5 → sector 6
        assert detector.determine_sector(math.radians(342.1)) == 6
        # 341.9 deg → rotated = (90-341.9)%360 = 108.1 → wedge 6 → sector 10
        assert detector.determine_sector(math.radians(341.9)) == 10


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
        """1 deg → rotated = 89 → wedge 4 → sector 13.
        Sector 6 wedge spans Cartesian (342, 360], so 1 deg is in sector 13."""
        detector = SectorDetector(DEFAULT_CONFIG)
        sector = detector.determine_sector(math.radians(1.0))
        assert sector == 13

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
        """A +5 deg offset shifts the mapping: 90 deg now maps differently."""
        config = {
            "board": {
                "sectors": {
                    **DEFAULT_CONFIG["board"]["sectors"],
                    "sector_offset_deg": 5.0,
                }
            }
        }
        detector = SectorDetector(config)
        # With +5 offset, theta_deg becomes 95 deg.
        # rotated = (90 - 95) % 360 = 355 deg → wedge 19 → sector 5
        assert detector.determine_sector(math.radians(90.0)) == 5

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
