"""Unit tests for MotionClassifier.

Requirements: AC-8.3.1, AC-8.3.2, AC-8.3.3
"""

import pytest

from src.state_machine.events import MotionType
from src.state_machine.motion_classifier import MotionClassifier

# Default config matching the design document thresholds.
DEFAULT_CONFIG: dict = {
    "motion_classification": {
        "dart_speed_threshold_px_per_s": 500,
        "hand_speed_threshold_px_per_s": 200,
        "dart_size_threshold_px2": 100,
        "hand_size_threshold_px2": 500,
        "dart_duration_threshold_ms": 200,
        "hand_duration_threshold_ms": 500,
    }
}


@pytest.fixture
def classifier() -> MotionClassifier:
    return MotionClassifier(DEFAULT_CONFIG)


# ------------------------------------------------------------------
# Dart motion classification (fast, small, brief)  — AC-8.3.1
# ------------------------------------------------------------------

class TestDartClassification:
    def test_clear_dart_motion(self, classifier: MotionClassifier) -> None:
        motion = {"speed": 800.0, "size": 50.0, "duration": 100.0}
        assert classifier.classify_motion(motion) == MotionType.DART

    def test_dart_at_minimum_speed(self, classifier: MotionClassifier) -> None:
        """Speed just above threshold, size and duration well within."""
        motion = {"speed": 501.0, "size": 50.0, "duration": 100.0}
        assert classifier.classify_motion(motion) == MotionType.DART

    def test_dart_at_maximum_size(self, classifier: MotionClassifier) -> None:
        """Size just below threshold."""
        motion = {"speed": 800.0, "size": 99.0, "duration": 100.0}
        assert classifier.classify_motion(motion) == MotionType.DART

    def test_dart_at_maximum_duration(self, classifier: MotionClassifier) -> None:
        """Duration just below threshold."""
        motion = {"speed": 800.0, "size": 50.0, "duration": 199.0}
        assert classifier.classify_motion(motion) == MotionType.DART


# ------------------------------------------------------------------
# Hand motion classification (slow, large, sustained)  — AC-8.3.2
# ------------------------------------------------------------------

class TestHandClassification:
    def test_clear_hand_motion(self, classifier: MotionClassifier) -> None:
        motion = {"speed": 100.0, "size": 800.0, "duration": 700.0}
        assert classifier.classify_motion(motion) == MotionType.HAND

    def test_hand_at_maximum_speed(self, classifier: MotionClassifier) -> None:
        """Speed just below threshold."""
        motion = {"speed": 199.0, "size": 800.0, "duration": 700.0}
        assert classifier.classify_motion(motion) == MotionType.HAND

    def test_hand_at_minimum_size(self, classifier: MotionClassifier) -> None:
        """Size just above threshold."""
        motion = {"speed": 100.0, "size": 501.0, "duration": 700.0}
        assert classifier.classify_motion(motion) == MotionType.HAND

    def test_hand_at_minimum_duration(self, classifier: MotionClassifier) -> None:
        """Duration just above threshold."""
        motion = {"speed": 100.0, "size": 800.0, "duration": 501.0}
        assert classifier.classify_motion(motion) == MotionType.HAND


# ------------------------------------------------------------------
# Boundary / threshold-exact cases  — AC-8.3.1, AC-8.3.2
# ------------------------------------------------------------------

class TestBoundaryCases:
    def test_speed_exactly_at_dart_threshold_is_not_dart(
        self, classifier: MotionClassifier
    ) -> None:
        """speed == 500 is NOT > 500, so should not be DART."""
        motion = {"speed": 500.0, "size": 50.0, "duration": 100.0}
        assert classifier.classify_motion(motion) != MotionType.DART

    def test_size_exactly_at_dart_threshold_is_not_dart(
        self, classifier: MotionClassifier
    ) -> None:
        """size == 100 is NOT < 100, so should not be DART."""
        motion = {"speed": 800.0, "size": 100.0, "duration": 100.0}
        assert classifier.classify_motion(motion) != MotionType.DART

    def test_duration_exactly_at_dart_threshold_is_not_dart(
        self, classifier: MotionClassifier
    ) -> None:
        """duration == 200 is NOT < 200, so should not be DART."""
        motion = {"speed": 800.0, "size": 50.0, "duration": 200.0}
        assert classifier.classify_motion(motion) != MotionType.DART

    def test_speed_exactly_at_hand_threshold_is_not_hand(
        self, classifier: MotionClassifier
    ) -> None:
        """speed == 200 is NOT < 200, so should not be HAND."""
        motion = {"speed": 200.0, "size": 800.0, "duration": 700.0}
        assert classifier.classify_motion(motion) != MotionType.HAND

    def test_size_exactly_at_hand_threshold_is_not_hand(
        self, classifier: MotionClassifier
    ) -> None:
        """size == 500 is NOT > 500, so should not be HAND."""
        motion = {"speed": 100.0, "size": 500.0, "duration": 700.0}
        assert classifier.classify_motion(motion) != MotionType.HAND

    def test_duration_exactly_at_hand_threshold_is_not_hand(
        self, classifier: MotionClassifier
    ) -> None:
        """duration == 500 is NOT > 500, so should not be HAND."""
        motion = {"speed": 100.0, "size": 800.0, "duration": 500.0}
        assert classifier.classify_motion(motion) != MotionType.HAND


# ------------------------------------------------------------------
# UNKNOWN motion handling  — AC-8.3.3
# ------------------------------------------------------------------

class TestUnknownMotion:
    def test_ambiguous_motion_returns_unknown(
        self, classifier: MotionClassifier
    ) -> None:
        """Motion that fits neither dart nor hand criteria."""
        motion = {"speed": 300.0, "size": 300.0, "duration": 300.0}
        assert classifier.classify_motion(motion) == MotionType.UNKNOWN

    def test_zero_motion_returns_unknown(
        self, classifier: MotionClassifier
    ) -> None:
        motion = {"speed": 0.0, "size": 0.0, "duration": 0.0}
        # speed 0 < 200 and size 0 < 500 (not > 500) → not HAND; speed 0 not > 500 → not DART
        assert classifier.classify_motion(motion) == MotionType.UNKNOWN

    def test_missing_keys_default_to_zero(
        self, classifier: MotionClassifier
    ) -> None:
        """Empty dict should still return UNKNOWN without error."""
        assert classifier.classify_motion({}) == MotionType.UNKNOWN


# ------------------------------------------------------------------
# Compute helpers  — AC-8.3.3
# ------------------------------------------------------------------

class TestComputeHelpers:
    def test_compute_motion_speed(self, classifier: MotionClassifier) -> None:
        assert classifier.compute_motion_speed({"speed": 123.4}) == 123.4

    def test_compute_motion_size(self, classifier: MotionClassifier) -> None:
        assert classifier.compute_motion_size({"size": 456.7}) == 456.7

    def test_compute_motion_duration(self, classifier: MotionClassifier) -> None:
        assert classifier.compute_motion_duration({"duration": 789.0}) == 789.0

    def test_compute_defaults_to_zero(self, classifier: MotionClassifier) -> None:
        assert classifier.compute_motion_speed({}) == 0.0
        assert classifier.compute_motion_size({}) == 0.0
        assert classifier.compute_motion_duration({}) == 0.0


# ------------------------------------------------------------------
# Config loading
# ------------------------------------------------------------------

class TestConfigLoading:
    def test_defaults_used_when_config_empty(self) -> None:
        classifier = MotionClassifier({})
        assert classifier.dart_speed_threshold == 500
        assert classifier.hand_speed_threshold == 200
        assert classifier.dart_size_threshold == 100
        assert classifier.hand_size_threshold == 500
        assert classifier.dart_duration_threshold == 200
        assert classifier.hand_duration_threshold == 500

    def test_custom_thresholds_loaded(self) -> None:
        config = {
            "motion_classification": {
                "dart_speed_threshold_px_per_s": 600,
                "hand_speed_threshold_px_per_s": 150,
                "dart_size_threshold_px2": 80,
                "hand_size_threshold_px2": 600,
                "dart_duration_threshold_ms": 150,
                "hand_duration_threshold_ms": 600,
            }
        }
        classifier = MotionClassifier(config)
        assert classifier.dart_speed_threshold == 600
        assert classifier.hand_speed_threshold == 150
        assert classifier.dart_size_threshold == 80
        assert classifier.hand_size_threshold == 600
        assert classifier.dart_duration_threshold == 150
        assert classifier.hand_duration_threshold == 600
