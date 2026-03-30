"""
Dataset export for the human feedback system.

Filters verified (correct) feedback entries, splits into train/val/test
sets, and exports CSV files with per-camera detection rows. Also
generates a README with dataset statistics.

Requirements: AC-7.5.5.1, AC-7.5.5.2, AC-7.5.5.4, AC-7.5.5.5
"""

from __future__ import annotations

import csv
import logging
import random
from pathlib import Path

from src.analysis.accuracy_analyzer import _score_dict_to_label

logger = logging.getLogger(__name__)


class DatasetExporter:
    """Export verified feedback data as CSV datasets for ML training."""

    def filter_correct_detections(
        self, feedback_list: list[dict]
    ) -> list[dict]:
        """Keep only feedback entries where the detection was correct.

        Args:
            feedback_list: List of feedback metadata dicts.

        Returns:
            Filtered list containing only correct entries.
        """
        return [fb for fb in feedback_list if fb.get("is_correct")]

    def split_dataset(
        self,
        dataset: list,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
    ) -> tuple[list, list, list]:
        """Shuffle and split a dataset into train/val/test subsets.

        The dataset is shuffled in-place using ``random.shuffle`` and
        then split according to the given ratios. The train set receives
        any remainder so that no samples are lost.

        Args:
            dataset: List of items to split.
            train_ratio: Fraction for training set (default 0.70).
            val_ratio: Fraction for validation set (default 0.15).
            test_ratio: Fraction for test set (default 0.15).

        Returns:
            Tuple of (train, val, test) lists.
        """
        data = list(dataset)  # shallow copy to avoid mutating caller's list
        random.shuffle(data)

        total = len(data)
        val_size = round(total * val_ratio)
        test_size = round(total * test_ratio)
        train_size = total - val_size - test_size

        train = data[:train_size]
        val = data[train_size : train_size + val_size]
        test = data[train_size + val_size :]

        return train, val, test

    def export_csv(self, dataset: list[dict], output_path: str | Path) -> None:
        """Write a CSV file with one row per camera detection.

        Each feedback entry is expanded into N rows (one per camera
        detection found in ``dart_hit_event.detections``).

        Columns: timestamp, camera_id, image_path, tip_x, tip_y,
                 actual_score, confidence

        Args:
            dataset: List of feedback metadata dicts.
            output_path: Destination CSV file path.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "timestamp",
            "camera_id",
            "image_path",
            "tip_x",
            "tip_y",
            "actual_score",
            "confidence",
        ]

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for fb in dataset:
                dart_hit = fb.get("dart_hit_event", {})
                timestamp = dart_hit.get("timestamp", "")
                actual_label = _score_dict_to_label(fb.get("actual_score", {}))
                detections = dart_hit.get("detections", [])

                for det in detections:
                    writer.writerow(
                        {
                            "timestamp": timestamp,
                            "camera_id": det.get("camera_id"),
                            "image_path": det.get("image_path", ""),
                            "tip_x": det.get("pixel", {}).get("x"),
                            "tip_y": det.get("pixel", {}).get("y"),
                            "actual_score": actual_label,
                            "confidence": det.get("confidence"),
                        }
                    )

        logger.info("CSV exported to: %s (%d entries)", path, len(dataset))

    def generate_readme(
        self, dataset_stats: dict, output_path: str | Path
    ) -> None:
        """Write a README.md with dataset statistics and usage instructions.

        Args:
            dataset_stats: Dict with keys ``total_samples``,
                ``per_sector_counts``, ``per_ring_counts``,
                ``train_samples``, ``val_samples``, ``test_samples``.
            output_path: Destination file path.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        lines.append("# ARU-DART Verified Dataset")
        lines.append("")
        lines.append("## Statistics")
        lines.append("")
        lines.append(f"- Total samples: {dataset_stats.get('total_samples', 0)}")
        lines.append(f"- Train samples: {dataset_stats.get('train_samples', 0)}")
        lines.append(f"- Validation samples: {dataset_stats.get('val_samples', 0)}")
        lines.append(f"- Test samples: {dataset_stats.get('test_samples', 0)}")
        lines.append("")

        per_sector = dataset_stats.get("per_sector_counts", {})
        if per_sector:
            lines.append("## Per-Sector Distribution")
            lines.append("")
            for sector in sorted(per_sector.keys(), key=lambda s: int(s)):
                lines.append(f"- Sector {sector}: {per_sector[sector]}")
            lines.append("")

        per_ring = dataset_stats.get("per_ring_counts", {})
        if per_ring:
            lines.append("## Per-Ring Distribution")
            lines.append("")
            for ring in sorted(per_ring.keys()):
                lines.append(f"- {ring}: {per_ring[ring]}")
            lines.append("")

        lines.append("## Usage")
        lines.append("")
        lines.append("CSV columns: timestamp, camera_id, image_path, tip_x, tip_y, actual_score, confidence")
        lines.append("")
        lines.append("```python")
        lines.append("import pandas as pd")
        lines.append("")
        lines.append("train = pd.read_csv('train.csv')")
        lines.append("val = pd.read_csv('validation.csv')")
        lines.append("test = pd.read_csv('test.csv')")
        lines.append("```")
        lines.append("")

        path.write_text("\n".join(lines))
        logger.info("README saved to: %s", path)
