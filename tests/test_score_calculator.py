"""Unit tests for ScoreCalculator class."""

import datetime

from src.fusion.dart_hit_event import CameraDetection, DartHitEvent, Score
from src.fusion.score_calculator import ScoreCalculator

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


def _make_detection(camera_id: int, bx: float, by: float, conf: float = 0.8):
    """Helper to build a detection dict."""
    return {
        "camera_id": camera_id,
        "pixel": (400.0, 300.0),
        "board": (bx, by),
        "confidence": conf,
    }


class TestCalculateScore:
    """Tests for ScoreCalculator.calculate_score (task 7.2)."""

    def setup_method(self):
        self.calc = ScoreCalculator(CONFIG)

    def test_bull_score(self):
        score = self.calc.calculate_score("bull", 0, 50, None)
        assert score == Score(base=50, multiplier=0, total=50, ring="bull", sector=None)

    def test_single_bull_score(self):
        score = self.calc.calculate_score("single_bull", 0, 25, None)
        assert score == Score(
            base=25, multiplier=0, total=25, ring="single_bull", sector=None
        )

    def test_out_of_bounds_score(self):
        score = self.calc.calculate_score("out_of_bounds", 0, 0, None)
        assert score == Score(
            base=0, multiplier=0, total=0, ring="out_of_bounds", sector=None
        )

    def test_triple_20(self):
        score = self.calc.calculate_score("triple", 3, 0, 20)
        assert score == Score(base=20, multiplier=3, total=60, ring="triple", sector=20)

    def test_double_18(self):
        score = self.calc.calculate_score("double", 2, 0, 18)
        assert score == Score(
            base=18, multiplier=2, total=36, ring="double", sector=18
        )

    def test_single_5(self):
        score = self.calc.calculate_score("single", 1, 0, 5)
        assert score == Score(base=5, multiplier=1, total=5, ring="single", sector=5)


class TestProcessDetections:
    """Tests for ScoreCalculator.process_detections (tasks 7.1 + 7.3)."""

    def setup_method(self):
        self.calc = ScoreCalculator(CONFIG)

    def test_returns_none_for_empty_detections(self):
        result = self.calc.process_detections([])
        assert result is None

    def test_returns_none_for_low_confidence(self):
        det = _make_detection(0, 50.0, 50.0, conf=0.1)
        result = self.calc.process_detections([det])
        assert result is None

    def test_single_camera_bull(self):
        """Single detection at board center → bull 50."""
        det = _make_detection(0, 1.0, 1.0)
        event = self.calc.process_detections([det])
        assert event is not None
        assert event.score.total == 50
        assert event.score.ring == "bull"
        assert event.score.sector is None

    def test_single_camera_out_of_bounds(self):
        """Detection far from center → out of bounds."""
        det = _make_detection(0, 180.0, 0.0)
        event = self.calc.process_detections([det])
        assert event is not None
        assert event.score.total == 0
        assert event.score.ring == "out_of_bounds"

    def test_event_has_all_fields(self):
        """Verify DartHitEvent is fully populated (task 7.3)."""
        det = _make_detection(0, 0.0, 103.0)
        paths = {"0": "data/throws/cam0.jpg"}
        event = self.calc.process_detections([det], image_paths=paths)

        assert event is not None
        # Timestamp is ISO 8601
        datetime.datetime.fromisoformat(event.timestamp)
        # Board coordinates
        assert isinstance(event.board_x, float)
        assert isinstance(event.board_y, float)
        # Polar coordinates
        assert event.radius >= 0
        assert 0 <= event.angle_rad
        assert 0 <= event.angle_deg < 360
        # Score
        assert isinstance(event.score, Score)
        # Fusion metadata
        assert event.fusion_confidence > 0
        assert event.cameras_used == [0]
        assert event.num_cameras == 1
        # Detections
        assert len(event.detections) == 1
        assert isinstance(event.detections[0], CameraDetection)
        assert event.detections[0].camera_id == 0
        # Image paths
        assert event.image_paths == {"0": "data/throws/cam0.jpg"}

    def test_multi_camera_fusion(self):
        """Two cameras fused into weighted average."""
        d0 = _make_detection(0, 0.0, 103.0, conf=0.9)
        d1 = _make_detection(1, 0.0, 105.0, conf=0.7)
        event = self.calc.process_detections([d0, d1])

        assert event is not None
        assert event.num_cameras == 2
        assert set(event.cameras_used) == {0, 1}
        # Fused Y should be between 103 and 105 (weighted toward 103)
        assert 103.0 < event.board_y < 105.0
        assert len(event.detections) == 2

    def test_image_paths_default_empty(self):
        det = _make_detection(0, 1.0, 1.0)
        event = self.calc.process_detections([det])
        assert event is not None
        assert event.image_paths == {}
