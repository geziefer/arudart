"""Diagnostic session logger for the ARU-DART scoring pipeline.

Manages a diagnostic session: creates the session directory, writes per-throw
JSON records and annotated images, and produces a session summary on close.
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from src.diagnostics.detection_record import DetectionRecord

logger = logging.getLogger(__name__)


class DiagnosticLogger:
    """Manages diagnostic logging for a single scoring session.

    Creates a session directory on initialization, logs per-throw detection
    records as JSON files with annotated images, and writes a session summary
    with aggregate statistics.

    Attributes:
        session_dir: Read-only path to the current session directory.
    """

    def __init__(self, base_dir: str = "data/diagnostics") -> None:
        """Initialize a new diagnostic session.

        Creates a session directory named ``Session_NNN_YYYY-MM-DD_HH-MM-SS``
        under *base_dir*, where NNN is a zero-padded sequential number derived
        from existing session directories.

        Args:
            base_dir: Root directory for all diagnostic sessions.

        Raises:
            OSError: If the session directory cannot be created.
        """
        base_path = Path(base_dir)
        try:
            base_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(
                f"Cannot create diagnostics base directory '{base_dir}': {exc}"
            ) from exc

        session_number = self._next_session_number(base_path)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dir_name = f"Session_{session_number:03d}_{timestamp}"

        self._session_dir = base_path / dir_name
        try:
            self._session_dir.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise OSError(
                f"Cannot create session directory '{self._session_dir}': {exc}"
            ) from exc

        self._throw_count: int = 0
        self._records: list[DetectionRecord] = []

        logger.info("Diagnostic session started: %s", self._session_dir)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def session_dir(self) -> Path:
        """Read-only path to the current session directory."""
        return self._session_dir

    def log_detection(self, event: "DartHitEvent") -> DetectionRecord:  # noqa: F821
        """Log a single dart detection event.

        Creates a :class:`DetectionRecord` from the event, writes it as a
        numbered JSON file, copies any annotated images into the session
        directory, and appends the record to the internal list.

        Args:
            event: A DartHitEvent from the scoring pipeline.

        Returns:
            The DetectionRecord created from the event.
        """
        record = DetectionRecord.from_dart_hit_event(event)
        self._throw_count += 1

        # Write per-throw JSON: throw_NNN_HH-MM-SS.json
        now = datetime.now().strftime("%H-%M-%S")
        json_name = f"throw_{self._throw_count:03d}_{now}.json"
        json_path = self._session_dir / json_name
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(record.to_dict(), fh, indent=2)
        logger.info("Wrote detection record: %s", json_path)

        # Copy annotated images into session directory
        for cam_key, img_src in record.image_paths.items():
            src_path = Path(img_src)
            if not src_path.exists():
                logger.warning(
                    "Annotated image not found, skipping copy: %s", src_path
                )
                continue
            dest_name = (
                f"throw_{self._throw_count:03d}_cam{cam_key}_{src_path.name}"
            )
            dest_path = self._session_dir / dest_name
            try:
                shutil.copy2(str(src_path), str(dest_path))
                logger.debug("Copied image: %s -> %s", src_path, dest_path)
            except OSError as exc:
                logger.warning("Failed to copy image %s: %s", src_path, exc)

        self._records.append(record)
        return record

    def write_session_summary(self) -> None:
        """Write a session summary JSON file with aggregate statistics.

        Computes total throws, successful detections (non-zero cameras_used),
        average fusion confidence, and per-camera aggregate deviation stats
        (mean/max deviation, mean deviation vector dx/dy).
        """
        total_throws = len(self._records)
        successful_detections = sum(
            1 for r in self._records if len(r.cameras_used) > 0
        )

        if total_throws > 0:
            avg_fusion_confidence = sum(
                r.fusion_confidence for r in self._records
            ) / total_throws
        else:
            avg_fusion_confidence = 0.0

        # Per-camera aggregate stats
        per_camera_stats = self._compute_per_camera_stats()

        summary = {
            "session_dir": str(self._session_dir),
            "total_throws": total_throws,
            "successful_detections": successful_detections,
            "average_fusion_confidence": round(avg_fusion_confidence, 6),
            "per_camera_stats": per_camera_stats,
        }

        summary_path = self._session_dir / "session_summary.json"
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        logger.info("Wrote session summary: %s", summary_path)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _next_session_number(base_path: Path) -> int:
        """Find the next sequential session number.

        Scans *base_path* for directories matching ``Session_NNN_*`` and
        returns max(NNN) + 1, or 1 if none exist.
        """
        max_num = 0
        if base_path.exists():
            for child in base_path.iterdir():
                if child.is_dir() and child.name.startswith("Session_"):
                    parts = child.name.split("_", 2)
                    if len(parts) >= 2:
                        try:
                            num = int(parts[1])
                            max_num = max(max_num, num)
                        except ValueError:
                            continue
        return max_num + 1

    def _compute_per_camera_stats(self) -> dict:
        """Compute per-camera aggregate deviation statistics.

        Returns:
            Dict keyed by camera_id (str) with mean_deviation_mm,
            max_deviation_mm, and mean_deviation_vector {dx_mm, dy_mm}.
        """
        # Collect deviations per camera
        camera_deviations: dict[int, list[tuple[float, float, float]]] = {}
        for record in self._records:
            for cam in record.camera_data:
                if cam.camera_id not in camera_deviations:
                    camera_deviations[cam.camera_id] = []
                camera_deviations[cam.camera_id].append(
                    (cam.deviation_mm, cam.deviation_dx, cam.deviation_dy)
                )

        stats: dict[str, dict] = {}
        for cam_id, devs in sorted(camera_deviations.items()):
            n = len(devs)
            mean_dev = sum(d[0] for d in devs) / n
            max_dev = max(d[0] for d in devs)
            mean_dx = sum(d[1] for d in devs) / n
            mean_dy = sum(d[2] for d in devs) / n
            stats[str(cam_id)] = {
                "mean_deviation_mm": round(mean_dev, 6),
                "max_deviation_mm": round(max_dev, 6),
                "mean_deviation_vector": {
                    "dx_mm": round(mean_dx, 6),
                    "dy_mm": round(mean_dy, 6),
                },
            }

        return stats
