"""
Unit tests for PolarConverter class.

Tests specific scenarios for polar coordinate conversion including
origin handling, axis-aligned points, negative coordinates, and
angle normalization.

**Validates: Requirements AC-7.2.3, AC-7.2.4**
"""

import math

import pytest

from src.fusion.polar_converter import PolarConverter


converter = PolarConverter()


class TestOrigin:
    """Test origin (0, 0) edge case.

    **Validates: Requirements AC-7.2.4**
    """

    def test_origin_returns_zero_radius_and_angle(self) -> None:
        """Origin should map to (0, 0) in polar coordinates."""
        r, theta = converter.cartesian_to_polar(0.0, 0.0)
        assert r == 0.0
        assert theta == 0.0


class TestPositiveXAxis:
    """Test positive X axis point.

    **Validates: Requirements AC-7.2.3**
    """

    def test_positive_x_axis(self) -> None:
        """(100, 0) should give r=100, theta=0."""
        r, theta = converter.cartesian_to_polar(100.0, 0.0)
        assert abs(r - 100.0) < 1e-9
        assert abs(theta - 0.0) < 1e-9


class TestPositiveYAxis:
    """Test positive Y axis point.

    **Validates: Requirements AC-7.2.3**
    """

    def test_positive_y_axis(self) -> None:
        """(0, 100) should give r=100, theta=pi/2 (90 degrees)."""
        r, theta = converter.cartesian_to_polar(0.0, 100.0)
        assert abs(r - 100.0) < 1e-9
        assert abs(theta - math.pi / 2) < 1e-9


class TestNegativeCoordinates:
    """Test negative coordinate conversions.

    **Validates: Requirements AC-7.2.3**
    """

    def test_negative_x_axis(self) -> None:
        """(-100, 0) should give r=100, theta=pi (180 degrees)."""
        r, theta = converter.cartesian_to_polar(-100.0, 0.0)
        assert abs(r - 100.0) < 1e-9
        assert abs(theta - math.pi) < 1e-9

    def test_negative_y_axis(self) -> None:
        """(0, -100) should give r=100, theta=3*pi/2 (270 degrees)."""
        r, theta = converter.cartesian_to_polar(0.0, -100.0)
        assert abs(r - 100.0) < 1e-9
        assert abs(theta - 3 * math.pi / 2) < 1e-9

    def test_third_quadrant(self) -> None:
        """(-1, -1) should give theta in (pi, 3*pi/2)."""
        r, theta = converter.cartesian_to_polar(-1.0, -1.0)
        assert abs(r - math.sqrt(2)) < 1e-9
        assert abs(theta - 5 * math.pi / 4) < 1e-9


class TestAngleNormalization:
    """Test that theta is always in [0, 2*pi).

    **Validates: Requirements AC-7.2.3**
    """

    def test_all_quadrants_produce_valid_range(self) -> None:
        """Angles from all four quadrants should be in [0, 2*pi)."""
        test_points = [
            (1.0, 0.0),    # 0 degrees
            (1.0, 1.0),    # 45 degrees
            (0.0, 1.0),    # 90 degrees
            (-1.0, 1.0),   # 135 degrees
            (-1.0, 0.0),   # 180 degrees
            (-1.0, -1.0),  # 225 degrees
            (0.0, -1.0),   # 270 degrees
            (1.0, -1.0),   # 315 degrees
        ]
        for x, y in test_points:
            r, theta = converter.cartesian_to_polar(x, y)
            assert 0.0 <= theta < 2.0 * math.pi, (
                f"Theta {theta} out of range for ({x}, {y})"
            )

    def test_near_2pi_boundary(self) -> None:
        """A point just below the positive X axis should have theta near 2*pi, not negative."""
        r, theta = converter.cartesian_to_polar(100.0, -0.001)
        assert 0.0 <= theta < 2.0 * math.pi
        # Should be close to 2*pi (just under)
        assert theta > math.pi, f"Expected theta > pi, got {theta}"


class TestPolarToCartesian:
    """Test polar to Cartesian conversion.

    **Validates: Requirements AC-7.2.3**
    """

    def test_zero_radius(self) -> None:
        """r=0 should give (0, 0) regardless of angle."""
        x, y = converter.polar_to_cartesian(0.0, math.pi / 4)
        assert abs(x) < 1e-9
        assert abs(y) < 1e-9

    def test_known_conversion(self) -> None:
        """r=100, theta=pi/4 should give (70.71, 70.71)."""
        x, y = converter.polar_to_cartesian(100.0, math.pi / 4)
        expected = 100.0 * math.cos(math.pi / 4)
        assert abs(x - expected) < 1e-9
        assert abs(y - expected) < 1e-9


class TestAngleConversionHelpers:
    """Test radians_to_degrees and degrees_to_radians.

    **Validates: Requirements AC-7.2.3**
    """

    def test_zero(self) -> None:
        assert converter.radians_to_degrees(0.0) == 0.0
        assert converter.degrees_to_radians(0.0) == 0.0

    def test_90_degrees(self) -> None:
        assert abs(converter.radians_to_degrees(math.pi / 2) - 90.0) < 1e-9
        assert abs(converter.degrees_to_radians(90.0) - math.pi / 2) < 1e-9

    def test_180_degrees(self) -> None:
        assert abs(converter.radians_to_degrees(math.pi) - 180.0) < 1e-9
        assert abs(converter.degrees_to_radians(180.0) - math.pi) < 1e-9

    def test_360_degrees(self) -> None:
        assert abs(converter.radians_to_degrees(2 * math.pi) - 360.0) < 1e-9
        assert abs(converter.degrees_to_radians(360.0) - 2 * math.pi) < 1e-9
