"""
Unit tests for AccuracyAnalyzer.

Requirements: AC-7.5.3.1, AC-7.5.3.2, AC-7.5.3.3, AC-7.5.3.5
"""

import tempfile
from pathlib import Path

import pytest

from src.analysis.accuracy_analyzer import AccuracyAnalyzer, _score_dict_to_label


def _make_feedback(
    detected_ring: str,
    detected_sector: int | None,
    detected_total: int,
    actual_ring: str,
    actual_sector: int | None,
    actual_total: int,
    is_correct: bool,
) -> dict:
    """Helper to build a feedback dict matching JSON storage format."""
    return {
        "detected_score": {
            "ring": detected_ring,
            "sector": detected_sector,
            "total": detected_total,
        },
        "actual_score": {
            "ring": actual_ring,
            "sector": actual_sector,
            "total": actual_total,
        },
        "is_correct": is_correct,
    }


class TestScoreDictToLabel:
    def test_triple(self):
        assert _score_dict_to_label({"ring": "triple", "sector": 20, "total": 60}) == "T20"

    def test_double(self):
        assert _score_dict_to_label({"ring": "double", "sector": 16, "total": 32}) == "D16"

    def test_single(self):
        assert _score_dict_to_label({"ring": "single", "sector": 5, "total": 5}) == "S5"

    def test_bull(self):
        assert _score_dict_to_label({"ring": "bull", "sector": None, "total": 50}) == "DB"

    def test_single_bull(self):
        assert _score_dict_to_label({"ring": "single_bull", "sector": None, "total": 25}) == "SB"

    def test_miss(self):
        assert _score_dict_to_label({"ring": "miss", "sector": None, "total": 0}) == "Miss"


class TestOverallAccuracy:
    """AC-7.5.3.1: Overall accuracy = correct / total."""

    def setup_method(self):
        self.analyzer = AccuracyAnalyzer()

    def test_eight_of_ten_correct(self):
        """8/10 correct → 80%."""
        feedback = []
        for i in range(8):
            feedback.append(_make_feedback("single", 20, 20, "single", 20, 20, True))
        for i in range(2):
            feedback.append(_make_feedback("single", 20, 20, "single", 1, 1, False))
        assert self.analyzer.compute_overall_accuracy(feedback) == pytest.approx(80.0)

    def test_all_correct(self):
        feedback = [_make_feedback("triple", 20, 60, "triple", 20, 60, True)] * 5
        assert self.analyzer.compute_overall_accuracy(feedback) == pytest.approx(100.0)

    def test_all_incorrect(self):
        feedback = [_make_feedback("triple", 20, 60, "single", 20, 20, False)] * 5
        assert self.analyzer.compute_overall_accuracy(feedback) == pytest.approx(0.0)

    def test_empty_dataset(self):
        assert self.analyzer.compute_overall_accuracy([]) == 0.0


class TestPerSectorAccuracy:
    """AC-7.5.3.2: Per-sector accuracy grouping."""

    def setup_method(self):
        self.analyzer = AccuracyAnalyzer()

    def test_groups_by_actual_sector(self):
        feedback = [
            _make_feedback("single", 20, 20, "single", 20, 20, True),
            _make_feedback("single", 20, 20, "single", 20, 20, False),
            _make_feedback("single", 1, 1, "single", 1, 1, True),
        ]
        result = self.analyzer.compute_per_sector_accuracy(feedback)
        assert result[20] == pytest.approx(50.0)
        assert result[1] == pytest.approx(100.0)

    def test_skips_none_sectors(self):
        """Bulls and miss have sector=None and should be excluded."""
        feedback = [
            _make_feedback("bull", None, 50, "bull", None, 50, True),
            _make_feedback("single", 5, 5, "single", 5, 5, True),
        ]
        result = self.analyzer.compute_per_sector_accuracy(feedback)
        assert None not in result
        assert 5 in result

    def test_empty_dataset(self):
        assert self.analyzer.compute_per_sector_accuracy([]) == {}


class TestPerRingAccuracy:
    """AC-7.5.3.3: Per-ring accuracy grouping."""

    def setup_method(self):
        self.analyzer = AccuracyAnalyzer()

    def test_groups_by_actual_ring(self):
        feedback = [
            _make_feedback("single", 20, 20, "single", 20, 20, True),
            _make_feedback("single", 20, 20, "single", 1, 1, False),
            _make_feedback("double", 16, 32, "double", 16, 32, True),
        ]
        result = self.analyzer.compute_per_ring_accuracy(feedback)
        assert result["single"] == pytest.approx(50.0)
        assert result["double"] == pytest.approx(100.0)

    def test_empty_dataset(self):
        assert self.analyzer.compute_per_ring_accuracy([]) == {}


class TestFailureModes:
    """AC-7.5.3.5: Identify top failure modes."""

    def setup_method(self):
        self.analyzer = AccuracyAnalyzer()

    def test_identifies_top_failures(self):
        feedback = [
            _make_feedback("triple", 20, 60, "single", 20, 20, False),
            _make_feedback("triple", 20, 60, "single", 20, 20, False),
            _make_feedback("triple", 20, 60, "single", 20, 20, False),
            _make_feedback("double", 16, 32, "single", 16, 16, False),
            _make_feedback("single", 20, 20, "single", 20, 20, True),  # correct, skip
        ]
        modes = self.analyzer.identify_failure_modes(feedback, top_n=5)
        assert len(modes) == 2
        assert modes[0] == ("T20", "S20", 3)
        assert modes[1] == ("D16", "S16", 1)

    def test_empty_dataset(self):
        assert self.analyzer.identify_failure_modes([]) == []

    def test_all_correct_no_failures(self):
        feedback = [_make_feedback("single", 20, 20, "single", 20, 20, True)] * 5
        assert self.analyzer.identify_failure_modes(feedback) == []

    def test_top_n_limits_results(self):
        feedback = []
        for sector in range(1, 11):
            feedback.append(
                _make_feedback("triple", sector, sector * 3, "single", sector, sector, False)
            )
        modes = self.analyzer.identify_failure_modes(feedback, top_n=3)
        assert len(modes) == 3


class TestExportReport:
    """AC-7.5.3.6: Export analysis report to file."""

    def setup_method(self):
        self.analyzer = AccuracyAnalyzer()

    def test_creates_report_file(self):
        results = {
            "total": 10,
            "correct": 8,
            "incorrect": 2,
            "overall_accuracy": 80.0,
            "per_sector_accuracy": {20: 90.0, 1: 70.0},
            "per_ring_accuracy": {"single": 85.0, "double": 75.0},
            "failure_modes": [("T20", "S20", 2)],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.txt"
            self.analyzer.export_report(results, path)
            assert path.exists()
            content = path.read_text()
            assert "Overall Accuracy: 80.0%" in content
            assert "Total Throws: 10" in content
            assert "Sector 20: 90.0%" in content
            assert "T20 detected as S20: 2 occurrences" in content
