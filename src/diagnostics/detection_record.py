"""Detection record data models for diagnostic logging.

Defines CameraDiagnostic and DetectionRecord dataclasses that wrap
DartHitEvent data with additional per-camera deviation analysis.
"""

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CameraDiagnostic:
    """Per-camera diagnostic data including deviation from fused position.

    Attributes:
        camera_id: Camera identifier.
        pixel_x: Detected tip X in pixel coordinates.
        pixel_y: Detected tip Y in pixel coordinates.
        board_x: Mapped board X coordinate in mm.
        board_y: Mapped board Y coordinate in mm.
        confidence: Detection confidence in [0, 1].
        deviation_mm: Euclidean distance from fused position in mm.
        deviation_dx: X component of deviation vector (camera - fused) in mm.
        deviation_dy: Y component of deviation vector (camera - fused) in mm.
    """

    camera_id: int
    pixel_x: float
    pixel_y: float
    board_x: float
    board_y: float
    confidence: float
    deviation_mm: float
    deviation_dx: float
    deviation_dy: float

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "camera_id": self.camera_id,
            "pixel": {"x": self.pixel_x, "y": self.pixel_y},
            "board": {"x_mm": self.board_x, "y_mm": self.board_y},
            "confidence": self.confidence,
            "deviation_mm": self.deviation_mm,
            "deviation_vector": {
                "dx_mm": self.deviation_dx,
                "dy_mm": self.deviation_dy,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CameraDiagnostic":
        """Deserialize from a dictionary."""
        return cls(
            camera_id=data["camera_id"],
            pixel_x=data["pixel"]["x"],
            pixel_y=data["pixel"]["y"],
            board_x=data["board"]["x_mm"],
            board_y=data["board"]["y_mm"],
            confidence=data["confidence"],
            deviation_mm=data["deviation_mm"],
            deviation_dx=data["deviation_vector"]["dx_mm"],
            deviation_dy=data["deviation_vector"]["dy_mm"],
        )


@dataclass
class DetectionRecord:
    """Structured diagnostic record for a single dart detection.

    Wraps a DartHitEvent with additional per-camera deviation analysis.
    Supports JSON serialization for diagnostic logging.

    Attributes:
        timestamp: ISO 8601 formatted timestamp.
        board_x: Fused board X coordinate in mm.
        board_y: Fused board Y coordinate in mm.
        radius: Distance from board center in mm.
        angle_deg: Angle in degrees [0, 360).
        ring: Ring classification name.
        sector: Sector number (1-20), or None for bulls/miss.
        score_total: Final computed score.
        score_base: Base score value.
        score_multiplier: Score multiplier.
        fusion_confidence: Combined confidence from fusion.
        cameras_used: List of camera IDs that contributed.
        camera_data: List of per-camera diagnostic entries.
        image_paths: Mapping of camera_id to annotated image path.
    """

    timestamp: str
    board_x: float
    board_y: float
    radius: float
    angle_deg: float
    ring: str
    sector: Optional[int]
    score_total: int
    score_base: int
    score_multiplier: int
    fusion_confidence: float
    cameras_used: list[int]
    camera_data: list[CameraDiagnostic] = field(default_factory=list)
    image_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "timestamp": self.timestamp,
            "fused_position": {"x_mm": self.board_x, "y_mm": self.board_y},
            "polar": {"radius_mm": self.radius, "angle_deg": self.angle_deg},
            "classification": {"ring": self.ring, "sector": self.sector},
            "score": {
                "base": self.score_base,
                "multiplier": self.score_multiplier,
                "total": self.score_total,
            },
            "fusion_confidence": self.fusion_confidence,
            "cameras_used": self.cameras_used,
            "camera_data": [c.to_dict() for c in self.camera_data],
            "image_paths": self.image_paths,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DetectionRecord":
        """Deserialize from a dictionary."""
        return cls(
            timestamp=data["timestamp"],
            board_x=data["fused_position"]["x_mm"],
            board_y=data["fused_position"]["y_mm"],
            radius=data["polar"]["radius_mm"],
            angle_deg=data["polar"]["angle_deg"],
            ring=data["classification"]["ring"],
            sector=data["classification"]["sector"],
            score_total=data["score"]["total"],
            score_base=data["score"]["base"],
            score_multiplier=data["score"]["multiplier"],
            fusion_confidence=data["fusion_confidence"],
            cameras_used=data["cameras_used"],
            camera_data=[
                CameraDiagnostic.from_dict(c) for c in data.get("camera_data", [])
            ],
            image_paths=data.get("image_paths", {}),
        )

    @classmethod
    def from_dart_hit_event(cls, event: "DartHitEvent") -> "DetectionRecord":
        """Create a DetectionRecord from a DartHitEvent.

        Computes per-camera deviation vectors and Euclidean distances
        from the fused board position.

        Args:
            event: A DartHitEvent from the scoring pipeline.

        Returns:
            A DetectionRecord with computed camera deviations.
        """
        from src.fusion.dart_hit_event import DartHitEvent  # noqa: F811

        camera_data = []
        for detection in event.detections:
            dx = detection.board_x - event.board_x
            dy = detection.board_y - event.board_y
            deviation_mm = math.sqrt(dx * dx + dy * dy)
            camera_data.append(
                CameraDiagnostic(
                    camera_id=detection.camera_id,
                    pixel_x=detection.pixel_x,
                    pixel_y=detection.pixel_y,
                    board_x=detection.board_x,
                    board_y=detection.board_y,
                    confidence=detection.confidence,
                    deviation_mm=deviation_mm,
                    deviation_dx=dx,
                    deviation_dy=dy,
                )
            )

        return cls(
            timestamp=event.timestamp,
            board_x=event.board_x,
            board_y=event.board_y,
            radius=event.radius,
            angle_deg=event.angle_deg,
            ring=event.score.ring,
            sector=event.score.sector,
            score_total=event.score.total,
            score_base=event.score.base,
            score_multiplier=event.score.multiplier,
            fusion_confidence=event.fusion_confidence,
            cameras_used=event.cameras_used,
            camera_data=camera_data,
            image_paths=event.image_paths,
        )
