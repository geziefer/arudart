"""
Unit tests for the HeatmapGenerator class.

Tests heatmap image creation, color assignment, ring filtering,
and file output.

Requirements: AC-7.5.4.1, AC-7.5.4.2, AC-7.5.4.3, AC-7.5.4.5
"""

import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.analysis.heatmap_generator import (
    IMAGE_SIZE,
    HeatmapGenerator,
    assign_color,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic feedback data
# ---------------------------------------------------------------------------


def _make_feedback(
    x_mm: float,
    y_mm: float,
    is_correct: bool,
    ring: str = "single",
    sector: int = 20,
) -> dict:
    """Create a minimal feedback dict matching the metadata JSON format."""
    return {
        "detected_score": {"ring": ring, "sector": sector, "total": sector},
        "actual_score": {"ring": ring, "sector": sector, "total": sector},
        "is_correct": is_correct,
        "dart_hit_event": {
            "board_coordinates": {"x_mm": x_mm, "y_mm": y_mm},
            "polar_coordinates": {"radius_mm": 0, "angle_deg": 0},
            "score": {
                "base": sector,
                "multiplier": 1,
                "total": sector,
                "ring": ring,
                "sector": sector,
            },
            "fusion": {"confidence": 0.9, "cameras_used": [0], "num_cameras": 1},
            "detections": [],
        },
    }


# ---------------------------------------------------------------------------
# Color assignment tests
# ---------------------------------------------------------------------------


class TestAssignColor:
    """Test the assign_color helper function."""

    def test_green_for_high_accuracy(self):
        assert assign_color(0.95) == (0, 255, 0)

    def test_yellow_for_medium_accuracy(self):
        assert assign_color(0.80) == (0, 255, 255)

    def test_red_for_low_accuracy(self):
        assert assign_color(0.50) == (0, 0, 255)

    def test_gray_for_none(self):
        assert assign_color(None) == (128, 128, 128)

    def test_boundary_070(self):
        assert assign_color(0.70) == (0, 255, 255)

    def test_boundary_090(self):
        assert assign_color(0.90) == (0, 255, 255)

    def test_just_above_090(self):
        assert assign_color(0.901) == (0, 255, 0)

    def test_just_below_070(self):
        assert assign_color(0.699) == (0, 0, 255)


# ---------------------------------------------------------------------------
# Heatmap image creation tests
# ---------------------------------------------------------------------------


class TestGenerateHeatmap:
    """Test heatmap image generation."""

    def setup_method(self):
        self.gen = HeatmapGenerator()

    def test_returns_numpy_array(self):
        feedback = [_make_feedback(0, 0, True)]
        img = self.gen.generate_heatmap(feedback)
        assert isinstance(img, np.ndarray)

    def test_image_shape(self):
        feedback = [_make_feedback(10, 20, True)]
        img = self.gen.generate_heatmap(feedback)
        assert img.shape == (IMAGE_SIZE, IMAGE_SIZE, 3)

    def test_image_dtype(self):
        feedback = [_make_feedback(0, 0, False)]
        img = self.gen.generate_heatmap(feedback)
        assert img.dtype == np.uint8

    def test_empty_feedback_produces_image(self):
        img = self.gen.generate_heatmap([])
        assert img.shape == (IMAGE_SIZE, IMAGE_SIZE, 3)

    def test_heatmap_not_all_white(self):
        """With feedback data, the image should have colored cells."""
        feedback = [_make_feedback(0, 0, True) for _ in range(5)]
        img = self.gen.generate_heatmap(feedback)
        # The image should not be entirely white (overlay + cells)
        assert not np.all(img == 255)


# ---------------------------------------------------------------------------
# Ring filtering tests
# ---------------------------------------------------------------------------


class TestRingFiltering:
    """Test that ring_filter correctly limits feedback entries."""

    def setup_method(self):
        self.gen = HeatmapGenerator()

    def test_filter_singles(self):
        feedback = [
            _make_feedback(0, 0, True, ring="single"),
            _make_feedback(10, 10, True, ring="double"),
            _make_feedback(20, 20, True, ring="triple"),
        ]
        filtered = self.gen._filter_by_ring(feedback, "single")
        assert len(filtered) == 1
        assert filtered[0]["actual_score"]["ring"] == "single"

    def test_filter_doubles(self):
        feedback = [
            _make_feedback(0, 0, True, ring="single"),
            _make_feedback(10, 10, True, ring="double"),
        ]
        filtered = self.gen._filter_by_ring(feedback, "double")
        assert len(filtered) == 1

    def test_filter_triples(self):
        feedback = [
            _make_feedback(0, 0, True, ring="triple"),
            _make_feedback(10, 10, True, ring="single"),
        ]
        filtered = self.gen._filter_by_ring(feedback, "triple")
        assert len(filtered) == 1

    def test_filter_none_returns_all(self):
        feedback = [
            _make_feedback(0, 0, True, ring="single"),
            _make_feedback(10, 10, True, ring="double"),
            _make_feedback(20, 20, True, ring="triple"),
        ]
        filtered = self.gen._filter_by_ring(feedback, None)
        assert len(filtered) == 3

    def test_generate_heatmap_with_ring_filter(self):
        """generate_heatmap respects ring_filter parameter."""
        feedback = [
            _make_feedback(0, 0, True, ring="double"),
            _make_feedback(10, 10, False, ring="single"),
        ]
        img = self.gen.generate_heatmap(feedback, ring_filter="double")
        assert img.shape == (IMAGE_SIZE, IMAGE_SIZE, 3)


# ---------------------------------------------------------------------------
# Save heatmap tests
# ---------------------------------------------------------------------------


class TestSaveHeatmap:
    """Test saving heatmap images to disk."""

    def setup_method(self):
        self.gen = HeatmapGenerator()

    def test_save_creates_file(self):
        feedback = [_make_feedback(0, 0, True)]
        img = self.gen.generate_heatmap(feedback)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "heatmap.png"
            self.gen.save_heatmap(img, out_path)
            assert out_path.exists()

    def test_saved_file_is_valid_image(self):
        feedback = [_make_feedback(0, 0, True)]
        img = self.gen.generate_heatmap(feedback)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "heatmap.png"
            self.gen.save_heatmap(img, out_path)
            loaded = cv2.imread(str(out_path))
            assert loaded is not None
            assert loaded.shape == (IMAGE_SIZE, IMAGE_SIZE, 3)

    def test_save_creates_parent_directories(self):
        feedback = [_make_feedback(0, 0, True)]
        img = self.gen.generate_heatmap(feedback)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "sub" / "dir" / "heatmap.png"
            self.gen.save_heatmap(img, out_path)
            assert out_path.exists()

    def test_save_per_ring_heatmaps(self):
        """Generate and save separate heatmaps for each ring type."""
        feedback = [
            _make_feedback(0, 0, True, ring="single"),
            _make_feedback(50, 50, True, ring="double"),
            _make_feedback(-50, -50, False, ring="triple"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            for ring in ("single", "double", "triple"):
                img = self.gen.generate_heatmap(feedback, ring_filter=ring)
                out_path = Path(tmpdir) / f"accuracy_heatmap_{ring}s.png"
                self.gen.save_heatmap(img, out_path)
                assert out_path.exists()
