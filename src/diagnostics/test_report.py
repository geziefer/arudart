"""Test report data models and report generation for accuracy testing.

Defines TestReport dataclass for structured accuracy test results and
TestReportGenerator for aggregating per-throw results into overall metrics.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestReport:
    """Structured accuracy test report.

    Contains overall metrics, per-throw detail, and per-camera deviation
    statistics from an accuracy test session.

    Attributes:
        session_dir: Path to the diagnostic session directory.
        overall: Dict with total_throws, sector_match_rate, ring_match_rate,
            score_match_rate, mean_position_error_mm, max_position_error_mm.
        per_throw: List of per-throw result dicts.
        per_camera: Dict of camera_id to mean/max deviation stats.
    """

    session_dir: str
    overall: dict[str, Any]
    per_throw: list[dict[str, Any]]
    per_camera: dict[str, dict[str, float]]

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "session_dir": self.session_dir,
            "overall": dict(self.overall),
            "per_throw": [dict(t) for t in self.per_throw],
            "per_camera": {
                k: dict(v) for k, v in self.per_camera.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestReport":
        """Deserialize from a dictionary."""
        return cls(
            session_dir=data["session_dir"],
            overall=data["overall"],
            per_throw=data["per_throw"],
            per_camera=data["per_camera"],
        )

    def print_summary(self) -> None:
        """Print a human-readable summary to the console (ASCII only)."""
        o = self.overall
        print("=== Accuracy Test Report ===")
        print(f"Total throws: {o['total_throws']}")
        print(f"Sector match rate: {o['sector_match_rate']}%")
        print(f"Ring match rate: {o['ring_match_rate']}%")
        print(f"Score match rate: {o['score_match_rate']}%")
        print(f"Mean position error: {o['mean_position_error_mm']} mm")
        print(f"Max position error: {o['max_position_error_mm']} mm")


class TestReportGenerator:
    """Aggregates per-throw accuracy results into a TestReport."""

    @staticmethod
    def generate_report(
        results: list[dict[str, Any]],
        diagnostic_logger: Any,
    ) -> TestReport:
        """Generate a TestReport from per-throw accuracy results.

        Args:
            results: List of per-throw result dicts, each containing:
                target_name, expected_score, detected_score,
                position_error_mm, angular_error_deg, ring_match,
                sector_match, score_match, record (DetectionRecord).
            diagnostic_logger: DiagnosticLogger instance for session info
                and per-camera deviation data.

        Returns:
            A TestReport with aggregated metrics.
        """
        total = len(results)

        if total == 0:
            overall = {
                "total_throws": 0,
                "sector_match_rate": 0,
                "ring_match_rate": 0,
                "score_match_rate": 0,
                "mean_position_error_mm": 0.0,
                "max_position_error_mm": 0.0,
            }
            return TestReport(
                session_dir=str(diagnostic_logger.session_dir),
                overall=overall,
                per_throw=[],
                per_camera={},
            )

        # Overall metrics
        sector_matches = sum(1 for r in results if r["sector_match"])
        ring_matches = sum(1 for r in results if r["ring_match"])
        score_matches = sum(1 for r in results if r["score_match"])
        position_errors = [r["position_error_mm"] for r in results]

        overall = {
            "total_throws": total,
            "sector_match_rate": round(sector_matches / total * 100, 1),
            "ring_match_rate": round(ring_matches / total * 100, 1),
            "score_match_rate": round(score_matches / total * 100, 1),
            "mean_position_error_mm": round(
                sum(position_errors) / total, 1
            ),
            "max_position_error_mm": round(max(position_errors), 1),
        }

        # Per-throw detail
        per_throw = []
        for r in results:
            per_throw.append({
                "target": r["target_name"],
                "expected_score": r["expected_score"],
                "detected_score": r["detected_score"],
                "position_error_mm": round(r["position_error_mm"], 1),
                "angular_error_deg": round(r["angular_error_deg"], 1),
                "ring_match": r["ring_match"],
                "sector_match": r["sector_match"],
            })

        # Per-camera deviation stats from detection records
        per_camera = TestReportGenerator._compute_per_camera_stats(results)

        return TestReport(
            session_dir=str(diagnostic_logger.session_dir),
            overall=overall,
            per_throw=per_throw,
            per_camera=per_camera,
        )

    @staticmethod
    def _compute_per_camera_stats(
        results: list[dict[str, Any]],
    ) -> dict[str, dict[str, float]]:
        """Compute per-camera mean/max deviation from detection records.

        Args:
            results: Per-throw result dicts containing 'record' keys.

        Returns:
            Dict keyed by camera_id string with mean_deviation_mm and
            max_deviation_mm.
        """
        camera_deviations: dict[str, list[float]] = {}

        for r in results:
            record = r.get("record")
            if record is None:
                continue
            for cam in record.camera_data:
                cam_key = str(cam.camera_id)
                if cam_key not in camera_deviations:
                    camera_deviations[cam_key] = []
                camera_deviations[cam_key].append(cam.deviation_mm)

        per_camera: dict[str, dict[str, float]] = {}
        for cam_id, devs in sorted(camera_deviations.items()):
            per_camera[cam_id] = {
                "mean_deviation_mm": round(sum(devs) / len(devs), 1),
                "max_deviation_mm": round(max(devs), 1),
            }

        return per_camera
