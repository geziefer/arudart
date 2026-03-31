"""MotionClassifier for distinguishing dart throws from hand pull-outs.

Classifies motion as DART (fast, small, brief), HAND (slow, large, sustained),
or UNKNOWN based on speed, size, and duration thresholds loaded from config.

Requirements: AC-8.3.1, AC-8.3.2, AC-8.3.3
"""

import logging

from src.state_machine.events import MotionType

logger = logging.getLogger(__name__)

# Default thresholds used when config keys are missing.
_DEFAULTS = {
    "dart_speed_threshold_px_per_s": 500,
    "hand_speed_threshold_px_per_s": 200,
    "dart_size_threshold_px2": 100,
    "hand_size_threshold_px2": 500,
    "dart_duration_threshold_ms": 200,
    "hand_duration_threshold_ms": 500,
}


class MotionClassifier:
    """Classify detected motion as a dart throw or hand pull-out.

    Thresholds are read from the ``motion_classification`` section of the
    supplied *config* dict.  Any missing key falls back to a sensible default.

    Attributes:
        dart_speed_threshold: Minimum speed (px/s) for dart classification.
        hand_speed_threshold: Maximum speed (px/s) for hand classification.
        dart_size_threshold: Maximum size (px²) for dart classification.
        hand_size_threshold: Minimum size (px²) for hand classification.
        dart_duration_threshold: Maximum duration (ms) for dart classification.
        hand_duration_threshold: Minimum duration (ms) for hand classification.
    """

    def __init__(self, config: dict) -> None:
        mc = config.get("motion_classification", {})
        self.dart_speed_threshold: float = mc.get(
            "dart_speed_threshold_px_per_s",
            _DEFAULTS["dart_speed_threshold_px_per_s"],
        )
        self.hand_speed_threshold: float = mc.get(
            "hand_speed_threshold_px_per_s",
            _DEFAULTS["hand_speed_threshold_px_per_s"],
        )
        self.dart_size_threshold: float = mc.get(
            "dart_size_threshold_px2",
            _DEFAULTS["dart_size_threshold_px2"],
        )
        self.hand_size_threshold: float = mc.get(
            "hand_size_threshold_px2",
            _DEFAULTS["hand_size_threshold_px2"],
        )
        self.dart_duration_threshold: float = mc.get(
            "dart_duration_threshold_ms",
            _DEFAULTS["dart_duration_threshold_ms"],
        )
        self.hand_duration_threshold: float = mc.get(
            "hand_duration_threshold_ms",
            _DEFAULTS["hand_duration_threshold_ms"],
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_motion(self, motion_data: dict) -> MotionType:
        """Classify *motion_data* as DART, HAND, or UNKNOWN.

        Args:
            motion_data: Dictionary with keys ``speed`` (px/s),
                ``size`` (px²), and ``duration`` (ms).

        Returns:
            ``MotionType.DART`` if the motion is fast, small, and brief.
            ``MotionType.HAND`` if the motion is slow, large, and sustained.
            ``MotionType.UNKNOWN`` otherwise.
        """
        speed = self.compute_motion_speed(motion_data)
        size = self.compute_motion_size(motion_data)
        duration = self.compute_motion_duration(motion_data)

        if (
            speed > self.dart_speed_threshold
            and size < self.dart_size_threshold
            and duration < self.dart_duration_threshold
        ):
            return MotionType.DART

        if (
            speed < self.hand_speed_threshold
            and size > self.hand_size_threshold
            and duration > self.hand_duration_threshold
        ):
            return MotionType.HAND

        logger.warning(
            "Motion classified as UNKNOWN (speed=%.1f, size=%.1f, duration=%.1f)",
            speed,
            size,
            duration,
        )
        return MotionType.UNKNOWN

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def compute_motion_speed(motion_data: dict) -> float:
        """Extract or compute motion speed in px/s.

        Args:
            motion_data: Dictionary containing a ``speed`` key.

        Returns:
            Speed value as a float.
        """
        return float(motion_data.get("speed", 0.0))

    @staticmethod
    def compute_motion_size(motion_data: dict) -> float:
        """Extract or compute motion size in px².

        Args:
            motion_data: Dictionary containing a ``size`` key.

        Returns:
            Size value as a float.
        """
        return float(motion_data.get("size", 0.0))

    @staticmethod
    def compute_motion_duration(motion_data: dict) -> float:
        """Extract or compute motion duration in ms.

        Args:
            motion_data: Dictionary containing a ``duration`` key.

        Returns:
            Duration value as a float.
        """
        return float(motion_data.get("duration", 0.0))
