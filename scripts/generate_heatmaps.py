#!/usr/bin/env python3
"""
Generate accuracy heatmaps from feedback data.

Loads all feedback from data/feedback/, generates an overall heatmap
plus per-ring heatmaps (singles, doubles, triples), and saves them
as PNG images.

Requirements: AC-7.5.4.5

Usage:
    PYTHONPATH=. python scripts/generate_heatmaps.py
"""

import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.heatmap_generator import HeatmapGenerator
from src.feedback.feedback_storage import FeedbackStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

FEEDBACK_DIR = Path("data/feedback")


def main() -> None:
    storage = FeedbackStorage(feedback_dir=FEEDBACK_DIR)
    feedback = storage.load_all_feedback()

    if not feedback:
        logger.warning("No feedback data found in %s", FEEDBACK_DIR)
        print("No feedback data found. Collect some feedback first.")
        return

    generator = HeatmapGenerator()

    heatmaps = {
        "accuracy_heatmap.png": None,
        "accuracy_heatmap_singles.png": "single",
        "accuracy_heatmap_doubles.png": "double",
        "accuracy_heatmap_triples.png": "triple",
    }

    for filename, ring_filter in heatmaps.items():
        label = ring_filter or "overall"
        image = generator.generate_heatmap(feedback, ring_filter=ring_filter)
        output_path = FEEDBACK_DIR / filename
        generator.save_heatmap(image, output_path)
        print(f"Saved {label} heatmap: {output_path}")

    print(f"\nAll heatmaps saved to {FEEDBACK_DIR}")


if __name__ == "__main__":
    main()
