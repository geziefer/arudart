"""
Accuracy analysis for the human feedback system.

Computes overall, per-sector, and per-ring accuracy metrics from
feedback data. Generates confusion matrices and identifies top
failure modes.

Requirements: AC-7.5.3.1, AC-7.5.3.2, AC-7.5.3.3, AC-7.5.3.4,
              AC-7.5.3.5, AC-7.5.3.6
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _score_dict_to_label(score: dict) -> str:
    """Convert a score dict to a short label string.

    Args:
        score: Dict with keys ``ring``, ``sector``, ``total``.

    Returns:
        Label such as "T20", "D16", "S5", "SB", "DB", or "Miss".
    """
    ring = score.get("ring", "")
    sector = score.get("sector")
    if ring == "triple":
        return f"T{sector}"
    if ring == "double":
        return f"D{sector}"
    if ring == "single":
        return f"S{sector}"
    if ring == "bull":
        return "DB"
    if ring == "single_bull":
        return "SB"
    return "Miss"


class AccuracyAnalyzer:
    """Analyze feedback data to compute accuracy metrics."""

    def compute_overall_accuracy(self, feedback_list: list[dict]) -> float:
        """Compute overall accuracy as percentage of correct detections.

        Args:
            feedback_list: List of feedback metadata dicts.

        Returns:
            Accuracy as a float percentage (0.0–100.0).
            Returns 0.0 for an empty list.
        """
        if not feedback_list:
            return 0.0
        correct = sum(1 for fb in feedback_list if fb.get("is_correct"))
        return (correct / len(feedback_list)) * 100.0

    def compute_per_sector_accuracy(
        self, feedback_list: list[dict]
    ) -> dict[int, float]:
        """Compute accuracy grouped by actual score sector.

        Entries with ``actual_score.sector`` of ``None`` (bulls/miss) are
        skipped.

        Args:
            feedback_list: List of feedback metadata dicts.

        Returns:
            Mapping of sector number → accuracy percentage.
        """
        groups: dict[int, list[bool]] = {}
        for fb in feedback_list:
            sector = fb.get("actual_score", {}).get("sector")
            if sector is None:
                continue
            groups.setdefault(sector, []).append(bool(fb.get("is_correct")))

        return {
            sector: (sum(vals) / len(vals)) * 100.0
            for sector, vals in groups.items()
        }

    def compute_per_ring_accuracy(
        self, feedback_list: list[dict]
    ) -> dict[str, float]:
        """Compute accuracy grouped by actual score ring type.

        Args:
            feedback_list: List of feedback metadata dicts.

        Returns:
            Mapping of ring name → accuracy percentage.
        """
        groups: dict[str, list[bool]] = {}
        for fb in feedback_list:
            ring = fb.get("actual_score", {}).get("ring")
            if ring is None:
                continue
            groups.setdefault(ring, []).append(bool(fb.get("is_correct")))

        return {
            ring: (sum(vals) / len(vals)) * 100.0
            for ring, vals in groups.items()
        }

    def generate_confusion_matrix(
        self, feedback_list: list[dict]
    ) -> dict[str, dict[str, int]]:
        """Build a confusion matrix of detected vs actual score labels.

        Args:
            feedback_list: List of feedback metadata dicts.

        Returns:
            Nested dict ``{detected_label: {actual_label: count}}``.
        """
        matrix: dict[str, dict[str, int]] = {}
        for fb in feedback_list:
            detected = _score_dict_to_label(fb.get("detected_score", {}))
            actual = _score_dict_to_label(fb.get("actual_score", {}))
            matrix.setdefault(detected, {})
            matrix[detected][actual] = matrix[detected].get(actual, 0) + 1
        return matrix

    def identify_failure_modes(
        self, feedback_list: list[dict], top_n: int = 5
    ) -> list[tuple[str, str, int]]:
        """Identify the most common failure modes.

        A failure mode is a ``(detected_label, actual_label)`` pair where
        the detection was incorrect.

        Args:
            feedback_list: List of feedback metadata dicts.
            top_n: Number of top failure modes to return.

        Returns:
            List of ``(detected_label, actual_label, count)`` tuples
            sorted by count descending.
        """
        counter: Counter[tuple[str, str]] = Counter()
        for fb in feedback_list:
            if fb.get("is_correct"):
                continue
            detected = _score_dict_to_label(fb.get("detected_score", {}))
            actual = _score_dict_to_label(fb.get("actual_score", {}))
            counter[(detected, actual)] += 1

        return [
            (det, act, cnt)
            for (det, act), cnt in counter.most_common(top_n)
        ]

    def export_report(
        self, analysis_results: dict, output_path: str | Path
    ) -> None:
        """Write a human-readable analysis report to a text file.

        Args:
            analysis_results: Dict with keys ``overall_accuracy``,
                ``per_sector_accuracy``, ``per_ring_accuracy``,
                ``failure_modes``, ``total``, ``correct``, ``incorrect``.
            output_path: Destination file path.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        lines.append("ARU-DART Feedback Analysis Report")
        lines.append(f"Generated: {now}")
        lines.append("=" * 40)
        lines.append("")

        # Overall statistics
        lines.append("Overall Statistics")
        lines.append("-" * 20)
        lines.append(f"Total Throws: {analysis_results.get('total', 0)}")
        lines.append(f"Correct Detections: {analysis_results.get('correct', 0)}")
        lines.append(f"Incorrect Detections: {analysis_results.get('incorrect', 0)}")
        lines.append(f"Overall Accuracy: {analysis_results.get('overall_accuracy', 0.0):.1f}%")
        lines.append("")

        # Per-sector accuracy
        per_sector = analysis_results.get("per_sector_accuracy", {})
        if per_sector:
            lines.append("Per-Sector Accuracy")
            lines.append("-" * 20)
            for sector in sorted(per_sector.keys()):
                lines.append(f"Sector {sector}: {per_sector[sector]:.1f}%")
            lines.append("")

        # Per-ring accuracy
        per_ring = analysis_results.get("per_ring_accuracy", {})
        if per_ring:
            lines.append("Per-Ring Accuracy")
            lines.append("-" * 20)
            for ring, acc in per_ring.items():
                lines.append(f"{ring}: {acc:.1f}%")
            lines.append("")

        # Top failure modes
        failure_modes = analysis_results.get("failure_modes", [])
        if failure_modes:
            lines.append(f"Top {len(failure_modes)} Failure Modes")
            lines.append("-" * 20)
            for i, (det, act, cnt) in enumerate(failure_modes, 1):
                lines.append(f"{i}. {det} detected as {act}: {cnt} occurrences")
            lines.append("")

        path.write_text("\n".join(lines))
        logger.info("Analysis report saved to: %s", path)
