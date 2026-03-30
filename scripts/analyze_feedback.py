#!/usr/bin/env python3
"""
Analyze feedback data and generate an accuracy report.

Loads all feedback from data/feedback/, runs AccuracyAnalyzer,
and exports a report to data/feedback/analysis_report.txt.

Requirements: AC-7.5.3.6

Usage:
    PYTHONPATH=. python scripts/analyze_feedback.py
"""

import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.accuracy_analyzer import AccuracyAnalyzer
from src.feedback.feedback_storage import FeedbackStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

FEEDBACK_DIR = Path("data/feedback")
REPORT_PATH = FEEDBACK_DIR / "analysis_report.txt"


def main() -> None:
    storage = FeedbackStorage(feedback_dir=FEEDBACK_DIR)
    feedback = storage.load_all_feedback()

    if not feedback:
        logger.warning("No feedback data found in %s", FEEDBACK_DIR)
        print("No feedback data found. Collect some feedback first.")
        return

    analyzer = AccuracyAnalyzer()

    overall = analyzer.compute_overall_accuracy(feedback)
    per_sector = analyzer.compute_per_sector_accuracy(feedback)
    per_ring = analyzer.compute_per_ring_accuracy(feedback)
    confusion = analyzer.generate_confusion_matrix(feedback)
    failures = analyzer.identify_failure_modes(feedback, top_n=5)

    total = len(feedback)
    correct = sum(1 for fb in feedback if fb.get("is_correct"))
    incorrect = total - correct

    results = {
        "overall_accuracy": overall,
        "per_sector_accuracy": per_sector,
        "per_ring_accuracy": per_ring,
        "confusion_matrix": confusion,
        "failure_modes": failures,
        "total": total,
        "correct": correct,
        "incorrect": incorrect,
    }

    analyzer.export_report(results, REPORT_PATH)

    # Print summary to console
    print(f"\nFeedback Analysis Summary")
    print(f"{'=' * 30}")
    print(f"Total throws:   {total}")
    print(f"Correct:        {correct}")
    print(f"Incorrect:      {incorrect}")
    print(f"Overall accuracy: {overall:.1f}%")
    print(f"\nReport saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
