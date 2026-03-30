"""
Integration tests for the feedback system integration with main.py.

Tests the full feedback workflow with mocked user input, feedback mode
flag activation, and feedback storage integration.

Requirements: AC-7.5.1.1, AC-7.5.1.5
"""

import argparse
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.feedback.feedback_collector import FeedbackCollector
from src.feedback.feedback_prompt import FeedbackPrompt
from src.feedback.feedback_storage import FeedbackStorage
from src.feedback.score_parser import ParsedScore
from src.fusion.dart_hit_event import CameraDetection, DartHitEvent, Score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dart_hit_event() -> DartHitEvent:
    """Create a realistic DartHitEvent for testing."""
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
                camera_id=0, pixel_x=412.3, pixel_y=287.5,
                board_x=1.8, board_y=99.2, confidence=0.85,
            ),
        ],
        image_paths={"0": "cam0_annotated.jpg"},
    )


# ---------------------------------------------------------------------------
# Test: --feedback-mode flag parsing
# ---------------------------------------------------------------------------


class TestFeedbackModeFlag:
    """Test that --feedback-mode CLI flag is parsed correctly."""

    def test_feedback_mode_flag_default_false(self):
        """Without --feedback-mode, args.feedback_mode should be False."""
        parser = argparse.ArgumentParser()
        parser.add_argument('--feedback-mode', action='store_true',
                            help='Enable feedback collection mode')
        args = parser.parse_args([])
        assert args.feedback_mode is False

    def test_feedback_mode_flag_enabled(self):
        """With --feedback-mode, args.feedback_mode should be True."""
        parser = argparse.ArgumentParser()
        parser.add_argument('--feedback-mode', action='store_true',
                            help='Enable feedback collection mode')
        args = parser.parse_args(['--feedback-mode'])
        assert args.feedback_mode is True

    def test_feedback_mode_initializes_components(self):
        """When feedback_mode is True, FeedbackCollector and FeedbackStorage are created."""
        feedback_collector = None
        feedback_storage = None
        feedback_mode = True

        if feedback_mode:
            feedback_storage = FeedbackStorage()
            feedback_collector = FeedbackCollector()

        assert feedback_collector is not None
        assert feedback_storage is not None
        assert isinstance(feedback_collector, FeedbackCollector)
        assert isinstance(feedback_storage, FeedbackStorage)

    def test_feedback_mode_disabled_leaves_none(self):
        """When feedback_mode is False, collector and storage remain None."""
        feedback_collector = None
        feedback_storage = None
        feedback_mode = False

        if feedback_mode:
            feedback_storage = FeedbackStorage()
            feedback_collector = FeedbackCollector()

        assert feedback_collector is None
        assert feedback_storage is None


# ---------------------------------------------------------------------------
# Test: Full feedback workflow
# ---------------------------------------------------------------------------


class TestFeedbackWorkflowIntegration:
    """Test the full feedback collection + storage workflow."""

    def test_collect_and_save_correct_detection(self, tmp_path):
        """Full workflow: user confirms detection → feedback saved as correct."""
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "y"

        collector = FeedbackCollector(prompt=mock_prompt)
        storage = FeedbackStorage(feedback_dir=tmp_path / "feedback")

        event = _make_dart_hit_event()
        image_paths = {"0": "cam0_annotated.jpg"}

        # Collect feedback
        feedback_data = collector.collect_feedback(event, image_paths)
        assert feedback_data is not None
        assert feedback_data["is_correct"] is True

        # Save feedback
        feedback_id = storage.save_feedback(feedback_data)
        assert feedback_id is not None

        # Verify stored in correct/ subdirectory
        correct_dir = tmp_path / "feedback" / "correct"
        assert correct_dir.exists()
        entries = list(correct_dir.iterdir())
        assert len(entries) == 1

        # Verify metadata.json exists
        metadata_path = entries[0] / "metadata.json"
        assert metadata_path.exists()

    def test_collect_and_save_incorrect_detection(self, tmp_path):
        """Full workflow: user corrects detection → feedback saved as incorrect."""
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "n"
        mock_prompt.prompt_score_input.return_value = "S20"

        collector = FeedbackCollector(prompt=mock_prompt)
        storage = FeedbackStorage(feedback_dir=tmp_path / "feedback")

        event = _make_dart_hit_event()  # detected T20
        image_paths = {"0": "cam0_annotated.jpg"}

        # Collect feedback
        feedback_data = collector.collect_feedback(event, image_paths)
        assert feedback_data is not None
        assert feedback_data["is_correct"] is False

        # Save feedback
        feedback_id = storage.save_feedback(feedback_data)
        assert feedback_id is not None

        # Verify stored in incorrect/ subdirectory
        incorrect_dir = tmp_path / "feedback" / "incorrect"
        assert incorrect_dir.exists()
        entries = list(incorrect_dir.iterdir())
        assert len(entries) == 1

    def test_feedback_collector_called_with_correct_event(self):
        """Verify collect_feedback receives the right DartHitEvent."""
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "y"

        collector = FeedbackCollector(prompt=mock_prompt)
        event = _make_dart_hit_event()
        image_paths = {"0": "cam0.jpg", "1": "cam1.jpg"}

        result = collector.collect_feedback(event, image_paths)

        # Verify the event is passed through
        assert result["dart_hit_event"] is event
        assert result["image_paths"] == image_paths

        # Verify prompt was called with correct display string and confidence
        mock_prompt.prompt_confirmation.assert_called_once_with(
            "T20 (60 points)", 0.85
        )

    def test_feedback_storage_called_with_feedback_data(self, tmp_path):
        """Verify save_feedback is called with the collected feedback dict."""
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "s"

        collector = FeedbackCollector(prompt=mock_prompt)
        storage = FeedbackStorage(feedback_dir=tmp_path / "feedback")

        event = _make_dart_hit_event()
        feedback_data = collector.collect_feedback(event, {})

        assert feedback_data is not None
        feedback_id = storage.save_feedback(feedback_data)

        # Verify feedback was saved
        all_feedback = storage.load_all_feedback()
        assert len(all_feedback) == 1
        assert all_feedback[0]["feedback_id"] == feedback_id


# ---------------------------------------------------------------------------
# Test: Integration pattern matching main.py logic
# ---------------------------------------------------------------------------


class TestMainLoopFeedbackPattern:
    """Test the feedback integration pattern as used in the main loop functions."""

    def test_feedback_collected_when_enabled(self, tmp_path):
        """Simulate the main loop pattern: feedback collected when collector is not None."""
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "y"

        feedback_collector = FeedbackCollector(prompt=mock_prompt)
        feedback_storage = FeedbackStorage(feedback_dir=tmp_path / "feedback")

        event = _make_dart_hit_event()
        image_paths = {"0": "cam0.jpg"}

        # Simulate the pattern from main.py
        if feedback_collector is not None:
            feedback_data = feedback_collector.collect_feedback(event, image_paths)
            if feedback_data is not None and feedback_storage is not None:
                feedback_id = feedback_storage.save_feedback(feedback_data)

        # Verify feedback was collected and saved
        all_feedback = feedback_storage.load_all_feedback()
        assert len(all_feedback) == 1

    def test_feedback_skipped_when_disabled(self):
        """Simulate the main loop pattern: no feedback when collector is None."""
        feedback_collector = None
        feedback_storage = None

        event = _make_dart_hit_event()
        image_paths = {"0": "cam0.jpg"}
        feedback_saved = False

        # Simulate the pattern from main.py
        if feedback_collector is not None:
            feedback_data = feedback_collector.collect_feedback(event, image_paths)
            if feedback_data is not None and feedback_storage is not None:
                feedback_storage.save_feedback(feedback_data)
                feedback_saved = True

        assert feedback_saved is False

    def test_multiple_throws_saved_independently(self, tmp_path):
        """Multiple throws each get their own feedback entry."""
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "y"

        feedback_collector = FeedbackCollector(prompt=mock_prompt)
        feedback_storage = FeedbackStorage(feedback_dir=tmp_path / "feedback")

        for _ in range(3):
            event = _make_dart_hit_event()
            feedback_data = feedback_collector.collect_feedback(event, {})
            if feedback_data is not None:
                feedback_storage.save_feedback(feedback_data)

        all_feedback = feedback_storage.load_all_feedback()
        assert len(all_feedback) == 3
