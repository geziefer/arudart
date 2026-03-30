"""
Feedback data storage for the human feedback system.

Persists feedback data with complete context (metadata, images) in an
organized directory structure. Feedback is stored under data/feedback/
with correct/ and incorrect/ subdirectories.

Requirements: AC-7.5.2.1, AC-7.5.2.2, AC-7.5.2.3, AC-7.5.2.4, AC-7.5.2.5
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.feedback.score_parser import ParsedScore

logger = logging.getLogger(__name__)


def _parsed_score_to_dict(score: ParsedScore) -> dict:
    """Serialize a ParsedScore to a JSON-compatible dictionary.

    Args:
        score: ParsedScore instance.

    Returns:
        Dictionary with ring, sector, and total keys.
    """
    return {
        "ring": score.ring,
        "sector": score.sector,
        "total": score.total,
    }


def _score_to_label(score: ParsedScore) -> str:
    """Convert a ParsedScore to a short label for directory naming.

    Examples:
        triple/20 → "T20"
        double/16 → "D16"
        single/5  → "S5"
        bull      → "DB"
        single_bull → "SB"
        miss      → "Miss"

    Args:
        score: ParsedScore instance.

    Returns:
        Short label string.
    """
    ring = score.ring
    sector = score.sector
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


class FeedbackStorage:
    """Persist feedback data with complete context in organized directories.

    Feedback entries are stored under a base directory with correct/ and
    incorrect/ subdirectories. Each entry gets a unique timestamp-based
    directory containing metadata.json and copied image files.
    """

    def __init__(self, feedback_dir: str | Path = "data/feedback") -> None:
        """Initialize FeedbackStorage.

        Args:
            feedback_dir: Base directory for feedback storage.
        """
        self.feedback_dir = Path(feedback_dir)
        self.correct_dir = self.feedback_dir / "correct"
        self.incorrect_dir = self.feedback_dir / "incorrect"

    def save_feedback(self, feedback_data: dict) -> str:
        """Save a feedback entry with metadata and images.

        Args:
            feedback_data: Dictionary with keys:
                detected_score (ParsedScore), actual_score (ParsedScore),
                is_correct (bool), user_response (str),
                dart_hit_event (DartHitEvent), image_paths (dict).

        Returns:
            Unique feedback ID string.
        """
        detected_score: ParsedScore = feedback_data["detected_score"]
        actual_score: ParsedScore = feedback_data["actual_score"]
        is_correct: bool = feedback_data["is_correct"]

        # Generate unique ID from current timestamp + detected score label
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        detected_label = _score_to_label(detected_score)

        if is_correct:
            feedback_id = f"{timestamp_str}_{detected_label}"
            subdir = self.correct_dir
        else:
            actual_label = _score_to_label(actual_score)
            feedback_id = f"{timestamp_str}_{detected_label}_actual_{actual_label}"
            subdir = self.incorrect_dir

        entry_dir = subdir / feedback_id

        # Ensure uniqueness — append microseconds if directory exists
        if entry_dir.exists():
            micro = now.strftime("%f")
            if is_correct:
                feedback_id = f"{timestamp_str}_{micro}_{detected_label}"
            else:
                actual_label = _score_to_label(actual_score)
                feedback_id = (
                    f"{timestamp_str}_{micro}_{detected_label}_actual_{actual_label}"
                )
            entry_dir = subdir / feedback_id

        entry_dir.mkdir(parents=True, exist_ok=True)

        # Copy images
        saved_image_paths = self._copy_images(
            feedback_data.get("image_paths", {}), entry_dir
        )

        # Build metadata
        dart_hit_event = feedback_data["dart_hit_event"]
        metadata = {
            "feedback_id": feedback_id,
            "timestamp": now.isoformat(),
            "detected_score": _parsed_score_to_dict(detected_score),
            "actual_score": _parsed_score_to_dict(actual_score),
            "is_correct": is_correct,
            "user_response": feedback_data.get("user_response", ""),
            "dart_hit_event": dart_hit_event.to_dict(),
            "image_paths": saved_image_paths,
        }

        metadata_path = entry_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info("Feedback saved to: %s", entry_dir)
        return feedback_id

    def load_all_feedback(self) -> list[dict]:
        """Load all saved feedback entries.

        Scans correct/ and incorrect/ directories for metadata.json files.

        Returns:
            List of metadata dictionaries.
        """
        entries: list[dict] = []
        for subdir in (self.correct_dir, self.incorrect_dir):
            if not subdir.exists():
                continue
            for entry_dir in sorted(subdir.iterdir()):
                if not entry_dir.is_dir():
                    continue
                metadata_path = entry_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path) as f:
                        entries.append(json.load(f))
        return entries

    def _copy_images(
        self, image_paths: dict, dest_dir: Path
    ) -> dict:
        """Copy images from source paths to the feedback directory.

        Args:
            image_paths: Mapping of camera_id → image path(s).
                Values can be a single path string or a dict of
                {type: path} (e.g., {"pre": "...", "post": "...", "annotated": "..."}).
            dest_dir: Destination directory.

        Returns:
            Updated image_paths dict with relative filenames in dest_dir.
        """
        saved: dict = {}
        for cam_id, paths in image_paths.items():
            if isinstance(paths, dict):
                cam_saved: dict = {}
                for img_type, src_path in paths.items():
                    copied = self._copy_single_image(
                        src_path, dest_dir, f"cam{cam_id}_{img_type}"
                    )
                    cam_saved[img_type] = copied
                saved[str(cam_id)] = cam_saved
            else:
                # Single path string
                copied = self._copy_single_image(
                    paths, dest_dir, f"cam{cam_id}"
                )
                saved[str(cam_id)] = copied
        return saved

    @staticmethod
    def _copy_single_image(
        src_path: str | Path, dest_dir: Path, name_prefix: str
    ) -> str | None:
        """Copy a single image file to dest_dir.

        Args:
            src_path: Source image path.
            dest_dir: Destination directory.
            name_prefix: Prefix for the destination filename.

        Returns:
            Relative filename in dest_dir, or None if source missing.
        """
        src = Path(src_path)
        if not src.exists():
            logger.error("Image not found: %s", src)
            return None
        suffix = src.suffix or ".jpg"
        dest_name = f"{name_prefix}{suffix}"
        dest = dest_dir / dest_name
        shutil.copy2(src, dest)
        return dest_name
