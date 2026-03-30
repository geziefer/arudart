"""
Unit tests for FeedbackStorage.

Tests directory creation, metadata JSON structure, image copying,
correct/incorrect organization, and error handling.

Requirements: AC-7.5.2.1, AC-7.5.2.2, AC-7.5.2.3
"""

import json

import pytest

from src.feedback.feedback_storage import FeedbackStorage, _score_to_label
from src.feedback.score_parser import ParsedScore
from src.fusion.dart_hit_event import CameraDetection, DartHitEvent, Score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dart_hit_event() -> DartHitEvent:
    """Create a minimal DartHitEvent for testing."""
    return DartHitEvent(
        timestamp="2024-01-15T14:32:18.123456Z",
        board_x=2.3,
        board_y=98.7,
        radius=98.7,
        angle_rad=1.547,
        angle_deg=88.6,
        score=Score(base=20, multiplier=3, total=60, ring="triple", sector=20),
        fusion_confidence=0.85,
        cameras_used=[0, 1, 2],
        num_cameras=3,
        detections=[
            CameraDetection(
                camera_id=0,
                pixel_x=412.3,
                pixel_y=287.5,
                board_x=1.8,
                board_y=99.2,
                confidence=0.85,
            ),
        ],
        image_paths={"0": "cam0_annotated.jpg"},
    )


def _make_feedback_data(
    is_correct: bool = True,
    detected: ParsedScore | None = None,
    actual: ParsedScore | None = None,
    image_paths: dict | None = None,
) -> dict:
    """Build a feedback_data dict for testing."""
    if detected is None:
        detected = ParsedScore(ring="triple", sector=20, total=60)
    if actual is None:
        actual = detected if is_correct else ParsedScore(ring="single", sector=20, total=20)
    return {
        "detected_score": detected,
        "actual_score": actual,
        "is_correct": is_correct,
        "user_response": "y" if is_correct else "n",
        "dart_hit_event": _make_dart_hit_event(),
        "image_paths": image_paths or {},
    }


def _create_dummy_image(path, content: bytes = b"\x89PNG_DUMMY") -> None:
    """Write a tiny dummy file to simulate an image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


# ---------------------------------------------------------------------------
# _score_to_label tests
# ---------------------------------------------------------------------------


class TestScoreToLabel:
    def test_triple(self):
        assert _score_to_label(ParsedScore("triple", 20, 60)) == "T20"

    def test_double(self):
        assert _score_to_label(ParsedScore("double", 16, 32)) == "D16"

    def test_single(self):
        assert _score_to_label(ParsedScore("single", 5, 5)) == "S5"

    def test_bull(self):
        assert _score_to_label(ParsedScore("bull", None, 50)) == "DB"

    def test_single_bull(self):
        assert _score_to_label(ParsedScore("single_bull", None, 25)) == "SB"

    def test_miss(self):
        assert _score_to_label(ParsedScore("miss", None, 0)) == "Miss"


# ---------------------------------------------------------------------------
# Directory creation
# ---------------------------------------------------------------------------


class TestDirectoryCreation:
    def test_creates_correct_subdir(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        data = _make_feedback_data(is_correct=True)
        fid = storage.save_feedback(data)

        entry_dir = tmp_path / "correct" / fid
        assert entry_dir.exists()
        assert entry_dir.is_dir()

    def test_creates_incorrect_subdir(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        data = _make_feedback_data(is_correct=False)
        fid = storage.save_feedback(data)

        entry_dir = tmp_path / "incorrect" / fid
        assert entry_dir.exists()
        assert entry_dir.is_dir()

    def test_creates_nested_dirs_from_scratch(self, tmp_path):
        base = tmp_path / "deep" / "nested"
        storage = FeedbackStorage(feedback_dir=base)
        data = _make_feedback_data(is_correct=True)
        fid = storage.save_feedback(data)

        assert (base / "correct" / fid / "metadata.json").exists()


# ---------------------------------------------------------------------------
# Metadata JSON structure
# ---------------------------------------------------------------------------


class TestMetadataJson:
    def test_all_required_fields_present(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        data = _make_feedback_data(is_correct=True)
        fid = storage.save_feedback(data)

        meta_path = tmp_path / "correct" / fid / "metadata.json"
        meta = json.loads(meta_path.read_text())

        required = [
            "feedback_id",
            "timestamp",
            "detected_score",
            "actual_score",
            "is_correct",
            "user_response",
            "dart_hit_event",
            "image_paths",
        ]
        for field in required:
            assert field in meta, f"Missing field: {field}"
            assert meta[field] is not None, f"Field is None: {field}"

    def test_detected_score_structure(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        data = _make_feedback_data(is_correct=True)
        fid = storage.save_feedback(data)

        meta_path = tmp_path / "correct" / fid / "metadata.json"
        meta = json.loads(meta_path.read_text())

        ds = meta["detected_score"]
        assert ds["ring"] == "triple"
        assert ds["sector"] == 20
        assert ds["total"] == 60

    def test_dart_hit_event_serialized(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        data = _make_feedback_data(is_correct=True)
        fid = storage.save_feedback(data)

        meta_path = tmp_path / "correct" / fid / "metadata.json"
        meta = json.loads(meta_path.read_text())

        dhe = meta["dart_hit_event"]
        assert "board_coordinates" in dhe
        assert "score" in dhe
        assert "detections" in dhe

    def test_feedback_id_matches_dirname(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        data = _make_feedback_data(is_correct=True)
        fid = storage.save_feedback(data)

        meta_path = tmp_path / "correct" / fid / "metadata.json"
        meta = json.loads(meta_path.read_text())
        assert meta["feedback_id"] == fid

    def test_incorrect_feedback_id_contains_actual(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        data = _make_feedback_data(
            is_correct=False,
            detected=ParsedScore("double", 20, 40),
            actual=ParsedScore("single", 20, 20),
        )
        fid = storage.save_feedback(data)

        assert "D20" in fid
        assert "actual" in fid
        assert "S20" in fid


# ---------------------------------------------------------------------------
# Image copying
# ---------------------------------------------------------------------------


class TestImageCopying:
    def test_copies_single_image(self, tmp_path):
        src_dir = tmp_path / "source"
        src_img = src_dir / "cam0.jpg"
        _create_dummy_image(src_img)

        storage = FeedbackStorage(feedback_dir=tmp_path / "fb")
        data = _make_feedback_data(image_paths={"0": str(src_img)})
        fid = storage.save_feedback(data)

        entry_dir = tmp_path / "fb" / "correct" / fid
        copied_files = list(entry_dir.glob("cam0*"))
        assert len(copied_files) == 1

    def test_copies_dict_of_images(self, tmp_path):
        src_dir = tmp_path / "source"
        pre = src_dir / "pre.jpg"
        post = src_dir / "post.jpg"
        ann = src_dir / "annotated.jpg"
        for p in (pre, post, ann):
            _create_dummy_image(p)

        image_paths = {
            "0": {"pre": str(pre), "post": str(post), "annotated": str(ann)},
        }
        storage = FeedbackStorage(feedback_dir=tmp_path / "fb")
        data = _make_feedback_data(image_paths=image_paths)
        fid = storage.save_feedback(data)

        entry_dir = tmp_path / "fb" / "correct" / fid
        assert (entry_dir / "cam0_pre.jpg").exists()
        assert (entry_dir / "cam0_post.jpg").exists()
        assert (entry_dir / "cam0_annotated.jpg").exists()

    def test_image_content_preserved(self, tmp_path):
        src_dir = tmp_path / "source"
        src_img = src_dir / "cam0.jpg"
        content = b"\x89PNG_TEST_CONTENT_12345"
        _create_dummy_image(src_img, content)

        storage = FeedbackStorage(feedback_dir=tmp_path / "fb")
        data = _make_feedback_data(image_paths={"0": str(src_img)})
        fid = storage.save_feedback(data)

        entry_dir = tmp_path / "fb" / "correct" / fid
        copied = list(entry_dir.glob("cam0*"))[0]
        assert copied.read_bytes() == content


# ---------------------------------------------------------------------------
# Correct / incorrect organization
# ---------------------------------------------------------------------------


class TestOrganization:
    def test_correct_goes_to_correct_dir(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        fid = storage.save_feedback(_make_feedback_data(is_correct=True))
        assert (tmp_path / "correct" / fid).exists()
        assert not any((tmp_path / "incorrect").glob("*")) or not (tmp_path / "incorrect").exists()

    def test_incorrect_goes_to_incorrect_dir(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        fid = storage.save_feedback(_make_feedback_data(is_correct=False))
        assert (tmp_path / "incorrect" / fid).exists()
        assert not any((tmp_path / "correct").glob("*")) or not (tmp_path / "correct").exists()


# ---------------------------------------------------------------------------
# Error handling — missing images
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_missing_image_saves_metadata_anyway(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        data = _make_feedback_data(
            image_paths={"0": "/nonexistent/path/cam0.jpg"}
        )
        fid = storage.save_feedback(data)

        meta_path = tmp_path / "correct" / fid / "metadata.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        # Image path recorded as None for missing file
        assert meta["image_paths"]["0"] is None

    def test_partial_images_copies_available(self, tmp_path):
        src_dir = tmp_path / "source"
        existing = src_dir / "cam0.jpg"
        _create_dummy_image(existing)

        storage = FeedbackStorage(feedback_dir=tmp_path / "fb")
        data = _make_feedback_data(
            image_paths={
                "0": str(existing),
                "1": "/nonexistent/cam1.jpg",
            }
        )
        fid = storage.save_feedback(data)

        entry_dir = tmp_path / "fb" / "correct" / fid
        assert len(list(entry_dir.glob("cam0*"))) == 1
        meta = json.loads((entry_dir / "metadata.json").read_text())
        assert meta["image_paths"]["0"] is not None
        assert meta["image_paths"]["1"] is None


# ---------------------------------------------------------------------------
# load_all_feedback
# ---------------------------------------------------------------------------


class TestLoadAllFeedback:
    def test_loads_correct_and_incorrect(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        storage.save_feedback(_make_feedback_data(is_correct=True))
        storage.save_feedback(_make_feedback_data(is_correct=False))

        entries = storage.load_all_feedback()
        assert len(entries) == 2

    def test_empty_directory_returns_empty(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        assert storage.load_all_feedback() == []

    def test_loaded_entry_has_required_fields(self, tmp_path):
        storage = FeedbackStorage(feedback_dir=tmp_path)
        storage.save_feedback(_make_feedback_data(is_correct=True))

        entries = storage.load_all_feedback()
        assert len(entries) == 1
        entry = entries[0]
        for field in (
            "feedback_id", "timestamp", "detected_score",
            "actual_score", "is_correct", "dart_hit_event", "image_paths",
        ):
            assert field in entry
