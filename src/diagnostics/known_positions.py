"""Known board positions for accuracy testing.

Defines a catalog of known dartboard positions with expected coordinates
and scores, computed from BoardGeometry. Also provides helper functions
for computing position and angular errors.
"""

import math
from dataclasses import dataclass
from typing import Optional

from src.calibration.board_geometry import BoardGeometry


@dataclass
class KnownPosition:
    """A predefined board location with expected score and coordinates.

    Attributes:
        name: Human-readable label (e.g. "T20", "SB", "DB", "BS5").
        expected_x: Expected board x coordinate in mm.
        expected_y: Expected board y coordinate in mm.
        expected_ring: Expected ring classification name.
        expected_sector: Expected sector number (1-20), or None for bulls.
        expected_score: Expected total score.
    """

    name: str
    expected_x: float
    expected_y: float
    expected_ring: str
    expected_sector: Optional[int]
    expected_score: int


def build_known_positions(
    board_geometry: BoardGeometry,
    ring_filter: Optional[str] = None,
) -> list[KnownPosition]:
    """Compute known positions from board geometry.

    When ring_filter is None, returns the original 14-position set
    (DB, SB, plus T/D/BS/SS for sectors 20, 1, 5).

    When ring_filter is provided ("T", "D", "BS", or "SS"), returns
    positions for that ring across all 20 sectors in clockwise order
    starting from 20. Bulls are excluded.

    Args:
        board_geometry: BoardGeometry instance for coordinate computation.
        ring_filter: Optional ring abbreviation to filter by.
            "T" = triple, "D" = double, "BS" = big single, "SS" = small single.
            None = original 14-position set.

    Returns:
        List of KnownPosition objects.
    """
    # All 20 sectors in clockwise order from 20
    all_sectors = BoardGeometry.SECTOR_ORDER  # [20, 1, 18, 4, 13, ...]

    if ring_filter is not None:
        return _build_ring_positions(board_geometry, ring_filter, all_sectors)

    # Original 14-position set (backward compatible)
    positions: list[KnownPosition] = []

    # DB (double bull) — board center
    positions.append(KnownPosition(
        name="DB",
        expected_x=0.0,
        expected_y=0.0,
        expected_ring="bull",
        expected_sector=None,
        expected_score=50,
    ))

    # SB (single bull) — midpoint of single bull ring at sector 20 angle (90°)
    sb_radius = (BoardGeometry.DOUBLE_BULL_RADIUS + BoardGeometry.SINGLE_BULL_RADIUS) / 2
    sb_angle = board_geometry.get_sector_angle(20)  # 90° = π/2
    positions.append(KnownPosition(
        name="SB",
        expected_x=sb_radius * math.cos(sb_angle),
        expected_y=sb_radius * math.sin(sb_angle),
        expected_ring="single_bull",
        expected_sector=None,
        expected_score=25,
    ))

    # Sectors to generate positions for
    sectors = [20, 1, 5]

    for sector in sectors:
        # Triple
        tx, ty = board_geometry.get_board_coords(sector, "triple")
        positions.append(KnownPosition(
            name=f"T{sector}",
            expected_x=tx,
            expected_y=ty,
            expected_ring="triple",
            expected_sector=sector,
            expected_score=sector * 3,
        ))

        # Double
        dx, dy = board_geometry.get_board_coords(sector, "double")
        positions.append(KnownPosition(
            name=f"D{sector}",
            expected_x=dx,
            expected_y=dy,
            expected_ring="double",
            expected_sector=sector,
            expected_score=sector * 2,
        ))

        # Big single (outer single between triple and double)
        bsx, bsy = board_geometry.get_board_coords(sector, "single")
        positions.append(KnownPosition(
            name=f"BS{sector}",
            expected_x=bsx,
            expected_y=bsy,
            expected_ring="single",
            expected_sector=sector,
            expected_score=sector,
        ))

        # Small single (inner single between bull and triple)
        ss_radius = (BoardGeometry.SINGLE_BULL_RADIUS + BoardGeometry.TRIPLE_RING_INNER_RADIUS) / 2
        ss_angle = board_geometry.get_sector_angle(sector)
        positions.append(KnownPosition(
            name=f"SS{sector}",
            expected_x=ss_radius * math.cos(ss_angle),
            expected_y=ss_radius * math.sin(ss_angle),
            expected_ring="single",
            expected_sector=sector,
            expected_score=sector,
        ))

    return positions


def _build_ring_positions(
    board_geometry: BoardGeometry,
    ring_filter: str,
    sectors: list[int],
) -> list[KnownPosition]:
    """Build positions for a single ring across all 20 sectors.

    Args:
        board_geometry: BoardGeometry instance.
        ring_filter: "T", "D", "BS", or "SS".
        sectors: Ordered list of sector numbers.

    Returns:
        List of 20 KnownPosition objects.
    """
    ring_map = {
        "T":  ("triple",  "triple"),
        "D":  ("double",  "double"),
        "BS": ("single",  "single"),
        "SS": ("single",  None),   # SS uses custom radius, not get_board_coords
    }

    if ring_filter not in ring_map:
        raise ValueError(f"Invalid ring_filter '{ring_filter}'. Must be T, D, BS, or SS.")

    ring_name, board_ring_type = ring_map[ring_filter]
    positions: list[KnownPosition] = []

    ss_radius = (BoardGeometry.SINGLE_BULL_RADIUS + BoardGeometry.TRIPLE_RING_INNER_RADIUS) / 2

    for sector in sectors:
        if ring_filter == "SS":
            angle = board_geometry.get_sector_angle(sector)
            x = ss_radius * math.cos(angle)
            y = ss_radius * math.sin(angle)
        else:
            coords = board_geometry.get_board_coords(sector, board_ring_type)
            if coords is None:
                continue
            x, y = coords

        if ring_filter == "T":
            score = sector * 3
        elif ring_filter == "D":
            score = sector * 2
        else:
            score = sector

        positions.append(KnownPosition(
            name=f"{ring_filter}{sector}",
            expected_x=x,
            expected_y=y,
            expected_ring=ring_name,
            expected_sector=sector,
            expected_score=score,
        ))

    return positions


def compute_angular_error(a_deg: float, b_deg: float) -> float:
    """Compute the minimum angular difference between two angles.

    Handles wraparound correctly (e.g. 1° and 359° differ by 2°).

    Args:
        a_deg: First angle in degrees.
        b_deg: Second angle in degrees.

    Returns:
        Angular error in degrees, always in [0, 180].
    """
    diff = abs(a_deg - b_deg)
    return min(diff, 360.0 - diff)


def compute_position_error(x1: float, y1: float, x2: float, y2: float) -> float:
    """Compute Euclidean distance between two board positions.

    Args:
        x1: First position x coordinate.
        y1: First position y coordinate.
        x2: Second position x coordinate.
        y2: Second position y coordinate.

    Returns:
        Euclidean distance in mm.
    """
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
