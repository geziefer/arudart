"""
Property tests for calibration verification error computation.

Property 9 (continued): Verification error computation
- Average error equals sum of errors / count
- Max error >= average error
- Min error <= average error
- Empty results produce zero stats
- Failed measurements (None errors) are excluded from averages
"""

import sys
from pathlib import Path

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from calibration.verify_calibration import compute_statistics


# Strategy: generate a single verification result dict
def result_entry(error_mm):
    """Build a result dict with given error (or None for failed)."""
    if error_mm is None:
        return {
            "label": "test",
            "expected_mm": (0.0, 0.0),
            "measured_mm": None,
            "pixel": (100, 100),
            "error_mm": None,
        }
    return {
        "label": "test",
        "expected_mm": (0.0, 0.0),
        "measured_mm": (1.0, 1.0),
        "pixel": (100, 100),
        "error_mm": round(error_mm, 2),
    }


positive_error = st.floats(min_value=0.01, max_value=500.0, allow_nan=False)
result_with_error = positive_error.map(result_entry)
failed_result = st.just(result_entry(None))
any_result = st.one_of(result_with_error, failed_result)


@given(st.lists(result_with_error, min_size=1, max_size=50))
@settings(max_examples=200)
def test_avg_error_equals_mean(results):
    """Average error must equal arithmetic mean of individual errors."""
    stats = compute_statistics(results)
    errors = [r["error_mm"] for r in results]
    expected_avg = round(sum(errors) / len(errors), 2)
    assert abs(stats["avg_error_mm"] - expected_avg) < 0.02


@given(st.lists(result_with_error, min_size=1, max_size=50))
@settings(max_examples=200)
def test_max_geq_avg_geq_min(results):
    """max_error >= avg_error >= min_error always holds."""
    stats = compute_statistics(results)
    assert stats["max_error_mm"] >= stats["avg_error_mm"]
    assert stats["avg_error_mm"] >= stats["min_error_mm"]


@given(st.lists(result_with_error, min_size=1, max_size=50))
@settings(max_examples=200)
def test_max_error_is_actual_max(results):
    """Max error must equal the largest individual error."""
    stats = compute_statistics(results)
    expected_max = round(max(r["error_mm"] for r in results), 2)
    assert abs(stats["max_error_mm"] - expected_max) < 0.02


@given(st.lists(result_with_error, min_size=1, max_size=50))
@settings(max_examples=200)
def test_min_error_is_actual_min(results):
    """Min error must equal the smallest individual error."""
    stats = compute_statistics(results)
    expected_min = round(min(r["error_mm"] for r in results), 2)
    assert abs(stats["min_error_mm"] - expected_min) < 0.02


def test_empty_results_produce_zeros():
    """Empty input should produce zero stats."""
    stats = compute_statistics([])
    assert stats["avg_error_mm"] == 0.0
    assert stats["max_error_mm"] == 0.0
    assert stats["min_error_mm"] == 0.0
    assert stats["num_measured"] == 0
    assert stats["num_failed"] == 0


@given(
    st.lists(result_with_error, min_size=1, max_size=20),
    st.lists(failed_result, min_size=1, max_size=10),
)
@settings(max_examples=200)
def test_failed_measurements_excluded_from_avg(good_results, bad_results):
    """Failed measurements (error_mm=None) must not affect averages."""
    mixed = good_results + bad_results
    stats = compute_statistics(mixed)

    errors = [r["error_mm"] for r in good_results]
    expected_avg = round(sum(errors) / len(errors), 2)

    assert stats["num_measured"] == len(good_results)
    assert stats["num_failed"] == len(bad_results)
    assert abs(stats["avg_error_mm"] - expected_avg) < 0.02


@given(st.lists(failed_result, min_size=1, max_size=10))
@settings(max_examples=50)
def test_all_failed_produces_zeros(results):
    """If every measurement failed, stats should be zero."""
    stats = compute_statistics(results)
    assert stats["avg_error_mm"] == 0.0
    assert stats["max_error_mm"] == 0.0
    assert stats["num_measured"] == 0
    assert stats["num_failed"] == len(results)


@given(positive_error)
@settings(max_examples=100)
def test_single_result_avg_equals_value(error):
    """With a single result, avg = max = min = that error."""
    results = [result_entry(error)]
    stats = compute_statistics(results)
    rounded = round(error, 2)
    assert stats["avg_error_mm"] == rounded
    assert stats["max_error_mm"] == rounded
    assert stats["min_error_mm"] == rounded
    assert stats["num_measured"] == 1
