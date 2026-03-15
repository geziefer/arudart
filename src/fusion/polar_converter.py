"""
Polar coordinate conversion for dart board positioning.

Converts between Cartesian board coordinates (x, y in mm) and polar
coordinates (radius, angle) for ring and sector determination.
"""

import math


class PolarConverter:
    """Convert between Cartesian and polar coordinate systems.

    Stateless converter used in the scoring pipeline to transform fused
    board coordinates into polar form for ring/sector classification.

    Args:
        config: Configuration dictionary (accepted for interface consistency,
            not used by this class).
    """

    def __init__(self, config: dict | None = None) -> None:
        pass

    def cartesian_to_polar(self, x: float, y: float) -> tuple[float, float]:
        """Convert Cartesian (x, y) to polar (r, theta).

        Args:
            x: X coordinate in mm.
            y: Y coordinate in mm.

        Returns:
            Tuple of (r, theta) where r is the radius in mm and theta
            is the angle in radians, normalized to [0, 2*pi).
            Returns (0.0, 0.0) for the origin.
        """
        r = math.sqrt(x * x + y * y)
        if r == 0.0:
            return (0.0, 0.0)
        two_pi = 2.0 * math.pi
        theta = math.atan2(y, x) % two_pi
        # Guard against floating-point edge case where modulo returns exactly 2π
        if theta >= two_pi:
            theta = 0.0
        return (r, theta)

    def polar_to_cartesian(self, r: float, theta: float) -> tuple[float, float]:
        """Convert polar (r, theta) to Cartesian (x, y).

        Args:
            r: Radius in mm.
            theta: Angle in radians.

        Returns:
            Tuple of (x, y) coordinates in mm.
        """
        x = r * math.cos(theta)
        y = r * math.sin(theta)
        return (x, y)

    def radians_to_degrees(self, theta_rad: float) -> float:
        """Convert angle from radians to degrees.

        Args:
            theta_rad: Angle in radians.

        Returns:
            Angle in degrees.
        """
        return math.degrees(theta_rad)

    def degrees_to_radians(self, theta_deg: float) -> float:
        """Convert angle from degrees to radians.

        Args:
            theta_deg: Angle in degrees.

        Returns:
            Angle in radians.
        """
        return math.radians(theta_deg)
