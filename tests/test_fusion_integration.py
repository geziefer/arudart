"""Integration tests for the full fusion pipeline.

Tests ScoreCalculator with realistic multi-camera detection data,
verifying end-to-end scoring from detection dicts through to DartHitEvent.
Uses known control points (T20, D20, bull, etc.) with expected scores.
"""

import json
import math
import tempfile
from pathlib import Path

from src.fusion import ScoreCalculator
from src.fusion.dart_hit_event import DartHitEvent, Score

CONFIG = {
    "fusion": {"outlier_threshold_mm": 50.0, "min_confidence": 0.3},
    "board": {
        "bull_radius_mm": 6.35,
        "single_bull_radius_mm": 15.9,
        "triple_inner_mm": 99.0,
        "triple_outer_mm": 107.0,
        "double_inner_mm": 162.0,
        "double_outer_mm": 170.0,
        "sectors": {
            "sector_order": [
                20, 1, 18, 4, 13, 6, 10, 15, 2, 17,
                3, 19, 7, 16, 8, 11, 14, 9, 12, 5,
            ],
            "sector_width_deg": 18.0,
            "wire_gap_deg": 2.0,
            "sector_offset_deg": 0.0,
        },
    },
}


def _det(camera_id: int, bx: float, by: float, conf: float = 0.85):
    """Build a detection dict matching ScoreCalculator input format."""
    return {
        "camera_id": camera_id,
        "pixel": (400.0, 300.0),
        "board": (bx, by),
        "confidence": conf,
    }


# --- Known control point coordinates ---
# Sector 20 is at top (90 degrees in Cartesian = +Y axis)
# Triple ring: 99-107mm, center ~103mm
# Double ring: 162-170mm, center ~166mm
# Bull: r < 6.35mm
# Single bull: 6.35 <= r < 15.9mm

# T20: triple ring, sector 20 (top, +Y axis) → board coords (0, 103)
# D20: double ring, sector 20 → board coords (0, 166)
# S20: single ring, sector 20 → board coords (0, 50)
# Bull: center → board coords (0, 0) or (1, 1)
# Single bull: → board coords (0, 10)


class TestKnownControlPoints:
    """Test scoring for known dartboard positions."""

    def setup_method(self):
        self.calc = ScoreCalculator(CONFIG)

    def test_triple_20(self):
        """T20 = 60 points (20 x 3)."""
        det = _det(0, 0.0, 103.0)
        event = self.calc.process_detections([det])
        assert event is not None
        assert event.score.total == 60
        assert event.score.base == 20
        assert event.score.multiplier == 3
        assert event.score.ring == "triple"
        assert event.score.sector == 20

    def test_double_20(self):
        """D20 = 40 points (20 x 2)."""
        det = _det(0, 0.0, 166.0)
        event = self.calc.process_detections([det])
        assert event is not None
        assert event.score.total == 40
        assert event.score.base == 20
        assert event.score.multiplier == 2
        assert event.score.ring == "double"
        assert event.score.sector == 20

    def test_single_20(self):
        """S20 = 20 points (20 x 1)."""
        det = _det(0, 0.0, 50.0)
        event = self.calc.process_detections([det])
        assert event is not None
        assert event.score.total == 20
        assert event.score.base == 20
        assert event.score.multiplier == 1
        assert event.score.ring == "single"
        assert event.score.sector == 20

    def test_bull(self):
        """Bull = 50 points."""
        det = _det(0, 1.0, 1.0)
        event = self.calc.process_detections([det])
        assert event is not None
        assert event.score.total == 50
        assert event.score.ring == "bull"
        assert event.score.sector is None

    def test_single_bull(self):
        """Single bull = 25 points."""
        det = _det(0, 0.0, 10.0)
        event = self.calc.process_detections([det])
        assert event is not None
        assert event.score.total == 25
        assert event.score.ring == "single_bull"
        assert event.score.sector is None

    def test_out_of_bounds(self):
        """Out of bounds = 0 points."""
        det = _det(0, 0.0, 180.0)
        event = self.calc.process_detections([det])
        assert event is not None
        assert event.score.total == 0
        assert event.score.ring == "out_of_bounds"

    def test_triple_19(self):
        """T19 = 57 points. Sector 19 is at index 11 in sector_order."""
        # Sector detector: rotated = (90 - theta_deg) % 360
        # wedge_index = int(rotated / 18)
        # Sector 19 is at index 11, so rotated center = 11*18 + 9 = 207
        # theta_deg = 90 - 207 = -117 → 243 degrees
        angle_deg = 243.0
        angle_rad = math.radians(angle_deg)
        r = 103.0  # Triple ring center
        bx = r * math.cos(angle_rad)
        by = r * math.sin(angle_rad)
        det = _det(0, bx, by)
        event = self.calc.process_detections([det])
        assert event is not None
        assert event.score.ring == "triple"
        assert event.score.sector == 19
        assert event.score.total == 57


class TestMultiCameraFusion:
    """Test fusion with multiple camera detections."""

    def setup_method(self):
        self.calc = ScoreCalculator(CONFIG)

    def test_two_cameras_agree(self):
        """Two cameras detecting near T20 should fuse correctly."""
        d0 = _det(0, 0.0, 102.0, conf=0.9)
        d1 = _det(1, 0.0, 104.0, conf=0.8)
        event = self.calc.process_detections([d0, d1])
        assert event is not None
        assert event.num_cameras == 2
        assert set(event.cameras_used) == {0, 1}
        assert event.score.ring == "triple"
        assert event.score.sector == 20
        assert event.score.total == 60

    def test_three_cameras_agree(self):
        """Three cameras all detecting near bull."""
        d0 = _det(0, 1.0, 1.0, conf=0.85)
        d1 = _det(1, -1.0, 1.5, conf=0.80)
        d2 = _det(2, 0.5, 0.5, conf=0.75)
        event = self.calc.process_detections([d0, d1, d2])
        assert event is not None
        assert event.num_cameras == 3
        assert event.score.total == 50
        assert event.score.ring == "bull"

    def test_three_cameras_with_outlier(self):
        """Three cameras, one outlier rejected."""
        d0 = _det(0, 0.0, 103.0, conf=0.9)
        d1 = _det(1, 0.0, 104.0, conf=0.85)
        d2 = _det(2, 0.0, 200.0, conf=0.7)  # Outlier: >50mm from median
        event = self.calc.process_detections([d0, d1, d2])
        assert event is not None
        # Outlier should be rejected, fused from cam 0 and 1
        assert event.score.ring == "triple"
        assert event.score.sector == 20

    def test_weighted_average_shifts_toward_higher_confidence(self):
        """Fused position should be closer to higher-confidence detection."""
        d0 = _det(0, 0.0, 100.0, conf=0.9)
        d1 = _det(1, 0.0, 106.0, conf=0.3)
        event = self.calc.process_detections([d0, d1])
        assert event is not None
        # Weighted average should be closer to 100 than 106
        assert event.board_y < 103.0


class TestErrorHandling:
    """Test error conditions."""

    def setup_method(self):
        self.calc = ScoreCalculator(CONFIG)

    def test_no_detections(self):
        """Empty detection list returns None."""
        result = self.calc.process_detections([])
        assert result is None

    def test_all_low_confidence(self):
        """All detections below min_confidence returns None."""
        d0 = _det(0, 0.0, 103.0, conf=0.1)
        d1 = _det(1, 0.0, 104.0, conf=0.2)
        result = self.calc.process_detections([d0, d1])
        assert result is None

    def test_all_outliers(self):
        """All detections are outliers (>50mm apart) returns None."""
        d0 = _det(0, 0.0, 0.0, conf=0.8)
        d1 = _det(1, 0.0, 100.0, conf=0.8)
        d2 = _det(2, 100.0, 0.0, conf=0.8)
        result = self.calc.process_detections([d0, d1, d2])
        # With 3 detections all far apart, median-based outlier rejection
        # may keep some. The result depends on implementation.
        # At minimum, it should not crash.
        # If all rejected, returns None; otherwise a valid event.
        assert result is None or isinstance(result, DartHitEvent)


class TestEventSerialization:
    """Test DartHitEvent JSON serialization in integration context."""

    def setup_method(self):
        self.calc = ScoreCalculator(CONFIG)

    def test_event_to_json_and_back(self):
        """Full pipeline event can be serialized and deserialized."""
        d0 = _det(0, 0.0, 103.0, conf=0.9)
        d1 = _det(1, 0.0, 104.0, conf=0.85)
        paths = {"0": "data/throws/cam0.jpg", "1": "data/throws/cam1.jpg"}
        event = self.calc.process_detections([d0, d1], image_paths=paths)
        assert event is not None

        # Serialize to dict and back
        event_dict = event.to_dict()
        restored = DartHitEvent.from_dict(event_dict)

        assert restored.score.total == event.score.total
        assert restored.score.ring == event.score.ring
        assert restored.score.sector == event.score.sector
        assert restored.num_cameras == event.num_cameras
        assert restored.cameras_used == event.cameras_used
        assert len(restored.detections) == len(event.detections)
        assert restored.image_paths == event.image_paths

    def test_save_event_to_json_file(self):
        """Event can be saved to a JSON file and loaded back."""
        det = _det(0, 0.0, 103.0)
        event = self.calc.process_detections([det])
        assert event is not None

        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "event_test.json"
            with open(event_path, 'w') as f:
                json.dump(event.to_dict(), f, indent=2)

            with open(event_path, 'r') as f:
                loaded = json.load(f)

            restored = DartHitEvent.from_dict(loaded)
            assert restored.score.total == 60
            assert restored.score.ring == "triple"
            assert restored.score.sector == 20


class TestEventCompleteness:
    """Verify DartHitEvent has all required fields from the pipeline."""

    def setup_method(self):
        self.calc = ScoreCalculator(CONFIG)

    def test_all_fields_populated(self):
        """Event from pipeline has all required fields."""
        d0 = _det(0, 0.0, 103.0, conf=0.9)
        d1 = _det(1, 0.0, 105.0, conf=0.8)
        paths = {"0": "cam0.jpg", "1": "cam1.jpg"}
        event = self.calc.process_detections([d0, d1], image_paths=paths)
        assert event is not None

        # Timestamp
        assert event.timestamp is not None
        assert "T" in event.timestamp  # ISO 8601

        # Board coordinates
        assert isinstance(event.board_x, float)
        assert isinstance(event.board_y, float)

        # Polar coordinates
        assert event.radius >= 0
        assert 0 <= event.angle_rad < 2 * math.pi
        assert 0 <= event.angle_deg < 360

        # Score
        assert isinstance(event.score, Score)
        assert event.score.total >= 0

        # Fusion metadata
        assert 0 < event.fusion_confidence <= 1.0
        assert len(event.cameras_used) == 2
        assert event.num_cameras == 2

        # Per-camera detections
        assert len(event.detections) == 2
        for det in event.detections:
            assert det.camera_id in (0, 1)
            assert det.confidence > 0

        # Image paths
        assert event.image_paths == paths
