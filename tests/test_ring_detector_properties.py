"""
Property-based tests for RingDetector class.

**Property 1: Ring Determination Correctness**

For any radius value, the ring detector should correctly classify it into
exactly one ring category (bull, single_bull, triple, double, single, or
out_of_bounds) according to the specified boundaries, and assign the correct
multiplier and base score.

**Validates: Requirements AC-7.3.1, AC-7.3.2, AC-7.3.3, AC-7.3.4, AC-7.3.5, AC-7.3.6**
"""

from hypothesis import given, settings, strategies as st

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

VALID_RINGS = {"bull", "single_bull", "triple", "double", "single", "out_of_bounds"}


class TestRingDeterminationCorrectness:
    """Property 1: Ring Determination Correctness.

    For any radius value in [0, 200], the ring detector classifies it into
    exactly one correct ring category with the correct multiplier and base score.

    **Validates: Requirements AC-7.3.1, AC-7.3.2, AC-7.3.3, AC-7.3.4, AC-7.3.5, AC-7.3.6**
    """

    @given(
        radius=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=200)
    def test_ring_classification_matches_boundaries(self, radius: float) -> None:
        """Every radius maps to exactly one ring with correct multiplier and base score."""
        detector = RingDetector(DEFAULT_CONFIG)
        ring_name, multiplier, base_score = detector.determine_ring(radius)

        # Must be a valid ring name
        assert ring_name in VALID_RINGS, f"Unknown ring: {ring_name} for radius {radius}"

        # Verify classification matches the boundary spec
        if radius < 6.35:
            assert ring_name == "bull"
            assert multiplier == 0
            assert base_score == 50
        elif radius < 15.9:
            assert ring_name == "single_bull"
            assert multiplier == 0
            assert base_score == 25
        elif 99.0 <= radius < 107.0:
            assert ring_name == "triple"
            assert multiplier == 3
            assert base_score == 0
        elif 162.0 <= radius < 170.0:
            assert ring_name == "double"
            assert multiplier == 2
            assert base_score == 0
        elif radius >= 170.0:
            assert ring_name == "out_of_bounds"
            assert multiplier == 0
            assert base_score == 0
        else:
            assert ring_name == "single"
            assert multiplier == 1
            assert base_score == 0
