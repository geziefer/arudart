"""
Unit tests for RingDetector class.

Tests specific radius values and boundary cases for ring classification.

**Validates: Requirements AC-7.3.1, AC-7.3.2, AC-7.3.3, AC-7.3.4, AC-7.3.5, AC-7.3.6**
"""

import pytest

from src.fusion.ring_detector import RingDetector

DEFAULT_CONFIG = {
    "board": {
        "bull_radius_mm": 6.35,
        "single_bull_radius_mm": 15.9,
        "triple_inner_mm": 99.0,
        "triple_outer_mm": 107.0,
        "double_inner_mm": 162.0,
        "double_outer_mm": 170.0,
    }
}


class TestBull:
    """Test bull ring classification (r < 6.35mm).

    **Validates: Requirements AC-7.3.1**
    """

    def test_bull_center(self) -> None:
        """r=3mm is well inside the bull."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(3.0) == ("bull", 0, 50)

    def test_bull_zero_radius(self) -> None:
        """r=0 (exact center) is bull."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(0.0) == ("bull", 0, 50)


class TestSingleBull:
    """Test single bull ring classification (6.35 <= r < 15.9mm).

    **Validates: Requirements AC-7.3.2**
    """

    def test_single_bull_middle(self) -> None:
        """r=10mm is in the single bull."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(10.0) == ("single_bull", 0, 25)


class TestTriple:
    """Test triple ring classification (99 <= r < 107mm).

    **Validates: Requirements AC-7.3.3**
    """

    def test_triple_middle(self) -> None:
        """r=103mm is in the triple ring."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(103.0) == ("triple", 3, 0)


class TestDouble:
    """Test double ring classification (162 <= r < 170mm).

    **Validates: Requirements AC-7.3.4**
    """

    def test_double_middle(self) -> None:
        """r=166mm is in the double ring."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(166.0) == ("double", 2, 0)


class TestSingle:
    """Test single ring classification (all other valid positions).

    **Validates: Requirements AC-7.3.5**
    """

    def test_single_inner(self) -> None:
        """r=50mm is in the single ring (between single bull and triple)."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(50.0) == ("single", 1, 0)

    def test_single_between_triple_and_double(self) -> None:
        """r=130mm is single (between triple outer and double inner)."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(130.0) == ("single", 1, 0)


class TestOutOfBounds:
    """Test out of bounds classification (r >= 170mm).

    **Validates: Requirements AC-7.3.6**
    """

    def test_out_of_bounds(self) -> None:
        """r=180mm is out of bounds."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(180.0) == ("out_of_bounds", 0, 0)


class TestBoundaries:
    """Test exact boundary values.

    **Validates: Requirements AC-7.3.1, AC-7.3.2, AC-7.3.3, AC-7.3.4, AC-7.3.5, AC-7.3.6**
    """

    def test_bull_boundary(self) -> None:
        """r=6.35 is exactly at bull boundary → single_bull."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(6.35) == ("single_bull", 0, 25)

    def test_single_bull_boundary(self) -> None:
        """r=15.9 is exactly at single_bull boundary → single."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(15.9) == ("single", 1, 0)

    def test_triple_inner_boundary(self) -> None:
        """r=99.0 is exactly at triple inner → triple."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(99.0) == ("triple", 3, 0)

    def test_triple_outer_boundary(self) -> None:
        """r=107.0 is exactly at triple outer → single."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(107.0) == ("single", 1, 0)

    def test_double_inner_boundary(self) -> None:
        """r=162.0 is exactly at double inner → double."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(162.0) == ("double", 2, 0)

    def test_double_outer_boundary(self) -> None:
        """r=170.0 is exactly at double outer → out_of_bounds."""
        detector = RingDetector(DEFAULT_CONFIG)
        assert detector.determine_ring(170.0) == ("out_of_bounds", 0, 0)
