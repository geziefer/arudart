"""Accuracy test runner for the ARU-DART scoring pipeline.

Orchestrates the accuracy test workflow: guides the user through placing
darts at known board positions, compares detected results against expected
values, and produces a TestReport with quantifiable accuracy metrics.
"""

import math
from typing import Optional

from src.diagnostics.diagnostic_logger import DiagnosticLogger
from src.diagnostics.known_positions import (
    KnownPosition,
    compute_angular_error,
    compute_position_error,
)
from src.diagnostics.test_report import TestReport, TestReportGenerator
from src.fusion.dart_hit_event import DartHitEvent
from src.fusion.score_calculator import ScoreCalculator


class AccuracyTestRunner:
    """Orchestrates accuracy testing against known board positions.

    Drives the manual-dart-test state machine, prompting the user for
    each known position, comparing detected results against expected
    values, and producing a TestReport.

    Args:
        known_positions: List of KnownPosition targets to test.
        diagnostic_logger: DiagnosticLogger for recording detections.
        score_calculator: ScoreCalculator pipeline instance.
        position_filter: Optional list of position names to test
            (subset selection). If None, all positions are tested.
    """

    def __init__(
        self,
        known_positions: list[KnownPosition],
        diagnostic_logger: DiagnosticLogger,
        score_calculator: ScoreCalculator,
        position_filter: Optional[list[str]] = None,
    ) -> None:
        if position_filter is not None:
            filter_set = set(position_filter)
            self.positions = [
                p for p in known_positions if p.name in filter_set
            ]
        else:
            self.positions = list(known_positions)

        self.diagnostic_logger = diagnostic_logger
        self.score_calculator = score_calculator
        self.current_index: int = 0
        self.results: list[dict] = []

    def get_current_target(self) -> Optional[KnownPosition]:
        """Return the current target position, or None if complete.

        Returns:
            The KnownPosition for the current throw, or None if all
            positions have been tested.
        """
        if self.current_index >= len(self.positions):
            return None
        return self.positions[self.current_index]

    def record_result(self, event: DartHitEvent) -> None:
        """Record a detection result against the current target.

        Logs the detection via the diagnostic logger, computes comparison
        metrics (position error, angular error, ring/sector/score match),
        appends the result, and advances to the next target.

        Args:
            event: The DartHitEvent from the scoring pipeline.
        """
        target = self.get_current_target()
        if target is None:
            return

        record = self.diagnostic_logger.log_detection(event)

        # Compute comparison metrics
        position_error = compute_position_error(
            event.board_x, event.board_y,
            target.expected_x, target.expected_y,
        )

        # Compute expected angle from target coordinates
        expected_angle_deg = math.degrees(
            math.atan2(target.expected_y, target.expected_x)
        )
        if expected_angle_deg < 0:
            expected_angle_deg += 360.0

        angular_error = compute_angular_error(
            event.angle_deg, expected_angle_deg,
        )

        ring_match = event.score.ring == target.expected_ring
        sector_match = event.score.sector == target.expected_sector
        score_match = event.score.total == target.expected_score

        self.results.append({
            "target_name": target.name,
            "expected_score": target.expected_score,
            "detected_score": event.score.total,
            "position_error_mm": position_error,
            "angular_error_deg": angular_error,
            "ring_match": ring_match,
            "sector_match": sector_match,
            "score_match": score_match,
            "record": record,
        })

        self.current_index += 1

    def is_complete(self) -> bool:
        """Check whether all positions have been tested.

        Returns:
            True if all positions have been tested.
        """
        return self.current_index >= len(self.positions)

    def generate_report(self) -> TestReport:
        """Generate a TestReport from the accumulated results.

        Returns:
            A TestReport with aggregated accuracy metrics.
        """
        return TestReportGenerator.generate_report(
            self.results, self.diagnostic_logger,
        )
