"""
Ring determination for dart board scoring.

Classifies a dart's radial distance from the board center into one of six
ring categories (bull, single_bull, triple, double, single, out_of_bounds)
using Winmau Blade 6 specifications.
"""

import logging

logger = logging.getLogger(__name__)


class RingDetector:
    """Determine which ring a dart hit based on its radius from center.

    Uses configurable board dimensions to classify radii into scoring rings.

    Args:
        config: Dictionary with 'board' section containing ring radii:
            bull_radius_mm, single_bull_radius_mm, triple_inner_mm,
            triple_outer_mm, double_inner_mm, double_outer_mm.
    """

    def __init__(self, config: dict) -> None:
        board_cfg = config.get("board", {})
        self.bull_radius: float = board_cfg.get("bull_radius_mm", 6.35)
        self.single_bull_radius: float = board_cfg.get("single_bull_radius_mm", 15.9)
        self.triple_inner: float = board_cfg.get("triple_inner_mm", 99.0)
        self.triple_outer: float = board_cfg.get("triple_outer_mm", 107.0)
        self.double_inner: float = board_cfg.get("double_inner_mm", 162.0)
        self.double_outer: float = board_cfg.get("double_outer_mm", 170.0)

    def determine_ring(self, radius: float) -> tuple[str, int, int]:
        """Classify a radius into a ring category.

        Args:
            radius: Distance from board center in mm (non-negative).

        Returns:
            Tuple of (ring_name, multiplier, base_score):
                - ring_name: one of "bull", "single_bull", "triple",
                  "double", "single", "out_of_bounds"
                - multiplier: 0 for bull/single_bull/out_of_bounds,
                  1 for single, 2 for double, 3 for triple
                - base_score: 50 for bull, 25 for single_bull, 0 otherwise
                  (sector-based rings get their base from the sector)
        """
        if radius < self.bull_radius:
            return ("bull", 0, 50)
        elif radius < self.single_bull_radius:
            return ("single_bull", 0, 25)
        elif self.triple_inner <= radius < self.triple_outer:
            return ("triple", 3, 0)
        elif self.double_inner <= radius < self.double_outer:
            return ("double", 2, 0)
        elif radius >= self.double_outer:
            return ("out_of_bounds", 0, 0)
        else:
            return ("single", 1, 0)
