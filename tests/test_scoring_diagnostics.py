"""Unit tests for scoring diagnostics modules.

Tests for DiagnosticLogger session management, JSON persistence,
image copying, and session summary computation.
"""

import json
import math
from pathlib import Path

import pytest

from src.diagnostics.detection_record import CameraDiagnostic, DetectionRecord
from src.diagnostics.diagnostic_logger import DiagnosticLogger
from src.fusion.dart_hit_event import CameraDetection, DartHitEvent, Score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    board_x: float = 10.0,
    board_y: float = 20.0,
    cameras: list[tuple[int, float, float]] | None = None,
    fusion_confidence: float = 0.85,
    image_paths: dict[str, str] | None = None,
) -> DartHitEvent:
    """Build a minimal DartHitEvent for testing."""
    if cameras is None:
        cameras = [(0, 11.0, 21.0), (1, 9.5, 19.5)]

    detections = [
        CameraDetection(
            camera_id=cid,
            pixel_x=100.0 + cid * 10,
            pixel_y=200.0 + cid * 10,
            board_x=bx,
            board_y=by,
            confidence=0.9,
        )
        for cid, bx, by in cameras
    ]

    return DartHitEvent(
        timestamp="2025-01-15T10:30:00.000000Z",
        board_x=board_x,
        board_y=board_y,
        radius=22.36,
        angle_rad=1.107,
        angle_deg=63.43,
        score=Score(base=20, multiplier=3, total=60, ring="triple", sector=20),
        fusion_confidence=fusion_confidence,
        cameras_used=[c[0] for c in cameras],
        num_cameras=len(cameras),
        detections=detections,
        image_paths=image_paths or {},
    )


# ---------------------------------------------------------------------------
# DiagnosticLogger tests
# ---------------------------------------------------------------------------


class TestDiagnosticLoggerInit:
    """Tests for DiagnosticLogger session directory creation."""

    def test_creates_session_directory(self, tmp_path: Path) -> None:
        """Session directory is created under base_dir."""
        dl = DiagnosticLogger(base_dir=str(tmp_path))
        assert dl.session_dir.exists()
        assert dl.session_dir.is_dir()
        assert dl.session_dir.parent == tmp_path

    def test_session_dir_naming_pattern(self, tmp_path: Path) -> None:
        """Session directory follows Session_NNN_YYYY-MM-DD_HH-MM-SS pattern."""
        dl = DiagnosticLogger(base_dir=str(tmp_path))
        name = dl.session_dir.name
        assert name.startswith("Session_001_")
        # Should have date and time components
        parts = name.split("_")
        assert len(parts) >= 4

    def test_sequential_numbering(self, tmp_path: Path) -> None:
        """Second session gets number 002."""
        dl1 = DiagnosticLogger(base_dir=str(tmp_path))
        dl2 = DiagnosticLogger(base_dir=str(tmp_path))
        assert "Session_001_" in dl1.session_dir.name
        assert "Session_002_" in dl2.session_dir.name

    def test_session_dir_is_readonly_property(self, tmp_path: Path) -> None:
        """session_dir property cannot be set."""
        dl = DiagnosticLogger(base_dir=str(tmp_path))
        with pytest.raises(AttributeError):
            dl.session_dir = tmp_path / "other"


class TestDiagnosticLoggerLogDetection:
    """Tests for DiagnosticLogger.log_detection()."""

    def test_returns_detection_record(self, tmp_path: Path) -> None:
        """log_detection returns a DetectionRecord."""
        dl = DiagnosticLogger(base_dir=str(tmp_path))
        event = _make_event()
        record = dl.log_detection(event)
        assert isinstance(record, DetectionRecord)
        assert record.board_x == event.board_x

    def test_writes_json_file(self, tmp_path: Path) -> None:
        """log_detection writes a throw_NNN_*.json file."""
        dl = DiagnosticLogger(base_dir=str(tmp_path))
        event = _make_event()
        dl.log_detection(event)

        json_files = list(dl.session_dir.glob("throw_001_*.json"))
        assert len(json_files) == 1

        with open(json_files[0], "r") as fh:
            data = json.load(fh)
        assert data["fused_position"]["x_mm"] == event.board_x

    def test_increments_throw_count(self, tmp_path: Path) -> None:
        """Multiple detections produce sequentially numbered files."""
        dl = DiagnosticLogger(base_dir=str(tmp_path))
        dl.log_detection(_make_event())
        dl.log_detection(_make_event())

        assert len(list(dl.session_dir.glob("throw_001_*.json"))) == 1
        assert len(list(dl.session_dir.glob("throw_002_*.json"))) == 1

    def test_copies_existing_images(self, tmp_path: Path) -> None:
        """Annotated images are copied into the session directory."""
        # Create a fake image file
        img_dir = tmp_path / "images"
        img_dir.mkdir()
        img_file = img_dir / "cam0_annotated.jpg"
        img_file.write_bytes(b"fake image data")

        dl = DiagnosticLogger(base_dir=str(tmp_path / "diag"))
        event = _make_event(image_paths={"0": str(img_file)})
        dl.log_detection(event)

        copied = list(dl.session_dir.glob("throw_001_cam0_*.jpg"))
        assert len(copied) == 1
        assert copied[0].read_bytes() == b"fake image data"

    def test_warns_on_missing_image(self, tmp_path: Path) -> None:
        """Missing image files are skipped with a warning, JSON still written."""
        dl = DiagnosticLogger(base_dir=str(tmp_path))
        event = _make_event(image_paths={"0": "/nonexistent/cam0.jpg"})
        record = dl.log_detection(event)

        # JSON should still be written
        json_files = list(dl.session_dir.glob("throw_001_*.json"))
        assert len(json_files) == 1
        # No image files copied
        img_files = list(dl.session_dir.glob("*.jpg"))
        assert len(img_files) == 0
        # Record still returned
        assert record is not None


class TestDiagnosticLoggerSessionSummary:
    """Tests for DiagnosticLogger.write_session_summary()."""

    def test_empty_session_summary(self, tmp_path: Path) -> None:
        """Summary with zero throws produces valid JSON without division errors."""
        dl = DiagnosticLogger(base_dir=str(tmp_path))
        dl.write_session_summary()

        summary_path = dl.session_dir / "session_summary.json"
        assert summary_path.exists()

        with open(summary_path, "r") as fh:
            data = json.load(fh)
        assert data["total_throws"] == 0
        assert data["successful_detections"] == 0
        assert data["average_fusion_confidence"] == 0.0
        assert data["per_camera_stats"] == {}

    def test_summary_with_detections(self, tmp_path: Path) -> None:
        """Summary correctly aggregates multiple detections."""
        dl = DiagnosticLogger(base_dir=str(tmp_path))

        # Log two events with known values
        event1 = _make_event(
            board_x=0.0,
            board_y=0.0,
            cameras=[(0, 3.0, 4.0)],  # deviation = 5.0
            fusion_confidence=0.8,
        )
        event2 = _make_event(
            board_x=0.0,
            board_y=0.0,
            cameras=[(0, 6.0, 8.0)],  # deviation = 10.0
            fusion_confidence=0.6,
        )
        dl.log_detection(event1)
        dl.log_detection(event2)
        dl.write_session_summary()

        with open(dl.session_dir / "session_summary.json", "r") as fh:
            data = json.load(fh)

        assert data["total_throws"] == 2
        assert data["successful_detections"] == 2
        assert abs(data["average_fusion_confidence"] - 0.7) < 1e-6

        cam0 = data["per_camera_stats"]["0"]
        assert abs(cam0["mean_deviation_mm"] - 7.5) < 1e-6
        assert abs(cam0["max_deviation_mm"] - 10.0) < 1e-6
        # Mean deviation vector: mean(3,6)=4.5, mean(4,8)=6.0
        assert abs(cam0["mean_deviation_vector"]["dx_mm"] - 4.5) < 1e-6
        assert abs(cam0["mean_deviation_vector"]["dy_mm"] - 6.0) < 1e-6

    def test_successful_detections_counts_nonempty_cameras(self, tmp_path: Path) -> None:
        """successful_detections counts records with non-empty cameras_used."""
        dl = DiagnosticLogger(base_dir=str(tmp_path))

        event_with_cameras = _make_event(cameras=[(0, 1.0, 1.0)])
        dl.log_detection(event_with_cameras)

        # Create an event with empty cameras_used
        event_no_cameras = DartHitEvent(
            timestamp="2025-01-15T10:31:00.000000Z",
            board_x=0.0,
            board_y=0.0,
            radius=0.0,
            angle_rad=0.0,
            angle_deg=0.0,
            score=Score(base=0, multiplier=0, total=0, ring="out_of_bounds", sector=None),
            fusion_confidence=0.0,
            cameras_used=[],
            num_cameras=0,
            detections=[],
            image_paths={},
        )
        dl.log_detection(event_no_cameras)
        dl.write_session_summary()

        with open(dl.session_dir / "session_summary.json", "r") as fh:
            data = json.load(fh)

        assert data["total_throws"] == 2
        assert data["successful_detections"] == 1


# ---------------------------------------------------------------------------
# TestReport and TestReportGenerator tests
# ---------------------------------------------------------------------------


def _make_record(
    camera_data: list[CameraDiagnostic] | None = None,
) -> DetectionRecord:
    """Build a minimal DetectionRecord for testing."""
    return DetectionRecord(
        timestamp="2025-01-15T10:30:00.000000Z",
        board_x=0.0,
        board_y=0.0,
        radius=22.36,
        angle_deg=63.43,
        ring="triple",
        sector=20,
        score_total=60,
        score_base=20,
        score_multiplier=3,
        fusion_confidence=0.85,
        cameras_used=[0, 1],
        camera_data=camera_data or [],
        image_paths={},
    )


def _make_result(
    target_name: str = "T20",
    expected_score: int = 60,
    detected_score: int = 60,
    position_error_mm: float = 4.2,
    angular_error_deg: float = 1.8,
    ring_match: bool = True,
    sector_match: bool = True,
    score_match: bool = True,
    camera_data: list[CameraDiagnostic] | None = None,
) -> dict:
    """Build a per-throw result dict for TestReportGenerator."""
    return {
        "target_name": target_name,
        "expected_score": expected_score,
        "detected_score": detected_score,
        "position_error_mm": position_error_mm,
        "angular_error_deg": angular_error_deg,
        "ring_match": ring_match,
        "sector_match": sector_match,
        "score_match": score_match,
        "record": _make_record(camera_data=camera_data),
    }


class TestTestReportToFromDict:
    """Tests for TestReport JSON round-trip."""

    def test_round_trip(self) -> None:
        """to_dict/from_dict produces equivalent TestReport."""
        from src.diagnostics.test_report import TestReport

        report = TestReport(
            session_dir="data/diagnostics/Session_001_2025-01-15_10-30-00",
            overall={
                "total_throws": 2,
                "sector_match_rate": 50.0,
                "ring_match_rate": 100.0,
                "score_match_rate": 50.0,
                "mean_position_error_mm": 5.0,
                "max_position_error_mm": 8.0,
            },
            per_throw=[
                {
                    "target": "T20",
                    "expected_score": 60,
                    "detected_score": 60,
                    "position_error_mm": 4.2,
                    "angular_error_deg": 1.8,
                    "ring_match": True,
                    "sector_match": True,
                },
            ],
            per_camera={
                "0": {"mean_deviation_mm": 3.2, "max_deviation_mm": 7.1},
            },
        )

        data = report.to_dict()
        restored = TestReport.from_dict(data)

        assert restored.session_dir == report.session_dir
        assert restored.overall == report.overall
        assert restored.per_throw == report.per_throw
        assert restored.per_camera == report.per_camera


class TestTestReportPrintSummary:
    """Tests for TestReport.print_summary()."""

    def test_print_summary_ascii_only(self, capsys) -> None:
        """print_summary outputs ASCII-only text with correct values."""
        from src.diagnostics.test_report import TestReport

        report = TestReport(
            session_dir="data/diagnostics/Session_001",
            overall={
                "total_throws": 14,
                "sector_match_rate": 71.4,
                "ring_match_rate": 85.7,
                "score_match_rate": 64.3,
                "mean_position_error_mm": 8.5,
                "max_position_error_mm": 22.1,
            },
            per_throw=[],
            per_camera={},
        )
        report.print_summary()
        output = capsys.readouterr().out

        assert "=== Accuracy Test Report ===" in output
        assert "Total throws: 14" in output
        assert "Sector match rate: 71.4%" in output
        assert "Ring match rate: 85.7%" in output
        assert "Score match rate: 64.3%" in output
        assert "Mean position error: 8.5 mm" in output
        assert "Max position error: 22.1 mm" in output

        # Verify ASCII only
        assert all(ord(c) < 128 for c in output)


class TestTestReportGenerator:
    """Tests for TestReportGenerator.generate_report()."""

    def test_zero_throws(self, tmp_path: Path) -> None:
        """Zero-throw edge case: no division by zero, rates are 0."""
        from src.diagnostics.test_report import TestReportGenerator

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        report = TestReportGenerator.generate_report([], dl)

        assert report.overall["total_throws"] == 0
        assert report.overall["sector_match_rate"] == 0
        assert report.overall["ring_match_rate"] == 0
        assert report.overall["score_match_rate"] == 0
        assert report.overall["mean_position_error_mm"] == 0.0
        assert report.overall["max_position_error_mm"] == 0.0
        assert report.per_throw == []
        assert report.per_camera == {}

    def test_all_matches(self, tmp_path: Path) -> None:
        """All throws match: 100% rates."""
        from src.diagnostics.test_report import TestReportGenerator

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        results = [
            _make_result(position_error_mm=3.0),
            _make_result(position_error_mm=5.0),
        ]
        report = TestReportGenerator.generate_report(results, dl)

        assert report.overall["total_throws"] == 2
        assert report.overall["sector_match_rate"] == 100.0
        assert report.overall["ring_match_rate"] == 100.0
        assert report.overall["score_match_rate"] == 100.0
        assert report.overall["mean_position_error_mm"] == 4.0
        assert report.overall["max_position_error_mm"] == 5.0

    def test_no_matches(self, tmp_path: Path) -> None:
        """No throws match: 0% rates."""
        from src.diagnostics.test_report import TestReportGenerator

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        results = [
            _make_result(
                ring_match=False,
                sector_match=False,
                score_match=False,
                position_error_mm=10.0,
            ),
            _make_result(
                ring_match=False,
                sector_match=False,
                score_match=False,
                position_error_mm=20.0,
            ),
        ]
        report = TestReportGenerator.generate_report(results, dl)

        assert report.overall["sector_match_rate"] == 0.0
        assert report.overall["ring_match_rate"] == 0.0
        assert report.overall["score_match_rate"] == 0.0
        assert report.overall["mean_position_error_mm"] == 15.0
        assert report.overall["max_position_error_mm"] == 20.0

    def test_per_camera_stats(self, tmp_path: Path) -> None:
        """Per-camera deviation stats are computed correctly."""
        from src.diagnostics.test_report import TestReportGenerator

        cam_data = [
            CameraDiagnostic(
                camera_id=0, pixel_x=100, pixel_y=200,
                board_x=3.0, board_y=4.0, confidence=0.9,
                deviation_mm=5.0, deviation_dx=3.0, deviation_dy=4.0,
            ),
            CameraDiagnostic(
                camera_id=1, pixel_x=110, pixel_y=210,
                board_x=6.0, board_y=8.0, confidence=0.85,
                deviation_mm=10.0, deviation_dx=6.0, deviation_dy=8.0,
            ),
        ]

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        results = [_make_result(camera_data=cam_data)]
        report = TestReportGenerator.generate_report(results, dl)

        assert "0" in report.per_camera
        assert "1" in report.per_camera
        assert report.per_camera["0"]["mean_deviation_mm"] == 5.0
        assert report.per_camera["0"]["max_deviation_mm"] == 5.0
        assert report.per_camera["1"]["mean_deviation_mm"] == 10.0
        assert report.per_camera["1"]["max_deviation_mm"] == 10.0

    def test_per_throw_detail(self, tmp_path: Path) -> None:
        """Per-throw detail contains correct fields."""
        from src.diagnostics.test_report import TestReportGenerator

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        results = [
            _make_result(
                target_name="D5",
                expected_score=10,
                detected_score=5,
                position_error_mm=12.3,
                angular_error_deg=4.5,
                ring_match=False,
                sector_match=True,
            ),
        ]
        report = TestReportGenerator.generate_report(results, dl)

        assert len(report.per_throw) == 1
        t = report.per_throw[0]
        assert t["target"] == "D5"
        assert t["expected_score"] == 10
        assert t["detected_score"] == 5
        assert t["position_error_mm"] == 12.3
        assert t["angular_error_deg"] == 4.5
        assert t["ring_match"] is False
        assert t["sector_match"] is True


# ---------------------------------------------------------------------------
# AccuracyTestRunner tests
# ---------------------------------------------------------------------------


from src.calibration.board_geometry import BoardGeometry
from src.diagnostics.accuracy_test_runner import AccuracyTestRunner
from src.diagnostics.known_positions import (
    KnownPosition,
    build_known_positions,
    compute_angular_error,
    compute_position_error,
)
from src.diagnostics.test_report import TestReport


def _make_event_for_target(
    target: KnownPosition,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    ring: str | None = None,
    sector: int | None = -1,
    score_total: int | None = None,
) -> DartHitEvent:
    """Build a DartHitEvent positioned at a known target with optional offsets.

    Args:
        target: The KnownPosition to base the event on.
        offset_x: X offset from the target position in mm.
        offset_y: Y offset from the target position in mm.
        ring: Override ring classification. Defaults to target's expected_ring.
        sector: Override sector. Use -1 (default) to use target's expected_sector.
        score_total: Override total score. Defaults to target's expected_score.

    Returns:
        A DartHitEvent at the specified position.
    """
    bx = target.expected_x + offset_x
    by = target.expected_y + offset_y
    radius = math.sqrt(bx * bx + by * by)
    angle_rad = math.atan2(by, bx)
    if angle_rad < 0:
        angle_rad += 2 * math.pi
    angle_deg = math.degrees(angle_rad)

    eff_ring = ring if ring is not None else target.expected_ring
    eff_sector = target.expected_sector if sector == -1 else sector
    eff_score = score_total if score_total is not None else target.expected_score

    return DartHitEvent(
        timestamp="2025-01-15T10:30:00.000000Z",
        board_x=bx,
        board_y=by,
        radius=radius,
        angle_rad=angle_rad,
        angle_deg=angle_deg,
        score=Score(
            base=eff_score,
            multiplier=1,
            total=eff_score,
            ring=eff_ring,
            sector=eff_sector,
        ),
        fusion_confidence=0.9,
        cameras_used=[0],
        num_cameras=1,
        detections=[
            CameraDetection(
                camera_id=0,
                pixel_x=400.0,
                pixel_y=300.0,
                board_x=bx + 0.5,
                board_y=by + 0.5,
                confidence=0.9,
            ),
        ],
        image_paths={},
    )


class TestAccuracyTestRunnerRecordResult:
    """Tests for AccuracyTestRunner.record_result() comparison metrics."""

    def test_exact_hit_on_t20(self, tmp_path: Path) -> None:
        """Exact hit on T20: position_error ~0, all matches True.

        Validates: Requirements 5.4, 5.5, 5.6
        """
        bg = BoardGeometry()
        known = build_known_positions(bg)
        t20 = next(p for p in known if p.name == "T20")

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=[t20],
            diagnostic_logger=dl,
            score_calculator=None,
        )

        event = _make_event_for_target(t20)
        runner.record_result(event)

        assert len(runner.results) == 1
        result = runner.results[0]

        assert result["position_error_mm"] == pytest.approx(0.0, abs=1e-6)
        assert result["ring_match"] is True
        assert result["sector_match"] is True
        assert result["score_match"] is True
        assert result["target_name"] == "T20"
        assert result["expected_score"] == 60

    def test_mismatched_detection_d5_vs_t20(self, tmp_path: Path) -> None:
        """Event scores D5 but target is T20: ring_match=False, score_match=False.

        Validates: Requirements 5.4, 5.6
        """
        bg = BoardGeometry()
        known = build_known_positions(bg)
        t20 = next(p for p in known if p.name == "T20")

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=[t20],
            diagnostic_logger=dl,
            score_calculator=None,
        )

        event = _make_event_for_target(
            t20,
            ring="double",
            sector=5,
            score_total=10,
        )
        runner.record_result(event)

        result = runner.results[0]
        assert result["ring_match"] is False
        assert result["sector_match"] is False
        assert result["score_match"] is False
        assert result["detected_score"] == 10
        assert result["expected_score"] == 60

    def test_position_error_with_offset(self, tmp_path: Path) -> None:
        """Offset of (3, 4) mm gives position_error = 5.0 mm.

        Validates: Requirements 5.4
        """
        bg = BoardGeometry()
        known = build_known_positions(bg)
        t20 = next(p for p in known if p.name == "T20")

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=[t20],
            diagnostic_logger=dl,
            score_calculator=None,
        )

        event = _make_event_for_target(t20, offset_x=3.0, offset_y=4.0)
        runner.record_result(event)

        result = runner.results[0]
        assert result["position_error_mm"] == pytest.approx(5.0, abs=0.1)

    def test_angular_error_computed(self, tmp_path: Path) -> None:
        """Angular error is computed and stored in the result.

        Validates: Requirements 5.5
        """
        bg = BoardGeometry()
        known = build_known_positions(bg)
        t20 = next(p for p in known if p.name == "T20")

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=[t20],
            diagnostic_logger=dl,
            score_calculator=None,
        )

        event = _make_event_for_target(t20)
        runner.record_result(event)

        result = runner.results[0]
        assert "angular_error_deg" in result
        # Exact hit should have very small angular error
        assert result["angular_error_deg"] == pytest.approx(0.0, abs=0.5)


class TestAccuracyTestRunnerIsComplete:
    """Tests for AccuracyTestRunner.is_complete() state transitions."""

    def test_not_complete_initially(self, tmp_path: Path) -> None:
        """Runner with positions starts as not complete."""
        bg = BoardGeometry()
        known = build_known_positions(bg)

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=known,
            diagnostic_logger=dl,
            score_calculator=None,
        )

        assert runner.is_complete() is False

    def test_complete_after_all_positions(self, tmp_path: Path) -> None:
        """Runner becomes complete after recording all positions."""
        bg = BoardGeometry()
        known = build_known_positions(bg)
        # Use only 2 positions for a quick test
        subset = known[:2]

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=subset,
            diagnostic_logger=dl,
            score_calculator=None,
        )

        for pos in subset:
            assert runner.is_complete() is False
            event = _make_event_for_target(pos)
            runner.record_result(event)

        assert runner.is_complete() is True

    def test_complete_with_empty_positions(self, tmp_path: Path) -> None:
        """Runner with no positions is immediately complete."""
        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=[],
            diagnostic_logger=dl,
            score_calculator=None,
        )

        assert runner.is_complete() is True

    def test_get_current_target_returns_none_when_complete(self, tmp_path: Path) -> None:
        """get_current_target returns None after all positions tested."""
        bg = BoardGeometry()
        known = build_known_positions(bg)
        subset = [known[0]]

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=subset,
            diagnostic_logger=dl,
            score_calculator=None,
        )

        event = _make_event_for_target(subset[0])
        runner.record_result(event)

        assert runner.get_current_target() is None


class TestAccuracyTestRunnerGenerateReport:
    """Tests for AccuracyTestRunner.generate_report()."""

    def test_report_type_and_total_throws(self, tmp_path: Path) -> None:
        """generate_report produces a valid TestReport with correct total_throws.

        Validates: Requirements 5.4, 5.5, 5.6
        """
        bg = BoardGeometry()
        known = build_known_positions(bg)
        subset = known[:3]

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=subset,
            diagnostic_logger=dl,
            score_calculator=None,
        )

        for pos in subset:
            event = _make_event_for_target(pos)
            runner.record_result(event)

        report = runner.generate_report()

        assert isinstance(report, TestReport)
        assert report.overall["total_throws"] == 3
        assert len(report.per_throw) == 3

    def test_report_with_zero_throws(self, tmp_path: Path) -> None:
        """generate_report with no results produces zero-throw report."""
        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=[],
            diagnostic_logger=dl,
            score_calculator=None,
        )

        report = runner.generate_report()

        assert isinstance(report, TestReport)
        assert report.overall["total_throws"] == 0

    def test_report_perfect_accuracy(self, tmp_path: Path) -> None:
        """All exact hits produce 100% match rates."""
        bg = BoardGeometry()
        known = build_known_positions(bg)
        # Use T20 and D5 (positions with sectors)
        t20 = next(p for p in known if p.name == "T20")
        d5 = next(p for p in known if p.name == "D5")
        subset = [t20, d5]

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=subset,
            diagnostic_logger=dl,
            score_calculator=None,
        )

        for pos in subset:
            event = _make_event_for_target(pos)
            runner.record_result(event)

        report = runner.generate_report()

        assert report.overall["sector_match_rate"] == 100.0
        assert report.overall["ring_match_rate"] == 100.0
        assert report.overall["score_match_rate"] == 100.0


class TestAccuracyTestRunnerPositionFilter:
    """Tests for AccuracyTestRunner position_filter parameter."""

    def test_filter_selects_subset(self, tmp_path: Path) -> None:
        """position_filter limits which positions are tested."""
        bg = BoardGeometry()
        known = build_known_positions(bg)

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=known,
            diagnostic_logger=dl,
            score_calculator=None,
            position_filter=["T20", "D5"],
        )

        assert len(runner.positions) == 2
        names = {p.name for p in runner.positions}
        assert names == {"T20", "D5"}

    def test_filter_none_uses_all(self, tmp_path: Path) -> None:
        """No filter uses all 14 known positions."""
        bg = BoardGeometry()
        known = build_known_positions(bg)

        dl = DiagnosticLogger(base_dir=str(tmp_path))
        runner = AccuracyTestRunner(
            known_positions=known,
            diagnostic_logger=dl,
            score_calculator=None,
            position_filter=None,
        )

        assert len(runner.positions) == 14


# ---------------------------------------------------------------------------
# CLI flag validation tests
# ---------------------------------------------------------------------------


class TestCLIDiagnosticsFlags:
    """Tests for --diagnostics and --accuracy-test CLI flag validation."""

    def _build_parser(self):
        """Build the same argparse parser as main.py's main()."""
        import argparse

        parser = argparse.ArgumentParser(description='ARU-DART Camera Capture')
        parser.add_argument('--config', default='config.toml')
        parser.add_argument('--dev-mode', action='store_true')
        parser.add_argument('--show-histogram', action='store_true')
        parser.add_argument('--manual-test', action='store_true')
        parser.add_argument('--record-mode', action='store_true')
        parser.add_argument('--single-camera', type=int, choices=[0, 1, 2])
        parser.add_argument('--calibrate', action='store_true')
        parser.add_argument('--calibrate-intrinsic', action='store_true')
        parser.add_argument('--verify-calibration', action='store_true')
        parser.add_argument('--single-dart-test', action='store_true')
        parser.add_argument('--manual-dart-test', action='store_true')
        parser.add_argument('--diagnostics', action='store_true',
                            help='Enable diagnostic logging (requires --manual-dart-test or --single-dart-test)')
        parser.add_argument('--accuracy-test', action='store_true',
                            help='Run accuracy test mode (implies --diagnostics)')
        return parser

    def _parse_and_validate(self, args_list):
        """Parse args and apply the same validation as main.py."""
        parser = self._build_parser()
        args = parser.parse_args(args_list)

        if args.accuracy_test:
            args.diagnostics = True

        if args.diagnostics and not (args.manual_dart_test or args.single_dart_test or args.accuracy_test):
            parser.error("--diagnostics requires --manual-dart-test, --single-dart-test, or --accuracy-test")

        return args

    def test_diagnostics_with_manual_dart_test(self) -> None:
        """--diagnostics with --manual-dart-test is valid."""
        args = self._parse_and_validate(['--diagnostics', '--manual-dart-test'])
        assert args.diagnostics is True
        assert args.manual_dart_test is True

    def test_diagnostics_with_single_dart_test(self) -> None:
        """--diagnostics with --single-dart-test is valid."""
        args = self._parse_and_validate(['--diagnostics', '--single-dart-test'])
        assert args.diagnostics is True
        assert args.single_dart_test is True

    def test_diagnostics_alone_errors(self) -> None:
        """--diagnostics without a test mode flag exits with error."""
        with pytest.raises(SystemExit):
            self._parse_and_validate(['--diagnostics'])

    def test_accuracy_test_implies_diagnostics(self) -> None:
        """--accuracy-test sets diagnostics to True."""
        args = self._parse_and_validate(['--accuracy-test'])
        assert args.accuracy_test is True
        assert args.diagnostics is True

    def test_accuracy_test_standalone(self) -> None:
        """--accuracy-test alone is valid (no error)."""
        args = self._parse_and_validate(['--accuracy-test'])
        assert args.accuracy_test is True

    def test_no_flags_no_diagnostics(self) -> None:
        """No flags: diagnostics and accuracy_test are False."""
        args = self._parse_and_validate([])
        assert args.diagnostics is False
        assert args.accuracy_test is False
