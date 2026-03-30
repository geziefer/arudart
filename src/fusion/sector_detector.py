"""
Sector determination for dart board scoring.

Maps a polar angle to one of the 20 standard dartboard sectors using the
standard clockwise layout with sector 20 at the top (12 o'clock position).

Coordinate system:
    - theta=0 is +X axis (3 o'clock, sector 6)
    - theta=90 deg is +Y axis (12 o'clock, sector 20)
    - Angles increase counter-clockwise (standard Cartesian)
    - Sector order goes clockwise from top
"""

import logging
import math

logger = logging.getLogger(__name__)

# Standard dartboard sector order, clockwise from top
DEFAULT_SECTOR_ORDER = [
    20, 1, 18, 4, 13, 6, 10, 15, 2, 17,
    3, 19, 7, 16, 8, 11, 14, 9, 12, 5,
]


class SectorDetector:
    """Determine which sector (1-20) a dart hit based on its angle.

    Converts a Cartesian polar angle to a sector number using the standard
    dartboard layout. Sector 20 is centered at the top (90 deg Cartesian).
    Sectors proceed clockwise.

    Args:
        config: Dictionary with 'board.sectors' section containing:
            sector_order, sector_width_deg, wire_gap_deg, sector_offset_deg.
    """

    def __init__(self, config: dict) -> None:
        sector_cfg = config.get("board", {}).get("sectors", {})
        self.sector_order: list[int] = sector_cfg.get(
            "sector_order", DEFAULT_SECTOR_ORDER
        )
        self.sector_width_deg: float = sector_cfg.get("sector_width_deg", 18.0)
        self.wire_gap_deg: float = sector_cfg.get("wire_gap_deg", 2.0)
        self.sector_offset_deg: float = sector_cfg.get("sector_offset_deg", 0.0)
        self.num_sectors: int = len(self.sector_order)
        self.wedge_width_deg: float = 360.0 / self.num_sectors

    def determine_sector(self, theta_rad: float) -> int:
        """Map a polar angle to a sector number (1-20).

        The algorithm converts from Cartesian angles (counter-clockwise from
        +X axis) to the dartboard's clockwise layout with sector 20 at top.

        Wire hits (within wire_gap_deg/2 of a sector boundary) are assigned
        to the nearest sector center rather than returning None.

        Args:
            theta_rad: Angle in radians, counter-clockwise from +X axis.

        Returns:
            Sector number in the range 1-20.
        """
        # 1. Convert to degrees
        theta_deg = math.degrees(theta_rad)

        # 2. Apply configurable offset (camera mounting rotation)
        theta_deg += self.sector_offset_deg

        # 3. Rotate so sector 20 is at 0 deg and negate for clockwise.
        #    Sector 20 is at 90 deg Cartesian. Sectors go clockwise, but
        #    Cartesian angles go counter-clockwise, so we negate:
        #      rotated = (90 - theta_deg) % 360
        #    Offset by half a wedge so boundaries fall between sector centers.
        rotated = (90.0 - theta_deg + self.wedge_width_deg / 2.0) % 360.0

        # 4. Determine wedge index (each wedge is 360/20 = 18 deg)
        wedge_index = int(rotated / self.wedge_width_deg)

        # Clamp to valid range (handles floating-point edge at 360)
        if wedge_index >= self.num_sectors:
            wedge_index = 0

        # 5. Map wedge index to sector number
        sector = self.sector_order[wedge_index]

        logger.debug(
            "Angle %.1f deg (%.3f rad) → rotated %.1f deg → wedge %d → sector %d",
            math.degrees(theta_rad),
            theta_rad,
            rotated,
            wedge_index,
            sector,
        )

        return sector
