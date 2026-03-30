"""
Property-based tests for the feedback system.

# Feature: step-7.5-feedback-system

Tests:
- Property 1: Score Parsing Correctness

**Validates: Requirements Score Input Format, AC-7.5.1.4**
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.feedback.score_parser import ParsedScore, ScoreParser

# --- Constants ---

VALID_SECTORS = list(range(1, 21))
RING_MULTIPLIERS = {"single": 1, "double": 2, "triple": 3}

# --- Strategies ---

sector_strategy = st.sampled_from(VALID_SECTORS)
regular_ring_strategy = st.sampled_from(["single", "double", "triple"])


@st.composite
def score_string_with_expected(draw):
    """Generate a random score string in a supported format along with expected ParsedScore.

    Covers all format variants: prefix notation, word notation, plain numbers,
    bull variants, single bull variants, and miss variants.
    """
    category = draw(st.sampled_from([
        "prefix", "word", "plain_number",
        "bull", "single_bull", "miss",
    ]))

    if category == "prefix":
        ring = draw(regular_ring_strategy)
        sector = draw(sector_strategy)
        prefix = {"single": "S", "double": "D", "triple": "T"}[ring]
        # Randomize case
        use_upper = draw(st.booleans())
        score_str = f"{prefix}{sector}" if use_upper else f"{prefix.lower()}{sector}"
        total = sector * RING_MULTIPLIERS[ring]
        return score_str, ParsedScore(ring=ring, sector=sector, total=total)

    elif category == "word":
        ring = draw(regular_ring_strategy)
        sector = draw(sector_strategy)
        # Randomize case for word
        word = ring.upper() if draw(st.booleans()) else ring
        score_str = f"{word} {sector}"
        total = sector * RING_MULTIPLIERS[ring]
        return score_str, ParsedScore(ring=ring, sector=sector, total=total)

    elif category == "plain_number":
        sector = draw(sector_strategy)
        score_str = str(sector)
        return score_str, ParsedScore(ring="single", sector=sector, total=sector)

    elif category == "bull":
        variant = draw(st.sampled_from(["50", "DB", "db", "bull", "double bull"]))
        return variant, ParsedScore(ring="bull", sector=None, total=50)

    elif category == "single_bull":
        variant = draw(st.sampled_from(["25", "SB", "sb", "single bull"]))
        return variant, ParsedScore(ring="single_bull", sector=None, total=25)

    else:  # miss
        variant = draw(st.sampled_from(["0", "miss", "bounce", "MISS", "Bounce"]))
        return variant, ParsedScore(ring="miss", sector=None, total=0)


# --- Property 1: Score Parsing Correctness ---


class TestScoreParsingCorrectness:
    """
    Feature: step-7.5-feedback-system, Property 1: Score Parsing Correctness

    For any valid score string in the supported formats (singles, doubles,
    triples, bulls, miss), the score parser should correctly extract the
    ring type, sector number, and total score.

    **Validates: Requirements Score Input Format, AC-7.5.1.4**
    """

    def setup_method(self):
        self.parser = ScoreParser()

    @given(data=score_string_with_expected())
    @settings(max_examples=100, deadline=None)
    def test_parsed_ring_matches_expected(self, data):
        """Parser extracts the correct ring type for any valid format."""
        score_str, expected = data
        result = self.parser.parse_score(score_str)

        assert result is not None, f"Parser returned None for valid input: {score_str!r}"
        assert result.ring == expected.ring, (
            f"Ring mismatch for {score_str!r}: got {result.ring}, expected {expected.ring}"
        )

    @given(data=score_string_with_expected())
    @settings(max_examples=100, deadline=None)
    def test_parsed_sector_matches_expected(self, data):
        """Parser extracts the correct sector for any valid format."""
        score_str, expected = data
        result = self.parser.parse_score(score_str)

        assert result is not None, f"Parser returned None for valid input: {score_str!r}"
        assert result.sector == expected.sector, (
            f"Sector mismatch for {score_str!r}: got {result.sector}, expected {expected.sector}"
        )

    @given(data=score_string_with_expected())
    @settings(max_examples=100, deadline=None)
    def test_parsed_total_matches_expected(self, data):
        """Parser calculates the correct total score for any valid format."""
        score_str, expected = data
        result = self.parser.parse_score(score_str)

        assert result is not None, f"Parser returned None for valid input: {score_str!r}"
        assert result.total == expected.total, (
            f"Total mismatch for {score_str!r}: got {result.total}, expected {expected.total}"
        )

    @given(data=score_string_with_expected())
    @settings(max_examples=100, deadline=None)
    def test_whitespace_padding_does_not_affect_result(self, data):
        """Adding whitespace around input should not change the parsed result."""
        score_str, expected = data
        padded = f"  {score_str}  "
        result = self.parser.parse_score(padded)

        assert result is not None, f"Parser returned None for padded input: {padded!r}"
        assert result.ring == expected.ring
        assert result.sector == expected.sector
        assert result.total == expected.total


# ---------------------------------------------------------------------------
# Imports for Property 3 & 4
# ---------------------------------------------------------------------------

import json
import tempfile
import time
from pathlib import Path

from src.feedback.feedback_storage import FeedbackStorage
from src.fusion.dart_hit_event import CameraDetection, DartHitEvent, Score

# --- Strategies for feedback storage properties ---

RINGS = ["single", "double", "triple", "bull", "single_bull", "miss"]
RING_MULTIPLIERS_FULL = {
    "single": 1, "double": 2, "triple": 3,
    "bull": 1, "single_bull": 1, "miss": 0,
}


@st.composite
def parsed_score_strategy(draw):
    """Generate a random ParsedScore."""
    ring = draw(st.sampled_from(RINGS))
    if ring in ("bull", "single_bull", "miss"):
        sector = None
        if ring == "bull":
            total = 50
        elif ring == "single_bull":
            total = 25
        else:
            total = 0
    else:
        sector = draw(st.integers(min_value=1, max_value=20))
        total = sector * RING_MULTIPLIERS_FULL[ring]
    return ParsedScore(ring=ring, sector=sector, total=total)


@st.composite
def dart_hit_event_strategy(draw):
    """Generate a minimal random DartHitEvent."""
    sector = draw(st.integers(min_value=1, max_value=20))
    ring = draw(st.sampled_from(["single", "double", "triple"]))
    multiplier = {"single": 1, "double": 2, "triple": 3}[ring]
    total = sector * multiplier
    confidence = draw(st.floats(min_value=0.1, max_value=1.0))
    board_x = draw(st.floats(min_value=-170.0, max_value=170.0))
    board_y = draw(st.floats(min_value=-170.0, max_value=170.0))

    return DartHitEvent(
        timestamp="2024-01-15T14:32:18.123456Z",
        board_x=board_x,
        board_y=board_y,
        radius=abs(board_x),
        angle_rad=1.0,
        angle_deg=57.3,
        score=Score(base=sector, multiplier=multiplier, total=total, ring=ring, sector=sector),
        fusion_confidence=confidence,
        cameras_used=[0],
        num_cameras=1,
        detections=[
            CameraDetection(
                camera_id=0,
                pixel_x=400.0,
                pixel_y=300.0,
                board_x=board_x,
                board_y=board_y,
                confidence=confidence,
            ),
        ],
        image_paths={},
    )


@st.composite
def feedback_data_strategy(draw):
    """Generate a random feedback_data dict suitable for FeedbackStorage."""
    detected = draw(parsed_score_strategy())
    is_correct = draw(st.booleans())
    if is_correct:
        actual = detected
    else:
        actual = draw(parsed_score_strategy())
    dart_hit = draw(dart_hit_event_strategy())
    return {
        "detected_score": detected,
        "actual_score": actual,
        "is_correct": is_correct,
        "user_response": "y" if is_correct else "n",
        "dart_hit_event": dart_hit,
        "image_paths": {},
    }


# --- Property 3: Feedback Entry Completeness ---


class TestFeedbackEntryCompleteness:
    """
    Feature: step-7.5-feedback-system, Property 3: Feedback Entry Completeness

    For any saved feedback entry, the metadata JSON should contain all
    required fields (feedback_id, timestamp, detected_score, actual_score,
    is_correct, dart_hit_event, image_paths), and all fields are non-null.

    **Validates: Requirements AC-7.5.2.2, AC-7.5.2.4**
    """

    @given(data=feedback_data_strategy())
    @settings(max_examples=100, deadline=None)
    def test_saved_metadata_has_all_required_fields(self, data):
        """Every saved feedback entry contains all required metadata fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FeedbackStorage(feedback_dir=tmpdir)
            fid = storage.save_feedback(data)

            # Determine subdirectory
            subdir = "correct" if data["is_correct"] else "incorrect"
            meta_path = Path(tmpdir) / subdir / fid / "metadata.json"
            assert meta_path.exists(), f"metadata.json not found for {fid}"

            meta = json.loads(meta_path.read_text())

            required_fields = [
                "feedback_id",
                "timestamp",
                "detected_score",
                "actual_score",
                "is_correct",
                "user_response",
                "dart_hit_event",
                "image_paths",
            ]
            for field in required_fields:
                assert field in meta, f"Missing field: {field}"
                assert meta[field] is not None, f"Field is None: {field}"

    @given(data=feedback_data_strategy())
    @settings(max_examples=100, deadline=None)
    def test_feedback_id_matches_directory_name(self, data):
        """The feedback_id in metadata matches the directory name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FeedbackStorage(feedback_dir=tmpdir)
            fid = storage.save_feedback(data)

            subdir = "correct" if data["is_correct"] else "incorrect"
            meta_path = Path(tmpdir) / subdir / fid / "metadata.json"
            meta = json.loads(meta_path.read_text())

            assert meta["feedback_id"] == fid


# --- Property 4: Filename Uniqueness ---


class TestFilenameUniqueness:
    """
    Feature: step-7.5-feedback-system, Property 4: Filename Uniqueness

    For any two feedback entries saved at different times, they should
    have unique feedback IDs and directory names, ensuring no overwrites.

    **Validates: Requirements AC-7.5.2.5**
    """

    @given(
        data1=feedback_data_strategy(),
        data2=feedback_data_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_two_entries_get_unique_ids(self, data1, data2):
        """Two consecutively saved entries always get different feedback IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FeedbackStorage(feedback_dir=tmpdir)
            fid1 = storage.save_feedback(data1)
            fid2 = storage.save_feedback(data2)

            assert fid1 != fid2, (
                f"Duplicate feedback IDs: {fid1}"
            )

    @given(
        data1=feedback_data_strategy(),
        data2=feedback_data_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_two_entries_get_unique_directories(self, data1, data2):
        """Two consecutively saved entries are stored in different directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FeedbackStorage(feedback_dir=tmpdir)
            fid1 = storage.save_feedback(data1)
            fid2 = storage.save_feedback(data2)

            subdir1 = "correct" if data1["is_correct"] else "incorrect"
            subdir2 = "correct" if data2["is_correct"] else "incorrect"

            dir1 = Path(tmpdir) / subdir1 / fid1
            dir2 = Path(tmpdir) / subdir2 / fid2

            assert dir1 != dir2, (
                f"Same directory for two entries: {dir1}"
            )
            assert dir1.exists()
            assert dir2.exists()


# ---------------------------------------------------------------------------
# Imports for Property 2 & 5 (Accuracy / Confusion Matrix)
# ---------------------------------------------------------------------------

from collections import Counter

from src.analysis.accuracy_analyzer import AccuracyAnalyzer, _score_dict_to_label

# --- Strategies for accuracy analysis properties ---

REGULAR_RINGS = ["single", "double", "triple"]
ALL_RINGS = ["single", "double", "triple", "bull", "single_bull", "miss"]

_RING_TOTALS = {
    "bull": 50,
    "single_bull": 25,
    "miss": 0,
}


@st.composite
def feedback_dict_strategy(draw):
    """Generate a single feedback dict as returned by FeedbackStorage.load_all_feedback().

    The dict mirrors the JSON structure with plain dicts for scores.
    """
    is_correct = draw(st.booleans())

    # Actual score
    actual_ring = draw(st.sampled_from(ALL_RINGS))
    if actual_ring in ("bull", "single_bull", "miss"):
        actual_sector = None
        actual_total = _RING_TOTALS[actual_ring]
    else:
        actual_sector = draw(st.integers(min_value=1, max_value=20))
        mult = {"single": 1, "double": 2, "triple": 3}[actual_ring]
        actual_total = actual_sector * mult

    if is_correct:
        detected_ring = actual_ring
        detected_sector = actual_sector
        detected_total = actual_total
    else:
        detected_ring = draw(st.sampled_from(ALL_RINGS))
        if detected_ring in ("bull", "single_bull", "miss"):
            detected_sector = None
            detected_total = _RING_TOTALS[detected_ring]
        else:
            detected_sector = draw(st.integers(min_value=1, max_value=20))
            mult = {"single": 1, "double": 2, "triple": 3}[detected_ring]
            detected_total = detected_sector * mult

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


# --- Property 2: Accuracy Computation Correctness ---


class TestAccuracyComputationCorrectness:
    """
    Feature: step-7.5-feedback-system, Property 2: Accuracy Computation Correctness

    For any set of feedback entries, the computed accuracy should equal
    the count of correct detections divided by the total count, and
    per-sector/per-ring accuracies should be computed correctly by grouping.

    **Validates: Requirements AC-7.5.3.1, AC-7.5.3.2, AC-7.5.3.3**
    """

    def setup_method(self):
        self.analyzer = AccuracyAnalyzer()

    @given(feedback=st.lists(feedback_dict_strategy(), min_size=1, max_size=50))
    @settings(max_examples=100, deadline=None)
    def test_overall_accuracy_equals_correct_over_total(self, feedback):
        """Overall accuracy = correct_count / total_count * 100."""
        correct = sum(1 for fb in feedback if fb["is_correct"])
        total = len(feedback)
        expected = (correct / total) * 100.0

        result = self.analyzer.compute_overall_accuracy(feedback)
        assert abs(result - expected) < 1e-9, (
            f"Expected {expected}, got {result}"
        )

    @given(feedback=st.lists(feedback_dict_strategy(), min_size=1, max_size=50))
    @settings(max_examples=100, deadline=None)
    def test_per_sector_accuracy_groups_correctly(self, feedback):
        """Per-sector accuracy groups by actual_score.sector and computes ratio."""
        result = self.analyzer.compute_per_sector_accuracy(feedback)

        # Manually compute expected
        groups: dict[int, list[bool]] = {}
        for fb in feedback:
            sector = fb["actual_score"]["sector"]
            if sector is None:
                continue
            groups.setdefault(sector, []).append(fb["is_correct"])

        for sector, vals in groups.items():
            expected = (sum(vals) / len(vals)) * 100.0
            assert abs(result[sector] - expected) < 1e-9

        # No extra sectors
        assert set(result.keys()) == set(groups.keys())

    @given(feedback=st.lists(feedback_dict_strategy(), min_size=1, max_size=50))
    @settings(max_examples=100, deadline=None)
    def test_per_ring_accuracy_groups_correctly(self, feedback):
        """Per-ring accuracy groups by actual_score.ring and computes ratio."""
        result = self.analyzer.compute_per_ring_accuracy(feedback)

        groups: dict[str, list[bool]] = {}
        for fb in feedback:
            ring = fb["actual_score"]["ring"]
            groups.setdefault(ring, []).append(fb["is_correct"])

        for ring, vals in groups.items():
            expected = (sum(vals) / len(vals)) * 100.0
            assert abs(result[ring] - expected) < 1e-9

        assert set(result.keys()) == set(groups.keys())


# --- Property 5: Confusion Matrix Correctness ---


class TestConfusionMatrixCorrectness:
    """
    Feature: step-7.5-feedback-system, Property 5: Confusion Matrix Correctness

    For any set of feedback entries, the confusion matrix should correctly
    count the occurrences of each (detected_score, actual_score) pair.

    **Validates: Requirements AC-7.5.3.4**
    """

    def setup_method(self):
        self.analyzer = AccuracyAnalyzer()

    @given(feedback=st.lists(feedback_dict_strategy(), min_size=1, max_size=50))
    @settings(max_examples=100, deadline=None)
    def test_matrix_counts_match_pair_frequencies(self, feedback):
        """Each cell in the matrix equals the count of that (detected, actual) pair."""
        matrix = self.analyzer.generate_confusion_matrix(feedback)

        # Manually count
        expected: dict[tuple[str, str], int] = Counter()
        for fb in feedback:
            det = _score_dict_to_label(fb["detected_score"])
            act = _score_dict_to_label(fb["actual_score"])
            expected[(det, act)] += 1

        # Verify every expected pair is in the matrix
        for (det, act), cnt in expected.items():
            assert matrix.get(det, {}).get(act, 0) == cnt, (
                f"Mismatch for ({det}, {act}): expected {cnt}, "
                f"got {matrix.get(det, {}).get(act, 0)}"
            )

        # Verify no extra entries in matrix
        total_matrix = sum(
            cnt for row in matrix.values() for cnt in row.values()
        )
        assert total_matrix == len(feedback)


# ---------------------------------------------------------------------------
# Imports for Property 8 (Color Mapping for Heatmaps)
# ---------------------------------------------------------------------------

from src.analysis.heatmap_generator import assign_color

# --- Property 8: Color Mapping for Heatmaps ---


class TestColorMappingForHeatmaps:
    """
    Feature: step-7.5-feedback-system, Property 8: Color Mapping for Heatmaps

    For any accuracy value, the assigned color should match the specified
    thresholds: green for >90%, yellow for 70-90%, red for <70%.

    **Validates: Requirements AC-7.5.4.2**
    """

    @given(accuracy=st.floats(min_value=0.9000000001, max_value=1.0))
    @settings(max_examples=100, deadline=None)
    def test_high_accuracy_is_green(self, accuracy):
        """Accuracy > 0.90 maps to green (0, 255, 0)."""
        assert assign_color(accuracy) == (0, 255, 0)

    @given(accuracy=st.floats(min_value=0.70, max_value=0.90))
    @settings(max_examples=100, deadline=None)
    def test_medium_accuracy_is_yellow(self, accuracy):
        """0.70 ≤ accuracy ≤ 0.90 maps to yellow (0, 255, 255)."""
        assert assign_color(accuracy) == (0, 255, 255)

    @given(accuracy=st.floats(min_value=0.0, max_value=0.6999999999))
    @settings(max_examples=100, deadline=None)
    def test_low_accuracy_is_red(self, accuracy):
        """Accuracy < 0.70 maps to red (0, 0, 255)."""
        assert assign_color(accuracy) == (0, 0, 255)

    def test_boundary_070_is_yellow(self):
        """Exactly 0.70 maps to yellow."""
        assert assign_color(0.70) == (0, 255, 255)

    def test_boundary_090_is_yellow(self):
        """Exactly 0.90 maps to yellow."""
        assert assign_color(0.90) == (0, 255, 255)

    def test_none_accuracy_is_gray(self):
        """None accuracy (no data) maps to gray."""
        assert assign_color(None) == (128, 128, 128)


# ---------------------------------------------------------------------------
# Imports for Property 6 & 7 (Dataset Export / Split)
# ---------------------------------------------------------------------------

import csv
import os

from src.analysis.dataset_exporter import DatasetExporter

# --- Strategies for dataset export properties ---


@st.composite
def feedback_with_detections_strategy(draw):
    """Generate a feedback dict with dart_hit_event containing detections.

    Mirrors the JSON structure returned by FeedbackStorage.load_all_feedback().
    """
    is_correct = draw(st.booleans())

    actual_ring = draw(st.sampled_from(ALL_RINGS))
    if actual_ring in ("bull", "single_bull", "miss"):
        actual_sector = None
        actual_total = _RING_TOTALS[actual_ring]
    else:
        actual_sector = draw(st.integers(min_value=1, max_value=20))
        mult = {"single": 1, "double": 2, "triple": 3}[actual_ring]
        actual_total = actual_sector * mult

    if is_correct:
        detected_ring = actual_ring
        detected_sector = actual_sector
        detected_total = actual_total
    else:
        detected_ring = draw(st.sampled_from(ALL_RINGS))
        if detected_ring in ("bull", "single_bull", "miss"):
            detected_sector = None
            detected_total = _RING_TOTALS[detected_ring]
        else:
            detected_sector = draw(st.integers(min_value=1, max_value=20))
            mult = {"single": 1, "double": 2, "triple": 3}[detected_ring]
            detected_total = detected_sector * mult

    # Generate 1-3 camera detections
    num_cams = draw(st.integers(min_value=1, max_value=3))
    detections = []
    for cam_id in range(num_cams):
        detections.append({
            "camera_id": cam_id,
            "pixel": {
                "x": draw(st.floats(min_value=0.0, max_value=800.0)),
                "y": draw(st.floats(min_value=0.0, max_value=600.0)),
            },
            "board": {
                "x": draw(st.floats(min_value=-170.0, max_value=170.0)),
                "y": draw(st.floats(min_value=-170.0, max_value=170.0)),
            },
            "confidence": draw(st.floats(min_value=0.1, max_value=1.0)),
        })

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
        "dart_hit_event": {
            "timestamp": "2024-01-15T14:32:18.123456Z",
            "detections": detections,
        },
    }


# --- Property 6: Dataset Export Correctness ---


class TestDatasetExportCorrectness:
    """
    Feature: step-7.5-feedback-system, Property 6: Dataset Export Correctness

    For any feedback dataset, the exported CSV should contain only correct
    detections, have the specified columns in order, and include one row
    per camera detection with correct data.

    **Validates: Requirements AC-7.5.5.1, AC-7.5.5.2**
    """

    def setup_method(self):
        self.exporter = DatasetExporter()

    @given(
        feedback=st.lists(
            feedback_with_detections_strategy(), min_size=1, max_size=30
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_exported_csv_contains_only_correct_detections(self, feedback):
        """CSV rows come exclusively from correct feedback entries."""
        correct_entries = [fb for fb in feedback if fb["is_correct"]]
        filtered = self.exporter.filter_correct_detections(feedback)

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "export.csv"
            self.exporter.export_csv(filtered, csv_path)

            with open(csv_path, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

        # Expected total rows = sum of detections across correct entries
        expected_rows = sum(
            len(fb["dart_hit_event"]["detections"]) for fb in correct_entries
        )
        assert len(rows) == expected_rows

    @given(
        feedback=st.lists(
            feedback_with_detections_strategy(), min_size=1, max_size=30
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_exported_csv_has_correct_columns(self, feedback):
        """CSV header matches the required column specification."""
        filtered = self.exporter.filter_correct_detections(feedback)

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "export.csv"
            self.exporter.export_csv(filtered, csv_path)

            with open(csv_path, newline="") as f:
                reader = csv.reader(f)
                header = next(reader)

        expected_columns = [
            "timestamp", "camera_id", "image_path",
            "tip_x", "tip_y", "actual_score", "confidence",
        ]
        assert header == expected_columns


# --- Property 7: Dataset Split Ratios ---


class TestDatasetSplitRatios:
    """
    Feature: step-7.5-feedback-system, Property 7: Dataset Split Ratios

    For any dataset split with specified ratios (70/15/15), the actual
    split sizes should be within ±1 sample of the expected sizes due to
    rounding, and the total must be preserved.

    **Validates: Requirements AC-7.5.5.4**
    """

    def setup_method(self):
        self.exporter = DatasetExporter()

    @given(data=st.lists(st.integers(), min_size=1, max_size=200))
    @settings(max_examples=100, deadline=None)
    def test_split_preserves_total(self, data):
        """train + val + test == total (no samples lost)."""
        train, val, test = self.exporter.split_dataset(data)
        assert len(train) + len(val) + len(test) == len(data)

    @given(data=st.lists(st.integers(), min_size=4, max_size=200))
    @settings(max_examples=100, deadline=None)
    def test_split_sizes_within_tolerance(self, data):
        """Each split size is within ±1 of the expected ratio-based size."""
        total = len(data)
        train, val, test = self.exporter.split_dataset(data)

        expected_val = round(total * 0.15)
        expected_test = round(total * 0.15)
        expected_train = total - expected_val - expected_test

        assert abs(len(train) - expected_train) <= 1
        assert abs(len(val) - expected_val) <= 1
        assert abs(len(test) - expected_test) <= 1
