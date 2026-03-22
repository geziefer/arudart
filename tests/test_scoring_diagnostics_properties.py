"""
Property-based tests for scoring diagnostics.

Tests:
- Property 1: DetectionRecord preserves DartHitEvent fields
- (Additional properties will be added by later tasks)

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 7.1, 7.2**
"""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.fusion.dart_hit_event import CameraDetection, DartHitEvent, Score
from src.diagnostics.detection_record import CameraDiagnostic, DetectionRecord


# ---------------------------------------------------------------------------
# Reusable strategies
# ---------------------------------------------------------------------------

VALID_RING_NAMES = [
    "bull",
    "single_bull",
    "triple",
    "double",
    "single",
    "out_of_bounds",
]


@st.composite
def score_strategy(draw):
    """Generate a random valid Score object."""
    base = draw(st.integers(min_value=0, max_value=20))
    multiplier = draw(st.integers(min_value=0, max_value=3))
    total = base * multiplier
    ring = draw(st.sampled_from(VALID_RING_NAMES))
    sector = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=20)))
    return Score(
        base=base,
        multiplier=multiplier,
        total=total,
        ring=ring,
        sector=sector,
    )


@st.composite
def camera_detection_strategy(draw):
    """Generate a random valid CameraDetection object."""
    camera_id = draw(st.integers(min_value=0, max_value=2))
    pixel_x = draw(st.floats(min_value=0, max_value=1280, allow_nan=False, allow_infinity=False))
    pixel_y = draw(st.floats(min_value=0, max_value=720, allow_nan=False, allow_infinity=False))
    board_x = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    board_y = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    confidence = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    return CameraDetection(
        camera_id=camera_id,
        pixel_x=pixel_x,
        pixel_y=pixel_y,
        board_x=board_x,
        board_y=board_y,
        confidence=confidence,
    )


@st.composite
def dart_hit_event_strategy(draw):
    """Generate a random valid DartHitEvent with 1-3 camera detections."""
    timestamp = draw(st.from_regex(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z",
        fullmatch=True,
    ))
    board_x = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    board_y = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    radius = draw(st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False))
    angle_rad = draw(st.floats(min_value=0, max_value=2 * math.pi, allow_nan=False, allow_infinity=False))
    angle_deg = draw(st.floats(min_value=0, max_value=360, allow_nan=False, allow_infinity=False))
    score = draw(score_strategy())
    fusion_confidence = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))

    num_cameras = draw(st.integers(min_value=1, max_value=3))
    cameras_used = draw(
        st.lists(
            st.integers(min_value=0, max_value=2),
            min_size=num_cameras,
            max_size=num_cameras,
            unique=True,
        )
    )

    detections = draw(
        st.lists(camera_detection_strategy(), min_size=1, max_size=3)
    )

    image_paths = draw(
        st.dictionaries(
            keys=st.sampled_from(["0", "1", "2"]),
            values=st.from_regex(r"data/throws/cam[012]_annotated_\d{8}_\d{6}\.jpg", fullmatch=True),
            min_size=0,
            max_size=3,
        )
    )

    return DartHitEvent(
        timestamp=timestamp,
        board_x=board_x,
        board_y=board_y,
        radius=radius,
        angle_rad=angle_rad,
        angle_deg=angle_deg,
        score=score,
        fusion_confidence=fusion_confidence,
        cameras_used=cameras_used,
        num_cameras=num_cameras,
        detections=detections,
        image_paths=image_paths,
    )


# ---------------------------------------------------------------------------
# Property 1: DetectionRecord preserves DartHitEvent fields
# ---------------------------------------------------------------------------


class TestDetectionRecordPreservesDartHitEventFields:
    """
    Property 1: DetectionRecord preserves DartHitEvent fields

    For any valid DartHitEvent with N camera detections, the DetectionRecord
    created via from_dart_hit_event() should contain the same fused coordinates,
    polar coordinates, classification, score, fusion_confidence, cameras_used,
    and N CameraDiagnostic entries whose camera_id, pixel coords, board coords,
    and confidence match the source detections.

    Feature: scoring-diagnostics, Property 1: DetectionRecord preserves DartHitEvent fields

    **Validates: Requirements 1.1, 1.2, 1.3**
    """

    FLOAT_TOLERANCE = 1e-9

    def _assert_floats_close(self, a: float, b: float, label: str) -> None:
        """Assert two floats are equal within tolerance."""
        assert abs(a - b) < self.FLOAT_TOLERANCE, (
            f"{label}: {a} != {b} (diff={abs(a - b)})"
        )

    @given(event=dart_hit_event_strategy())
    @settings(max_examples=100, deadline=None)
    def test_detection_record_preserves_dart_hit_event_fields(self, event: DartHitEvent) -> None:
        """
        Feature: scoring-diagnostics, Property 1: DetectionRecord preserves DartHitEvent fields

        Create a DetectionRecord from a random DartHitEvent and verify all
        source fields are preserved.

        **Validates: Requirements 1.1, 1.2, 1.3**
        """
        record = DetectionRecord.from_dart_hit_event(event)

        # --- Fused coordinates (Req 1.2) ---
        self._assert_floats_close(event.board_x, record.board_x, "board_x")
        self._assert_floats_close(event.board_y, record.board_y, "board_y")

        # --- Polar coordinates (Req 1.3) ---
        self._assert_floats_close(event.radius, record.radius, "radius")
        self._assert_floats_close(event.angle_deg, record.angle_deg, "angle_deg")

        # --- Classification (Req 1.3) ---
        assert event.score.ring == record.ring, (
            f"ring: {event.score.ring} != {record.ring}"
        )
        assert event.score.sector == record.sector, (
            f"sector: {event.score.sector} != {record.sector}"
        )

        # --- Score (Req 1.3) ---
        assert event.score.base == record.score_base, (
            f"score_base: {event.score.base} != {record.score_base}"
        )
        assert event.score.multiplier == record.score_multiplier, (
            f"score_multiplier: {event.score.multiplier} != {record.score_multiplier}"
        )
        assert event.score.total == record.score_total, (
            f"score_total: {event.score.total} != {record.score_total}"
        )

        # --- Fusion metadata (Req 1.2) ---
        self._assert_floats_close(
            event.fusion_confidence, record.fusion_confidence, "fusion_confidence"
        )
        assert event.cameras_used == record.cameras_used, (
            f"cameras_used: {event.cameras_used} != {record.cameras_used}"
        )

        # --- Per-camera diagnostics (Req 1.1) ---
        assert len(event.detections) == len(record.camera_data), (
            f"camera_data count: {len(event.detections)} != {len(record.camera_data)}"
        )
        for det, diag in zip(event.detections, record.camera_data):
            assert det.camera_id == diag.camera_id, (
                f"camera_id: {det.camera_id} != {diag.camera_id}"
            )
            self._assert_floats_close(det.pixel_x, diag.pixel_x, "pixel_x")
            self._assert_floats_close(det.pixel_y, diag.pixel_y, "pixel_y")
            self._assert_floats_close(det.board_x, diag.board_x, "board_x (camera)")
            self._assert_floats_close(det.board_y, diag.board_y, "board_y (camera)")
            self._assert_floats_close(det.confidence, diag.confidence, "confidence")


# ---------------------------------------------------------------------------
# Additional strategies for Property 2
# ---------------------------------------------------------------------------


@st.composite
def camera_diagnostic_strategy(draw):
    """Generate a random valid CameraDiagnostic object."""
    camera_id = draw(st.integers(min_value=0, max_value=2))
    pixel_x = draw(st.floats(min_value=0, max_value=1280, allow_nan=False, allow_infinity=False))
    pixel_y = draw(st.floats(min_value=0, max_value=720, allow_nan=False, allow_infinity=False))
    board_x = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    board_y = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    confidence = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    deviation_mm = draw(st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False))
    deviation_dx = draw(st.floats(min_value=-50, max_value=50, allow_nan=False, allow_infinity=False))
    deviation_dy = draw(st.floats(min_value=-50, max_value=50, allow_nan=False, allow_infinity=False))
    return CameraDiagnostic(
        camera_id=camera_id,
        pixel_x=pixel_x,
        pixel_y=pixel_y,
        board_x=board_x,
        board_y=board_y,
        confidence=confidence,
        deviation_mm=deviation_mm,
        deviation_dx=deviation_dx,
        deviation_dy=deviation_dy,
    )


@st.composite
def detection_record_strategy(draw):
    """Generate a random valid DetectionRecord object."""
    timestamp = draw(st.from_regex(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z",
        fullmatch=True,
    ))
    board_x = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    board_y = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    radius = draw(st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False))
    angle_deg = draw(st.floats(min_value=0, max_value=360, allow_nan=False, allow_infinity=False))
    ring = draw(st.sampled_from(VALID_RING_NAMES))
    sector = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=20)))
    score_base = draw(st.integers(min_value=0, max_value=20))
    score_multiplier = draw(st.integers(min_value=0, max_value=3))
    score_total = score_base * score_multiplier
    fusion_confidence = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))

    cameras_used = draw(
        st.lists(
            st.integers(min_value=0, max_value=2),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )

    camera_data = draw(
        st.lists(camera_diagnostic_strategy(), min_size=1, max_size=3)
    )

    image_paths = draw(
        st.dictionaries(
            keys=st.sampled_from(["0", "1", "2"]),
            values=st.from_regex(
                r"data/throws/cam[012]_annotated_\d{8}_\d{6}\.jpg",
                fullmatch=True,
            ),
            min_size=0,
            max_size=3,
        )
    )

    return DetectionRecord(
        timestamp=timestamp,
        board_x=board_x,
        board_y=board_y,
        radius=radius,
        angle_deg=angle_deg,
        ring=ring,
        sector=sector,
        score_total=score_total,
        score_base=score_base,
        score_multiplier=score_multiplier,
        fusion_confidence=fusion_confidence,
        cameras_used=cameras_used,
        camera_data=camera_data,
        image_paths=image_paths,
    )


# ---------------------------------------------------------------------------
# Property 2: DetectionRecord JSON round-trip
# ---------------------------------------------------------------------------


class TestDetectionRecordJsonRoundTrip:
    """
    Property 2: DetectionRecord JSON round-trip

    For any valid DetectionRecord, serializing it with to_dict() and then
    deserializing with from_dict() should produce an equivalent DetectionRecord
    (all fields equal within floating-point tolerance).

    Feature: scoring-diagnostics, Property 2: DetectionRecord JSON round-trip

    **Validates: Requirements 1.4, 1.5**
    """

    FLOAT_TOLERANCE = 1e-9

    def _assert_floats_close(self, a: float, b: float, label: str) -> None:
        """Assert two floats are equal within tolerance."""
        assert abs(a - b) < self.FLOAT_TOLERANCE, (
            f"{label}: {a} != {b} (diff={abs(a - b)})"
        )

    def _assert_camera_diagnostic_equal(
        self, original: CameraDiagnostic, restored: CameraDiagnostic, index: int
    ) -> None:
        """Assert two CameraDiagnostic objects are equivalent within tolerance."""
        assert original.camera_id == restored.camera_id, (
            f"camera_data[{index}].camera_id: {original.camera_id} != {restored.camera_id}"
        )
        self._assert_floats_close(original.pixel_x, restored.pixel_x, f"camera_data[{index}].pixel_x")
        self._assert_floats_close(original.pixel_y, restored.pixel_y, f"camera_data[{index}].pixel_y")
        self._assert_floats_close(original.board_x, restored.board_x, f"camera_data[{index}].board_x")
        self._assert_floats_close(original.board_y, restored.board_y, f"camera_data[{index}].board_y")
        self._assert_floats_close(original.confidence, restored.confidence, f"camera_data[{index}].confidence")
        self._assert_floats_close(original.deviation_mm, restored.deviation_mm, f"camera_data[{index}].deviation_mm")
        self._assert_floats_close(original.deviation_dx, restored.deviation_dx, f"camera_data[{index}].deviation_dx")
        self._assert_floats_close(original.deviation_dy, restored.deviation_dy, f"camera_data[{index}].deviation_dy")

    @given(record=detection_record_strategy())
    @settings(max_examples=100, deadline=None)
    def test_detection_record_json_round_trip(self, record: DetectionRecord) -> None:
        """
        Feature: scoring-diagnostics, Property 2: DetectionRecord JSON round-trip

        Serialize a random DetectionRecord with to_dict(), deserialize with
        from_dict(), and verify all fields match within float tolerance.

        **Validates: Requirements 1.4, 1.5**
        """
        data = record.to_dict()
        restored = DetectionRecord.from_dict(data)

        # --- Timestamp ---
        assert record.timestamp == restored.timestamp, (
            f"timestamp: {record.timestamp} != {restored.timestamp}"
        )

        # --- Fused position ---
        self._assert_floats_close(record.board_x, restored.board_x, "board_x")
        self._assert_floats_close(record.board_y, restored.board_y, "board_y")

        # --- Polar coordinates ---
        self._assert_floats_close(record.radius, restored.radius, "radius")
        self._assert_floats_close(record.angle_deg, restored.angle_deg, "angle_deg")

        # --- Classification ---
        assert record.ring == restored.ring, (
            f"ring: {record.ring} != {restored.ring}"
        )
        assert record.sector == restored.sector, (
            f"sector: {record.sector} != {restored.sector}"
        )

        # --- Score ---
        assert record.score_total == restored.score_total, (
            f"score_total: {record.score_total} != {restored.score_total}"
        )
        assert record.score_base == restored.score_base, (
            f"score_base: {record.score_base} != {restored.score_base}"
        )
        assert record.score_multiplier == restored.score_multiplier, (
            f"score_multiplier: {record.score_multiplier} != {restored.score_multiplier}"
        )

        # --- Fusion metadata ---
        self._assert_floats_close(
            record.fusion_confidence, restored.fusion_confidence, "fusion_confidence"
        )
        assert record.cameras_used == restored.cameras_used, (
            f"cameras_used: {record.cameras_used} != {restored.cameras_used}"
        )

        # --- Camera data ---
        assert len(record.camera_data) == len(restored.camera_data), (
            f"camera_data count: {len(record.camera_data)} != {len(restored.camera_data)}"
        )
        for i, (orig_cam, rest_cam) in enumerate(
            zip(record.camera_data, restored.camera_data)
        ):
            self._assert_camera_diagnostic_equal(orig_cam, rest_cam, i)

        # --- Image paths ---
        assert record.image_paths == restored.image_paths, (
            f"image_paths: {record.image_paths} != {restored.image_paths}"
        )

    @given(cam_diag=camera_diagnostic_strategy())
    @settings(max_examples=100, deadline=None)
    def test_camera_diagnostic_json_round_trip(self, cam_diag: CameraDiagnostic) -> None:
        """
        Feature: scoring-diagnostics, Property 2: CameraDiagnostic JSON round-trip

        Serialize a random CameraDiagnostic with to_dict(), deserialize with
        from_dict(), and verify all fields match within float tolerance.

        **Validates: Requirements 1.4, 1.5**
        """
        data = cam_diag.to_dict()
        restored = CameraDiagnostic.from_dict(data)

        self._assert_camera_diagnostic_equal(cam_diag, restored, 0)


# ---------------------------------------------------------------------------
# Property 3: Camera deviation vector consistency
# ---------------------------------------------------------------------------


class TestCameraDeviationVectorConsistency:
    """
    Property 3: Camera deviation vector consistency

    For any DetectionRecord created from a DartHitEvent, each CameraDiagnostic
    entry should have deviation_dx == camera.board_x - fused_board_x,
    deviation_dy == camera.board_y - fused_board_y, and
    deviation_mm == sqrt(deviation_dx^2 + deviation_dy^2).

    Feature: scoring-diagnostics, Property 3: Camera deviation vector consistency

    **Validates: Requirements 7.1, 7.2**
    """

    FLOAT_TOLERANCE = 1e-9

    def _assert_floats_close(self, a: float, b: float, label: str) -> None:
        """Assert two floats are equal within tolerance."""
        assert abs(a - b) < self.FLOAT_TOLERANCE, (
            f"{label}: {a} != {b} (diff={abs(a - b)})"
        )

    @given(event=dart_hit_event_strategy())
    @settings(max_examples=100, deadline=None)
    def test_camera_deviation_vector_consistency(self, event: DartHitEvent) -> None:
        """
        Feature: scoring-diagnostics, Property 3: Camera deviation vector consistency

        Create a DetectionRecord from a random DartHitEvent and verify that
        each camera diagnostic has consistent deviation components and magnitude.

        **Validates: Requirements 7.1, 7.2**
        """
        record = DetectionRecord.from_dart_hit_event(event)

        for i, diag in enumerate(record.camera_data):
            expected_dx = diag.board_x - record.board_x
            expected_dy = diag.board_y - record.board_y
            expected_deviation_mm = math.sqrt(expected_dx ** 2 + expected_dy ** 2)

            self._assert_floats_close(
                diag.deviation_dx, expected_dx,
                f"camera_data[{i}].deviation_dx",
            )
            self._assert_floats_close(
                diag.deviation_dy, expected_dy,
                f"camera_data[{i}].deviation_dy",
            )
            self._assert_floats_close(
                diag.deviation_mm, expected_deviation_mm,
                f"camera_data[{i}].deviation_mm",
            )


# ---------------------------------------------------------------------------
# Property 4: Session summary aggregation correctness
# ---------------------------------------------------------------------------

import json
import tempfile


class TestSessionSummaryAggregationCorrectness:
    """
    Property 4: Session summary aggregation correctness

    For any sequence of DartHitEvent objects logged to a DiagnosticLogger,
    the session summary should report total_throws equal to the count of
    records, successful_detections equal to the count of records with
    non-empty cameras_used, average_fusion_confidence equal to the mean of
    all records' fusion_confidence values, and per-camera mean/max deviation
    and mean deviation vector matching the values computed from the individual
    camera diagnostics across all records.

    Feature: scoring-diagnostics, Property 4: Session summary aggregation correctness

    **Validates: Requirements 2.4, 7.3**
    """

    FLOAT_TOLERANCE = 1e-5

    def _assert_floats_close(self, a: float, b: float, label: str) -> None:
        """Assert two floats are equal within tolerance."""
        assert abs(a - b) < self.FLOAT_TOLERANCE, (
            f"{label}: {a} != {b} (diff={abs(a - b)})"
        )

    @given(events=st.lists(dart_hit_event_strategy(), min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_session_summary_aggregation_correctness(self, events: list) -> None:
        """
        Feature: scoring-diagnostics, Property 4: Session summary aggregation correctness

        Generate random DartHitEvent sequences, feed to DiagnosticLogger,
        verify session summary aggregates match manual computation.

        **Validates: Requirements 2.4, 7.3**
        """
        from src.diagnostics.diagnostic_logger import DiagnosticLogger

        with tempfile.TemporaryDirectory() as tmp_dir:
            logger = DiagnosticLogger(base_dir=tmp_dir)

            # Feed all events through the logger
            records = []
            for event in events:
                record = logger.log_detection(event)
                records.append(record)

            # Write and read the session summary
            logger.write_session_summary()
            summary_path = logger.session_dir / "session_summary.json"
            with open(summary_path, "r", encoding="utf-8") as fh:
                summary = json.load(fh)

            # --- Verify total_throws ---
            assert summary["total_throws"] == len(events), (
                f"total_throws: {summary['total_throws']} != {len(events)}"
            )

            # --- Verify successful_detections ---
            expected_successful = sum(
                1 for e in events if len(e.cameras_used) > 0
            )
            assert summary["successful_detections"] == expected_successful, (
                f"successful_detections: {summary['successful_detections']} "
                f"!= {expected_successful}"
            )

            # --- Verify average_fusion_confidence ---
            expected_avg_conf = sum(
                e.fusion_confidence for e in events
            ) / len(events)
            self._assert_floats_close(
                summary["average_fusion_confidence"],
                round(expected_avg_conf, 6),
                "average_fusion_confidence",
            )

            # --- Verify per-camera stats ---
            # Manually compute per-camera deviations from the records
            camera_deviations: dict[int, list[tuple[float, float, float]]] = {}
            for record in records:
                for cam in record.camera_data:
                    if cam.camera_id not in camera_deviations:
                        camera_deviations[cam.camera_id] = []
                    camera_deviations[cam.camera_id].append(
                        (cam.deviation_mm, cam.deviation_dx, cam.deviation_dy)
                    )

            per_cam = summary["per_camera_stats"]

            # Verify same set of camera IDs
            expected_cam_ids = {str(cid) for cid in camera_deviations}
            actual_cam_ids = set(per_cam.keys())
            assert actual_cam_ids == expected_cam_ids, (
                f"camera IDs: {actual_cam_ids} != {expected_cam_ids}"
            )

            for cam_id_str, devs in sorted(
                ((str(k), v) for k, v in camera_deviations.items())
            ):
                n = len(devs)
                expected_mean_dev = sum(d[0] for d in devs) / n
                expected_max_dev = max(d[0] for d in devs)
                expected_mean_dx = sum(d[1] for d in devs) / n
                expected_mean_dy = sum(d[2] for d in devs) / n

                cam_stats = per_cam[cam_id_str]

                self._assert_floats_close(
                    cam_stats["mean_deviation_mm"],
                    round(expected_mean_dev, 6),
                    f"cam {cam_id_str} mean_deviation_mm",
                )
                self._assert_floats_close(
                    cam_stats["max_deviation_mm"],
                    round(expected_max_dev, 6),
                    f"cam {cam_id_str} max_deviation_mm",
                )
                self._assert_floats_close(
                    cam_stats["mean_deviation_vector"]["dx_mm"],
                    round(expected_mean_dx, 6),
                    f"cam {cam_id_str} mean_deviation_vector.dx_mm",
                )
                self._assert_floats_close(
                    cam_stats["mean_deviation_vector"]["dy_mm"],
                    round(expected_mean_dy, 6),
                    f"cam {cam_id_str} mean_deviation_vector.dy_mm",
                )


# ---------------------------------------------------------------------------
# Property 5: Known position coordinates match BoardGeometry
# ---------------------------------------------------------------------------

from src.diagnostics.known_positions import (
    KnownPosition,
    build_known_positions,
    compute_angular_error,
    compute_position_error,
)
from src.calibration.board_geometry import BoardGeometry


class TestKnownPositionCoordinatesMatchBoardGeometry:
    """
    Property 5: Known position coordinates match BoardGeometry

    For each known position in the catalog, verify that the expected board
    coordinates match the values computed from BoardGeometry. Positions with
    a sector and ring in (triple, double, single) should match
    board_geometry.get_board_coords(sector, ring_type). SS (small single)
    positions should use the midpoint radius
    (SINGLE_BULL_RADIUS + TRIPLE_RING_INNER_RADIUS) / 2 at the sector angle.
    DB should be (0, 0). SB should be at the midpoint of the bull ring at
    sector 20 angle.

    Feature: scoring-diagnostics, Property 5: Known position coordinates match BoardGeometry

    **Validates: Requirements 4.2, 4.3**
    """

    FLOAT_TOLERANCE = 1e-9

    def _assert_floats_close(self, a: float, b: float, label: str) -> None:
        """Assert two floats are equal within tolerance."""
        assert abs(a - b) < self.FLOAT_TOLERANCE, (
            f"{label}: {a} != {b} (diff={abs(a - b)})"
        )

    def test_known_position_coordinates_match_board_geometry(self) -> None:
        """
        Feature: scoring-diagnostics, Property 5: Known position coordinates match BoardGeometry

        For each of the 14 known positions, verify expected coordinates match
        the values computed from BoardGeometry methods.

        **Validates: Requirements 4.2, 4.3**
        """
        bg = BoardGeometry()
        positions = build_known_positions(bg)

        # Should have exactly 14 positions
        assert len(positions) == 14, f"Expected 14 positions, got {len(positions)}"

        # Map ring types used in known_positions to get_board_coords ring_type
        ring_to_board_coords_type = {
            "triple": "triple",
            "double": "double",
            "single": "single",  # big single
        }

        for pos in positions:
            if pos.name == "DB":
                # Double bull: must be at origin
                self._assert_floats_close(pos.expected_x, 0.0, f"{pos.name} expected_x")
                self._assert_floats_close(pos.expected_y, 0.0, f"{pos.name} expected_y")

            elif pos.name == "SB":
                # Single bull: midpoint of bull ring at sector 20 angle
                sb_radius = (
                    BoardGeometry.DOUBLE_BULL_RADIUS + BoardGeometry.SINGLE_BULL_RADIUS
                ) / 2
                sb_angle = bg.get_sector_angle(20)
                expected_x = sb_radius * math.cos(sb_angle)
                expected_y = sb_radius * math.sin(sb_angle)
                self._assert_floats_close(pos.expected_x, expected_x, f"{pos.name} expected_x")
                self._assert_floats_close(pos.expected_y, expected_y, f"{pos.name} expected_y")

            elif pos.name.startswith("SS"):
                # Small single: radius = (SINGLE_BULL_RADIUS + TRIPLE_RING_INNER_RADIUS) / 2
                assert pos.expected_sector is not None, f"{pos.name} must have a sector"
                ss_radius = (
                    BoardGeometry.SINGLE_BULL_RADIUS + BoardGeometry.TRIPLE_RING_INNER_RADIUS
                ) / 2
                ss_angle = bg.get_sector_angle(pos.expected_sector)
                expected_x = ss_radius * math.cos(ss_angle)
                expected_y = ss_radius * math.sin(ss_angle)
                self._assert_floats_close(pos.expected_x, expected_x, f"{pos.name} expected_x")
                self._assert_floats_close(pos.expected_y, expected_y, f"{pos.name} expected_y")

            else:
                # T, D, BS positions: verify against board_geometry.get_board_coords
                assert pos.expected_sector is not None, f"{pos.name} must have a sector"
                board_ring_type = ring_to_board_coords_type.get(pos.expected_ring)
                assert board_ring_type is not None, (
                    f"{pos.name}: unexpected ring '{pos.expected_ring}'"
                )
                coords = bg.get_board_coords(pos.expected_sector, board_ring_type)
                assert coords is not None, (
                    f"{pos.name}: get_board_coords({pos.expected_sector}, "
                    f"'{board_ring_type}') returned None"
                )
                expected_x, expected_y = coords
                self._assert_floats_close(
                    pos.expected_x, expected_x, f"{pos.name} expected_x"
                )
                self._assert_floats_close(
                    pos.expected_y, expected_y, f"{pos.name} expected_y"
                )


# ---------------------------------------------------------------------------
# Property 6: Position error is Euclidean distance
# ---------------------------------------------------------------------------


class TestPositionErrorIsEuclideanDistance:
    """
    Property 6: Position error is Euclidean distance

    For any pair of board coordinates, compute_position_error should return
    the Euclidean distance sqrt((x1-x2)^2 + (y1-y2)^2).

    Feature: scoring-diagnostics, Property 6: Position error is Euclidean distance

    **Validates: Requirements 5.4**
    """

    FLOAT_TOLERANCE = 1e-9

    @given(
        x1=st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False),
        y1=st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False),
        x2=st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False),
        y2=st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_position_error_is_euclidean_distance(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> None:
        """
        Feature: scoring-diagnostics, Property 6: Position error is Euclidean distance

        Generate random pairs of board coordinates, verify compute_position_error
        matches sqrt((x1-x2)^2 + (y1-y2)^2).

        **Validates: Requirements 5.4**
        """
        result = compute_position_error(x1, y1, x2, y2)
        expected = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
        assert abs(result - expected) < self.FLOAT_TOLERANCE, (
            f"compute_position_error({x1}, {y1}, {x2}, {y2}) = {result}, "
            f"expected {expected} (diff={abs(result - expected)})"
        )


# ---------------------------------------------------------------------------
# Property 7: Angular error handles wraparound
# ---------------------------------------------------------------------------


class TestAngularErrorHandlesWraparound:
    """
    Property 7: Angular error handles wraparound

    For any pair of angles in [0, 360), compute_angular_error should return
    min(|a-b|, 360-|a-b|) and the result should always be in [0, 180].

    Feature: scoring-diagnostics, Property 7: Angular error handles wraparound

    **Validates: Requirements 5.5**
    """

    FLOAT_TOLERANCE = 1e-9

    @given(
        a_deg=st.floats(min_value=0, max_value=360, allow_nan=False, allow_infinity=False, exclude_max=True),
        b_deg=st.floats(min_value=0, max_value=360, allow_nan=False, allow_infinity=False, exclude_max=True),
    )
    @settings(max_examples=100, deadline=None)
    def test_angular_error_handles_wraparound(
        self, a_deg: float, b_deg: float
    ) -> None:
        """
        Feature: scoring-diagnostics, Property 7: Angular error handles wraparound

        Generate random pairs of angles in [0, 360), verify compute_angular_error
        equals min(|a-b|, 360-|a-b|) and result is in [0, 180].

        **Validates: Requirements 5.5**
        """
        result = compute_angular_error(a_deg, b_deg)
        diff = abs(a_deg - b_deg)
        expected = min(diff, 360.0 - diff)
        assert abs(result - expected) < self.FLOAT_TOLERANCE, (
            f"compute_angular_error({a_deg}, {b_deg}) = {result}, "
            f"expected {expected} (diff={abs(result - expected)})"
        )
        assert 0 <= result <= 180, (
            f"compute_angular_error({a_deg}, {b_deg}) = {result}, "
            f"expected result in [0, 180]"
        )


# ---------------------------------------------------------------------------
# Additional imports for Properties 8 and 9
# ---------------------------------------------------------------------------

from src.diagnostics.test_report import TestReport, TestReportGenerator


# ---------------------------------------------------------------------------
# Strategy for Property 8: per-throw result dicts
# ---------------------------------------------------------------------------

TARGET_NAMES = ["T20", "T1", "T5", "D20", "D1", "D5", "BS20", "SB", "DB"]


@st.composite
def per_throw_result_strategy(draw):
    """Generate a random per-throw accuracy result dict.

    Produces a dict matching the format expected by
    TestReportGenerator.generate_report().
    """
    target_name = draw(st.sampled_from(TARGET_NAMES))
    expected_score = draw(st.integers(min_value=0, max_value=60))
    detected_score = draw(st.integers(min_value=0, max_value=60))
    position_error_mm = draw(
        st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False)
    )
    angular_error_deg = draw(
        st.floats(min_value=0, max_value=180, allow_nan=False, allow_infinity=False)
    )
    ring_match = draw(st.booleans())
    sector_match = draw(st.booleans())
    score_match = draw(st.booleans())
    record = draw(detection_record_strategy())

    return {
        "target_name": target_name,
        "expected_score": expected_score,
        "detected_score": detected_score,
        "position_error_mm": position_error_mm,
        "angular_error_deg": angular_error_deg,
        "ring_match": ring_match,
        "sector_match": sector_match,
        "score_match": score_match,
        "record": record,
    }


# ---------------------------------------------------------------------------
# Property 8: Report metric aggregation correctness
# ---------------------------------------------------------------------------


class TestReportMetricAggregationCorrectness:
    """
    Property 8: Report metric aggregation correctness

    For any list of per-throw accuracy results, the TestReport overall metrics
    should satisfy: sector_match_rate == count(sector_match) / total * 100,
    ring_match_rate == count(ring_match) / total * 100,
    score_match_rate == count(score_match) / total * 100,
    mean_position_error_mm == mean of all position errors,
    max_position_error_mm == max of all position errors.

    Feature: scoring-diagnostics, Property 8: Report metric aggregation correctness

    **Validates: Requirements 6.2, 6.3, 6.4**
    """

    FLOAT_TOLERANCE = 0.15  # rounding to 1 decimal place

    def _assert_floats_close(self, a: float, b: float, label: str) -> None:
        """Assert two floats are equal within tolerance."""
        assert abs(a - b) < self.FLOAT_TOLERANCE, (
            f"{label}: {a} != {b} (diff={abs(a - b)})"
        )

    @given(
        results=st.lists(per_throw_result_strategy(), min_size=1, max_size=15)
    )
    @settings(max_examples=100, deadline=None)
    def test_report_metric_aggregation_correctness(self, results: list) -> None:
        """
        Feature: scoring-diagnostics, Property 8: Report metric aggregation correctness

        Generate random per-throw accuracy results, create a DiagnosticLogger
        (tempfile), call TestReportGenerator.generate_report(), verify overall
        metrics match manual aggregation.

        **Validates: Requirements 6.2, 6.3, 6.4**
        """
        from src.diagnostics.diagnostic_logger import DiagnosticLogger

        with tempfile.TemporaryDirectory() as tmp_dir:
            diag_logger = DiagnosticLogger(base_dir=tmp_dir)

            report = TestReportGenerator.generate_report(results, diag_logger)

            total = len(results)
            overall = report.overall

            # --- total_throws ---
            assert overall["total_throws"] == total, (
                f"total_throws: {overall['total_throws']} != {total}"
            )

            # --- sector_match_rate ---
            expected_sector_rate = round(
                sum(1 for r in results if r["sector_match"]) / total * 100, 1
            )
            self._assert_floats_close(
                overall["sector_match_rate"],
                expected_sector_rate,
                "sector_match_rate",
            )

            # --- ring_match_rate ---
            expected_ring_rate = round(
                sum(1 for r in results if r["ring_match"]) / total * 100, 1
            )
            self._assert_floats_close(
                overall["ring_match_rate"],
                expected_ring_rate,
                "ring_match_rate",
            )

            # --- score_match_rate ---
            expected_score_rate = round(
                sum(1 for r in results if r["score_match"]) / total * 100, 1
            )
            self._assert_floats_close(
                overall["score_match_rate"],
                expected_score_rate,
                "score_match_rate",
            )

            # --- mean_position_error_mm ---
            position_errors = [r["position_error_mm"] for r in results]
            expected_mean = round(sum(position_errors) / total, 1)
            self._assert_floats_close(
                overall["mean_position_error_mm"],
                expected_mean,
                "mean_position_error_mm",
            )

            # --- max_position_error_mm ---
            expected_max = round(max(position_errors), 1)
            self._assert_floats_close(
                overall["max_position_error_mm"],
                expected_max,
                "max_position_error_mm",
            )


# ---------------------------------------------------------------------------
# Strategy for Property 9: TestReport objects
# ---------------------------------------------------------------------------


@st.composite
def report_strategy(draw):
    """Generate a random valid TestReport object."""
    session_dir = draw(st.from_regex(r"data/diagnostics/Session_\d{3}", fullmatch=True))

    total_throws = draw(st.integers(min_value=0, max_value=20))
    sector_match_rate = draw(
        st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)
    )
    ring_match_rate = draw(
        st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)
    )
    score_match_rate = draw(
        st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)
    )
    mean_position_error_mm = draw(
        st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False)
    )
    max_position_error_mm = draw(
        st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False)
    )

    overall = {
        "total_throws": total_throws,
        "sector_match_rate": round(sector_match_rate, 1),
        "ring_match_rate": round(ring_match_rate, 1),
        "score_match_rate": round(score_match_rate, 1),
        "mean_position_error_mm": round(mean_position_error_mm, 1),
        "max_position_error_mm": round(max_position_error_mm, 1),
    }

    # Per-throw: 0-5 entries
    num_throws = draw(st.integers(min_value=0, max_value=5))
    per_throw = []
    for _ in range(num_throws):
        entry = {
            "target": draw(st.sampled_from(TARGET_NAMES)),
            "expected_score": draw(st.integers(min_value=0, max_value=60)),
            "detected_score": draw(st.integers(min_value=0, max_value=60)),
            "position_error_mm": round(
                draw(st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False)),
                1,
            ),
            "angular_error_deg": round(
                draw(st.floats(min_value=0, max_value=180, allow_nan=False, allow_infinity=False)),
                1,
            ),
            "ring_match": draw(st.booleans()),
            "sector_match": draw(st.booleans()),
        }
        per_throw.append(entry)

    # Per-camera: 0-3 camera entries
    num_cameras = draw(st.integers(min_value=0, max_value=3))
    per_camera = {}
    for i in range(num_cameras):
        cam_id = str(i)
        per_camera[cam_id] = {
            "mean_deviation_mm": round(
                draw(st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False)),
                1,
            ),
            "max_deviation_mm": round(
                draw(st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False)),
                1,
            ),
        }

    return TestReport(
        session_dir=session_dir,
        overall=overall,
        per_throw=per_throw,
        per_camera=per_camera,
    )


# ---------------------------------------------------------------------------
# Property 9: TestReport JSON round-trip
# ---------------------------------------------------------------------------


class TestReportJsonRoundTrip:
    """
    Property 9: TestReport JSON round-trip

    For any valid TestReport, serializing it with to_dict() and then
    deserializing with from_dict() should produce an equivalent TestReport
    (all fields equal within floating-point tolerance).

    Feature: scoring-diagnostics, Property 9: TestReport JSON round-trip

    **Validates: Requirements 6.6**
    """

    FLOAT_TOLERANCE = 1e-9

    def _assert_floats_close(self, a: float, b: float, label: str) -> None:
        """Assert two floats are equal within tolerance."""
        assert abs(a - b) < self.FLOAT_TOLERANCE, (
            f"{label}: {a} != {b} (diff={abs(a - b)})"
        )

    @given(report=report_strategy())
    @settings(max_examples=100, deadline=None)
    def test_report_json_round_trip(self, report: TestReport) -> None:
        """
        Feature: scoring-diagnostics, Property 9: TestReport JSON round-trip

        Generate random TestReport objects, round-trip through to_dict()/from_dict(),
        verify equivalence within float tolerance.

        **Validates: Requirements 6.6**
        """
        data = report.to_dict()
        restored = TestReport.from_dict(data)

        # --- session_dir ---
        assert report.session_dir == restored.session_dir, (
            f"session_dir: {report.session_dir} != {restored.session_dir}"
        )

        # --- overall metrics ---
        for key in report.overall:
            orig_val = report.overall[key]
            rest_val = restored.overall[key]
            if isinstance(orig_val, float):
                self._assert_floats_close(orig_val, rest_val, f"overall.{key}")
            else:
                assert orig_val == rest_val, (
                    f"overall.{key}: {orig_val} != {rest_val}"
                )

        # --- per_throw ---
        assert len(report.per_throw) == len(restored.per_throw), (
            f"per_throw count: {len(report.per_throw)} != {len(restored.per_throw)}"
        )
        for i, (orig_t, rest_t) in enumerate(
            zip(report.per_throw, restored.per_throw)
        ):
            for key in orig_t:
                orig_val = orig_t[key]
                rest_val = rest_t[key]
                if isinstance(orig_val, float):
                    self._assert_floats_close(
                        orig_val, rest_val, f"per_throw[{i}].{key}"
                    )
                else:
                    assert orig_val == rest_val, (
                        f"per_throw[{i}].{key}: {orig_val} != {rest_val}"
                    )

        # --- per_camera ---
        assert set(report.per_camera.keys()) == set(restored.per_camera.keys()), (
            f"per_camera keys: {set(report.per_camera.keys())} "
            f"!= {set(restored.per_camera.keys())}"
        )
        for cam_id in report.per_camera:
            for key in report.per_camera[cam_id]:
                orig_val = report.per_camera[cam_id][key]
                rest_val = restored.per_camera[cam_id][key]
                if isinstance(orig_val, float):
                    self._assert_floats_close(
                        orig_val, rest_val, f"per_camera[{cam_id}].{key}"
                    )
                else:
                    assert orig_val == rest_val, (
                        f"per_camera[{cam_id}].{key}: {orig_val} != {rest_val}"
                    )
