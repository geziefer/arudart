"""
Unit tests for the DatasetExporter class.

Tests correct detection filtering, CSV structure and columns,
dataset splitting (70/15/15), and README generation.

Requirements: AC-7.5.5.1, AC-7.5.5.2, AC-7.5.5.4, AC-7.5.5.5
"""

import csv
import random
import tempfile
from pathlib import Path

import pytest

from src.analysis.dataset_exporter import DatasetExporter


def _make_feedback(is_correct: bool, ring: str = "triple", sector: int = 20,
                   num_cameras: int = 2) -> dict:
    """Build a minimal feedback dict with detections."""
    total_map = {"single": 1, "double": 2, "triple": 3}
    if ring in total_map:
        total = sector * total_map[ring]
    elif ring == "bull":
        total = 50
        sector = None
    elif ring == "single_bull":
        total = 25
        sector = None
    else:
        total = 0
        sector = None

    detections = [
        {
            "camera_id": i,
            "pixel": {"x": 400.0 + i * 10, "y": 300.0 + i * 5},
            "board": {"x": 2.0 + i, "y": 98.0 + i},
            "confidence": 0.80 + i * 0.02,
        }
        for i in range(num_cameras)
    ]

    return {
        "detected_score": {"ring": ring, "sector": sector, "total": total},
        "actual_score": {"ring": ring, "sector": sector, "total": total},
        "is_correct": is_correct,
        "dart_hit_event": {
            "timestamp": "2024-01-15T14:32:18.123456Z",
            "detections": detections,
        },
    }


class TestFilterCorrectDetections:
    """Test filter_correct_detections method."""

    def setup_method(self):
        self.exporter = DatasetExporter()

    def test_keeps_only_correct_entries(self):
        feedback = [
            _make_feedback(True),
            _make_feedback(False),
            _make_feedback(True),
        ]
        result = self.exporter.filter_correct_detections(feedback)
        assert len(result) == 2
        assert all(fb["is_correct"] for fb in result)

    def test_empty_list(self):
        assert self.exporter.filter_correct_detections([]) == []

    def test_all_correct(self):
        feedback = [_make_feedback(True) for _ in range(5)]
        result = self.exporter.filter_correct_detections(feedback)
        assert len(result) == 5

    def test_all_incorrect(self):
        feedback = [_make_feedback(False) for _ in range(5)]
        result = self.exporter.filter_correct_detections(feedback)
        assert len(result) == 0


class TestExportCsv:
    """Test export_csv method."""

    def setup_method(self):
        self.exporter = DatasetExporter()

    def test_csv_columns(self):
        feedback = [_make_feedback(True, num_cameras=2)]
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            self.exporter.export_csv(feedback, csv_path)

            with open(csv_path, newline="") as f:
                reader = csv.reader(f)
                header = next(reader)

        expected = [
            "timestamp", "camera_id", "image_path",
            "tip_x", "tip_y", "actual_score", "confidence",
        ]
        assert header == expected

    def test_rows_per_camera_detection(self):
        feedback = [
            _make_feedback(True, num_cameras=3),
            _make_feedback(True, num_cameras=2),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            self.exporter.export_csv(feedback, csv_path)

            with open(csv_path, newline="") as f:
                rows = list(csv.DictReader(f))

        assert len(rows) == 5  # 3 + 2

    def test_actual_score_label_format(self):
        feedback = [_make_feedback(True, ring="triple", sector=20, num_cameras=1)]
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            self.exporter.export_csv(feedback, csv_path)

            with open(csv_path, newline="") as f:
                rows = list(csv.DictReader(f))

        assert rows[0]["actual_score"] == "T20"

    def test_bull_score_label(self):
        feedback = [_make_feedback(True, ring="bull", num_cameras=1)]
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            self.exporter.export_csv(feedback, csv_path)

            with open(csv_path, newline="") as f:
                rows = list(csv.DictReader(f))

        assert rows[0]["actual_score"] == "DB"

    def test_empty_dataset_creates_header_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            self.exporter.export_csv([], csv_path)

            with open(csv_path, newline="") as f:
                reader = csv.reader(f)
                header = next(reader)
                rows = list(reader)

        assert len(rows) == 0
        assert len(header) == 7

    def test_pixel_coordinates_in_csv(self):
        feedback = [_make_feedback(True, num_cameras=1)]
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            self.exporter.export_csv(feedback, csv_path)

            with open(csv_path, newline="") as f:
                rows = list(csv.DictReader(f))

        assert rows[0]["tip_x"] == "400.0"
        assert rows[0]["tip_y"] == "300.0"


class TestSplitDataset:
    """Test split_dataset method."""

    def setup_method(self):
        self.exporter = DatasetExporter()

    def test_70_15_15_split(self):
        data = list(range(100))
        random.seed(42)
        train, val, test = self.exporter.split_dataset(data)

        assert len(train) + len(val) + len(test) == 100
        assert len(train) == 70
        assert len(val) == 15
        assert len(test) == 15

    def test_no_samples_lost(self):
        data = list(range(37))
        train, val, test = self.exporter.split_dataset(data)
        assert len(train) + len(val) + len(test) == 37

    def test_single_element(self):
        train, val, test = self.exporter.split_dataset([1])
        assert len(train) + len(val) + len(test) == 1

    def test_empty_dataset(self):
        train, val, test = self.exporter.split_dataset([])
        assert train == []
        assert val == []
        assert test == []

    def test_does_not_mutate_input(self):
        data = [1, 2, 3, 4, 5]
        original = data.copy()
        self.exporter.split_dataset(data)
        assert data == original


class TestGenerateReadme:
    """Test generate_readme method."""

    def setup_method(self):
        self.exporter = DatasetExporter()

    def test_readme_contains_statistics(self):
        stats = {
            "total_samples": 100,
            "train_samples": 70,
            "val_samples": 15,
            "test_samples": 15,
            "per_sector_counts": {20: 10, 1: 8},
            "per_ring_counts": {"triple": 30, "single": 50, "double": 20},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = Path(tmpdir) / "README.md"
            self.exporter.generate_readme(stats, readme_path)

            content = readme_path.read_text()

        assert "Total samples: 100" in content
        assert "Train samples: 70" in content
        assert "Validation samples: 15" in content
        assert "Test samples: 15" in content

    def test_readme_contains_sector_distribution(self):
        stats = {
            "total_samples": 20,
            "train_samples": 14,
            "val_samples": 3,
            "test_samples": 3,
            "per_sector_counts": {20: 10, 5: 10},
            "per_ring_counts": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = Path(tmpdir) / "README.md"
            self.exporter.generate_readme(stats, readme_path)

            content = readme_path.read_text()

        assert "Sector 5: 10" in content
        assert "Sector 20: 10" in content

    def test_readme_contains_ring_distribution(self):
        stats = {
            "total_samples": 20,
            "train_samples": 14,
            "val_samples": 3,
            "test_samples": 3,
            "per_sector_counts": {},
            "per_ring_counts": {"triple": 10, "single": 10},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = Path(tmpdir) / "README.md"
            self.exporter.generate_readme(stats, readme_path)

            content = readme_path.read_text()

        assert "single: 10" in content
        assert "triple: 10" in content

    def test_readme_contains_usage_instructions(self):
        stats = {
            "total_samples": 10,
            "train_samples": 7,
            "val_samples": 1,
            "test_samples": 2,
            "per_sector_counts": {},
            "per_ring_counts": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = Path(tmpdir) / "README.md"
            self.exporter.generate_readme(stats, readme_path)

            content = readme_path.read_text()

        assert "Usage" in content
        assert "pd.read_csv" in content

    def test_readme_creates_parent_dirs(self):
        stats = {"total_samples": 0, "train_samples": 0,
                 "val_samples": 0, "test_samples": 0,
                 "per_sector_counts": {}, "per_ring_counts": {}}
        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = Path(tmpdir) / "nested" / "dir" / "README.md"
            self.exporter.generate_readme(stats, readme_path)
            assert readme_path.exists()
