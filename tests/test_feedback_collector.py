"""
Unit tests for FeedbackPrompt and FeedbackCollector.

Tests the feedback collection workflow including confirmation,
correction, skip flows, and timeout handling.

Requirements: AC-7.5.1.3, AC-7.5.1.6
"""

from unittest.mock import MagicMock, patch

import pytest

from src.feedback.feedback_collector import (
    FeedbackCollector,
    score_to_display_string,
    score_to_parsed_score,
)
from src.feedback.feedback_prompt import FeedbackPrompt
from src.feedback.score_parser import ParsedScore, ScoreParser
from src.fusion.dart_hit_event import CameraDetection, DartHitEvent, Score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_score(
    ring: str = "triple",
    sector: int | None = 20,
    total: int = 60,
    base: int = 20,
    multiplier: int = 3,
) -> Score:
    return Score(
        base=base,
        multiplier=multiplier,
        total=total,
        ring=ring,
        sector=sector,
    )


def _make_dart_hit_event(score: Score | None = None) -> DartHitEvent:
    if score is None:
        score = _make_score()
    return DartHitEvent(
        timestamp="2024-01-15T14:32:18.123456Z",
        board_x=2.3,
        board_y=98.7,
        radius=98.7,
        angle_rad=1.547,
        angle_deg=88.6,
        score=score,
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


# ---------------------------------------------------------------------------
# score_to_display_string tests
# ---------------------------------------------------------------------------


class TestScoreToDisplayString:
    """Test the helper that converts Score to a display string."""

    def test_triple(self):
        s = _make_score(ring="triple", sector=20, total=60)
        assert score_to_display_string(s) == "T20 (60 points)"

    def test_double(self):
        s = _make_score(ring="double", sector=16, total=32, base=16, multiplier=2)
        assert score_to_display_string(s) == "D16 (32 points)"

    def test_single(self):
        s = _make_score(ring="single", sector=5, total=5, base=5, multiplier=1)
        assert score_to_display_string(s) == "S5 (5 points)"

    def test_bull(self):
        s = _make_score(ring="bull", sector=None, total=50, base=50, multiplier=1)
        assert score_to_display_string(s) == "DB (50 points)"

    def test_single_bull(self):
        s = _make_score(
            ring="single_bull", sector=None, total=25, base=25, multiplier=1
        )
        assert score_to_display_string(s) == "SB (25 points)"

    def test_miss(self):
        s = _make_score(ring="miss", sector=None, total=0, base=0, multiplier=0)
        assert score_to_display_string(s) == "Miss (0 points)"


# ---------------------------------------------------------------------------
# FeedbackPrompt tests
# ---------------------------------------------------------------------------


class TestFeedbackPromptConfirmation:
    """Test prompt_confirmation with mocked input."""

    @patch("builtins.input", return_value="y")
    def test_accept_y(self, mock_input):
        prompt = FeedbackPrompt(timeout=5)
        result = prompt.prompt_confirmation("T20 (60 points)", 0.85)
        assert result == "y"

    @patch("builtins.input", return_value="n")
    def test_accept_n(self, mock_input):
        prompt = FeedbackPrompt(timeout=5)
        result = prompt.prompt_confirmation("T20 (60 points)", 0.85)
        assert result == "n"

    @patch("builtins.input", return_value="c")
    def test_accept_c(self, mock_input):
        prompt = FeedbackPrompt(timeout=5)
        result = prompt.prompt_confirmation("T20 (60 points)", 0.85)
        assert result == "c"

    @patch("builtins.input", return_value="s")
    def test_accept_s(self, mock_input):
        prompt = FeedbackPrompt(timeout=5)
        result = prompt.prompt_confirmation("T20 (60 points)", 0.85)
        assert result == "s"

    @patch("builtins.input", return_value="Y")
    def test_case_insensitive(self, mock_input):
        prompt = FeedbackPrompt(timeout=5)
        result = prompt.prompt_confirmation("T20 (60 points)", 0.85)
        assert result == "y"

    @patch("builtins.input", side_effect=["x", "y"])
    def test_reprompt_on_invalid(self, mock_input):
        prompt = FeedbackPrompt(timeout=5)
        result = prompt.prompt_confirmation("T20 (60 points)", 0.85)
        assert result == "y"
        assert mock_input.call_count == 2


class TestFeedbackPromptScoreInput:
    """Test prompt_score_input with mocked input."""

    @patch("builtins.input", return_value="T20")
    def test_valid_input(self, mock_input):
        prompt = FeedbackPrompt()
        result = prompt.prompt_score_input()
        assert result == "T20"

    @patch("builtins.input", side_effect=["", "D16"])
    def test_reprompt_on_empty(self, mock_input):
        prompt = FeedbackPrompt()
        result = prompt.prompt_score_input()
        assert result == "D16"
        assert mock_input.call_count == 2


class TestFeedbackPromptTimeout:
    """Test timeout handling in prompt_confirmation."""

    def test_timeout_returns_skip(self):
        """When _input_with_timeout returns None, confirmation defaults to 's'."""
        prompt = FeedbackPrompt(timeout=1)
        # Mock _input_with_timeout to simulate timeout
        prompt._input_with_timeout = MagicMock(return_value=None)
        result = prompt.prompt_confirmation("T20 (60 points)", 0.85)
        assert result == "s"


# ---------------------------------------------------------------------------
# FeedbackCollector tests
# ---------------------------------------------------------------------------


class TestFeedbackCollectorConfirmation:
    """Test collect_feedback with 'y' (confirm) response."""

    def test_confirm_y(self):
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "y"

        collector = FeedbackCollector(prompt=mock_prompt)
        event = _make_dart_hit_event()
        image_paths = {"0": "cam0.jpg"}

        result = collector.collect_feedback(event, image_paths)

        assert result is not None
        assert result["user_response"] == "y"
        assert result["is_correct"] is True
        assert result["detected_score"] == result["actual_score"]
        assert result["dart_hit_event"] is event
        assert result["image_paths"] == image_paths

    def test_confirm_y_detected_equals_actual(self):
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "y"

        collector = FeedbackCollector(prompt=mock_prompt)
        event = _make_dart_hit_event()

        result = collector.collect_feedback(event, {})

        detected = result["detected_score"]
        actual = result["actual_score"]
        assert detected.ring == actual.ring
        assert detected.sector == actual.sector
        assert detected.total == actual.total


class TestFeedbackCollectorCorrection:
    """Test collect_feedback with 'n' (wrong) response."""

    def test_correction_n_different_score(self):
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "n"
        mock_prompt.prompt_score_input.return_value = "S20"

        collector = FeedbackCollector(prompt=mock_prompt)
        event = _make_dart_hit_event()  # detected T20

        result = collector.collect_feedback(event, {})

        assert result is not None
        assert result["user_response"] == "n"
        assert result["is_correct"] is False
        assert result["detected_score"].ring == "triple"
        assert result["actual_score"].ring == "single"
        assert result["actual_score"].sector == 20
        assert result["actual_score"].total == 20

    def test_correction_c_same_score(self):
        """User enters 'c' but types the same score — is_correct should be True."""
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "c"
        mock_prompt.prompt_score_input.return_value = "T20"

        collector = FeedbackCollector(prompt=mock_prompt)
        event = _make_dart_hit_event()  # detected T20

        result = collector.collect_feedback(event, {})

        assert result["user_response"] == "c"
        assert result["is_correct"] is True

    def test_correction_invalid_then_valid(self):
        """Parser returns None on first attempt, valid on second."""
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "n"
        mock_prompt.prompt_score_input.side_effect = ["xyz", "D16"]

        mock_parser = MagicMock(spec=ScoreParser)
        mock_parser.parse_score.side_effect = [
            None,  # "xyz" fails
            ParsedScore(ring="double", sector=16, total=32),  # "D16" succeeds
        ]

        collector = FeedbackCollector(prompt=mock_prompt, parser=mock_parser)
        event = _make_dart_hit_event()

        result = collector.collect_feedback(event, {})

        assert result["actual_score"].ring == "double"
        assert result["actual_score"].sector == 16
        assert mock_prompt.prompt_score_input.call_count == 2


class TestFeedbackCollectorSkip:
    """Test collect_feedback with 's' (skip) response."""

    def test_skip_uses_detected_score(self):
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "s"

        collector = FeedbackCollector(prompt=mock_prompt)
        event = _make_dart_hit_event()

        result = collector.collect_feedback(event, {})

        assert result is not None
        assert result["user_response"] == "s"
        assert result["is_correct"] is True
        assert result["detected_score"] == result["actual_score"]


class TestFeedbackCollectorDisplayString:
    """Test that the collector passes the right display string to the prompt."""

    def test_display_string_passed_to_prompt(self):
        mock_prompt = MagicMock(spec=FeedbackPrompt)
        mock_prompt.prompt_confirmation.return_value = "y"

        collector = FeedbackCollector(prompt=mock_prompt)
        event = _make_dart_hit_event()

        collector.collect_feedback(event, {})

        call_args = mock_prompt.prompt_confirmation.call_args
        assert call_args[0][0] == "T20 (60 points)"
        assert call_args[0][1] == 0.85
