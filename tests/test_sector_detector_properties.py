"""
Property-based tests for SectorDetector class.

**Property 4: Sector Determination Correctness**

For any angle theta in the range [0, 2*pi), the sector detector should map it
to exactly one sector number (1-20) according to the standard dartboard layout,
with sector 20 centered at the top (90 deg in Cartesian coordinates).

**Validates: Requirements AC-7.4.1, AC-7.4.2, AC-7.4.3, AC-7.4.4**
"""

import math

from hypothesis import given, settings, strategies as st

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

VALID_SECTORS = set(range(1, 21))


class TestSectorDeterminationCorrectness:
    """Property 4: Sector Determination Correctness.

    For any angle in [0, 2*pi), the sector detector maps it to exactly one
    valid sector number (1-20).

    **Validates: Requirements AC-7.4.1, AC-7.4.2, AC-7.4.3, AC-7.4.4**
    """

    @given(
        theta_rad=st.floats(
            min_value=0.0,
            max_value=2 * math.pi - 1e-9,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=200)
    def test_any_angle_maps_to_valid_sector(self, theta_rad: float) -> None:
        """Every angle in [0, 2*pi) maps to exactly one sector in 1-20."""
        detector = SectorDetector(DEFAULT_CONFIG)
        sector = detector.determine_sector(theta_rad)

        assert sector in VALID_SECTORS, (
            f"Angle {math.degrees(theta_rad):.2f} deg ({theta_rad:.4f} rad) "
            f"mapped to invalid sector {sector}"
        )

    @given(
        theta_rad=st.floats(
            min_value=0.0,
            max_value=2 * math.pi - 1e-9,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=200)
    def test_all_20_sectors_are_reachable(self, theta_rad: float) -> None:
        """The result is always an integer in [1, 20]."""
        detector = SectorDetector(DEFAULT_CONFIG)
        sector = detector.determine_sector(theta_rad)

        assert isinstance(sector, int), f"Sector should be int, got {type(sector)}"
        assert 1 <= sector <= 20, f"Sector {sector} out of range [1, 20]"

    @given(
        theta_rad=st.floats(
            min_value=0.0,
            max_value=2 * math.pi - 1e-9,
            allow_nan=False,
            allow_infinity=False,
        ),
        offset=st.floats(
            min_value=-10.0,
            max_value=10.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200)
    def test_offset_still_produces_valid_sector(
        self, theta_rad: float, offset: float
    ) -> None:
        """With any small offset, the result is still a valid sector."""
        config = {
            "board": {
                "sectors": {
                    **DEFAULT_CONFIG["board"]["sectors"],
                    "sector_offset_deg": offset,
                }
            }
        }
        detector = SectorDetector(config)
        sector = detector.determine_sector(theta_rad)

        assert sector in VALID_SECTORS, (
            f"Angle {math.degrees(theta_rad):.2f} deg with offset {offset} deg "
            f"mapped to invalid sector {sector}"
        )
