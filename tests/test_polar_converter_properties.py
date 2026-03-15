"""
Property-based tests for PolarConverter.

# Feature: step-7-multi-camera-fusion

Tests:
- Property 2: Polar Coordinate Round Trip

**Validates: Requirements AC-7.2.1, AC-7.2.2, AC-7.2.3, AC-7.2.5**
"""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from src.fusion.polar_converter import PolarConverter


converter = PolarConverter()


class TestPolarCoordinateRoundTrip:
    """
    Property 2: Polar Coordinate Round Trip

    For any valid board coordinate (x, y) within reasonable bounds
    (-200mm to +200mm), converting to polar coordinates then back to
    Cartesian should return approximately the same point within 0.01mm
    tolerance.

    **Validates: Requirements AC-7.2.1, AC-7.2.2, AC-7.2.3, AC-7.2.5**
    """

    @given(
        x=st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False),
        y=st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_cartesian_to_polar_to_cartesian_round_trip(self, x: float, y: float) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 2: Polar Coordinate Round Trip

        Converting (x, y) -> (r, theta) -> (x', y') should give x' ≈ x and y' ≈ y
        within 0.01mm tolerance.

        **Validates: Requirements AC-7.2.1, AC-7.2.2, AC-7.2.3, AC-7.2.5**
        """
        r, theta = converter.cartesian_to_polar(x, y)
        x_back, y_back = converter.polar_to_cartesian(r, theta)

        assert abs(x_back - x) < 0.01, (
            f"X round-trip error: |{x_back} - {x}| = {abs(x_back - x):.6f} mm"
        )
        assert abs(y_back - y) < 0.01, (
            f"Y round-trip error: |{y_back} - {y}| = {abs(y_back - y):.6f} mm"
        )

    @given(
        x=st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False),
        y=st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_theta_always_in_valid_range(self, x: float, y: float) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 2: Polar Coordinate Round Trip

        The angle theta must always be in [0, 2*pi) for any input.

        **Validates: Requirements AC-7.2.3**
        """
        r, theta = converter.cartesian_to_polar(x, y)

        assert 0.0 <= theta < 2.0 * math.pi, (
            f"Theta {theta} out of [0, 2π) range for input ({x}, {y})"
        )
        assert r >= 0.0, f"Radius {r} is negative for input ({x}, {y})"

    @given(
        theta_deg=st.floats(min_value=-720.0, max_value=720.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_degrees_radians_round_trip(self, theta_deg: float) -> None:
        """
        Feature: step-7-multi-camera-fusion, Property 2: Polar Coordinate Round Trip

        Converting degrees -> radians -> degrees should return the same value.

        **Validates: Requirements AC-7.2.2**
        """
        theta_rad = converter.degrees_to_radians(theta_deg)
        theta_deg_back = converter.radians_to_degrees(theta_rad)

        assert abs(theta_deg_back - theta_deg) < 1e-9, (
            f"Degree round-trip error: |{theta_deg_back} - {theta_deg}| = {abs(theta_deg_back - theta_deg)}"
        )
