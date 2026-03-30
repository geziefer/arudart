#!/usr/bin/env python3
"""
Export verified feedback data as a CSV dataset for ML training.

Loads all feedback from data/feedback/, filters correct detections,
splits into train/val/test (70/15/15), and exports CSV files plus
a README with dataset statistics.

Requirements: AC-7.5.5.1, AC-7.5.5.5

Usage:
    PYTHONPATH=. python scripts/export_dataset.py
    PYTHONPATH=. python scripts/export_dataset.py --output data/feedback/verified_dataset
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.dataset_exporter import DatasetExporter
from src.feedback.feedback_storage import FeedbackStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

FEEDBACK_DIR = Path("data/feedback")
DEFAULT_OUTPUT = FEEDBACK_DIR / "verified_dataset"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export verified feedback as CSV dataset."
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_OUTPUT),
        help="Output directory for CSV files (default: %(default)s)",
    )
    args = parser.parse_args()
    output_dir = Path(args.output)

    storage = FeedbackStorage(feedback_dir=FEEDBACK_DIR)
    feedback = storage.load_all_feedback()

    if not feedback:
        logger.warning("No feedback data found in %s", FEEDBACK_DIR)
        print("No feedback data found. Collect some feedback first.")
        return

    exporter = DatasetExporter()
    correct = exporter.filter_correct_detections(feedback)

    if not correct:
        logger.warning("No correct detections to export.")
        print("No correct detections found in feedback data.")
        return

    train, val, test = exporter.split_dataset(correct)

    output_dir.mkdir(parents=True, exist_ok=True)
    exporter.export_csv(train, output_dir / "train.csv")
    exporter.export_csv(val, output_dir / "validation.csv")
    exporter.export_csv(test, output_dir / "test.csv")

    # Compute statistics for README
    sector_counts: Counter[int] = Counter()
    ring_counts: Counter[str] = Counter()
    for fb in correct:
        actual = fb.get("actual_score", {})
        sector = actual.get("sector")
        ring = actual.get("ring")
        if sector is not None:
            sector_counts[sector] += 1
        if ring is not None:
            ring_counts[ring] += 1

    stats = {
        "total_samples": len(correct),
        "train_samples": len(train),
        "val_samples": len(val),
        "test_samples": len(test),
        "per_sector_counts": dict(sector_counts),
        "per_ring_counts": dict(ring_counts),
    }

    exporter.generate_readme(stats, output_dir / "README.md")

    print(f"\nDataset Export Summary")
    print(f"{'=' * 30}")
    print(f"Total correct:  {len(correct)}")
    print(f"Train:          {len(train)}")
    print(f"Validation:     {len(val)}")
    print(f"Test:           {len(test)}")
    print(f"\nExported to: {output_dir}")


if __name__ == "__main__":
    main()
