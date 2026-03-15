"""
Data models for dart hit events.

Defines the core dataclasses used throughout the fusion and scoring pipeline:
- Score: Final score with base, multiplier, total, ring, and sector
- CameraDetection: Per-camera detection data (pixel + board coordinates)
- DartHitEvent: Complete dart throw event with all detection and scoring info
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Score:
    """Dart score with base value, multiplier, and ring classification.

    Attributes:
        base: Base score (1-20 for sectors, 50 for bull, 25 for single bull, 0 for miss).
        multiplier: Score multiplier (0, 1, 2, or 3).
        total: Final computed score (base * multiplier, or fixed for bulls/miss).
        ring: Ring classification name.
        sector: Sector number (1-20), or None for bulls/miss.
    """

    base: int
    multiplier: int
    total: int
    ring: str
    sector: Optional[int]

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "base": self.base,
            "multiplier": self.multiplier,
            "total": self.total,
            "ring": self.ring,
            "sector": self.sector,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Score":
        """Deserialize from a dictionary."""
        return cls(
            base=data["base"],
            multiplier=data["multiplier"],
            total=data["total"],
            ring=data["ring"],
            sector=data.get("sector"),
        )


@dataclass
class CameraDetection:
    """Per-camera detection data with pixel and board coordinates.

    Attributes:
        camera_id: Camera identifier.
        pixel_x: Detected tip X in pixel coordinates.
        pixel_y: Detected tip Y in pixel coordinates.
        board_x: Mapped board X coordinate in mm.
        board_y: Mapped board Y coordinate in mm.
        confidence: Detection confidence in [0, 1].
    """

    camera_id: int
    pixel_x: float
    pixel_y: float
    board_x: float
    board_y: float
    confidence: float

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "camera_id": self.camera_id,
            "pixel": {"x": self.pixel_x, "y": self.pixel_y},
            "board": {"x": self.board_x, "y": self.board_y},
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CameraDetection":
        """Deserialize from a dictionary."""
        return cls(
            camera_id=data["camera_id"],
            pixel_x=data["pixel"]["x"],
            pixel_y=data["pixel"]["y"],
            board_x=data["board"]["x"],
            board_y=data["board"]["y"],
            confidence=data["confidence"],
        )


@dataclass
class DartHitEvent:
    """Complete dart throw event with detection, fusion, and scoring data.

    Attributes:
        timestamp: ISO 8601 formatted timestamp.
        board_x: Fused board X coordinate in mm.
        board_y: Fused board Y coordinate in mm.
        radius: Distance from board center in mm.
        angle_rad: Angle in radians [0, 2π).
        angle_deg: Angle in degrees [0, 360).
        score: Score object with base, multiplier, total, ring, sector.
        fusion_confidence: Combined confidence from fusion.
        cameras_used: List of camera IDs that contributed.
        num_cameras: Count of cameras used.
        detections: List of per-camera CameraDetection objects.
        image_paths: Mapping of camera_id to annotated image path.
    """

    timestamp: str
    board_x: float
    board_y: float
    radius: float
    angle_rad: float
    angle_deg: float
    score: Score
    fusion_confidence: float
    cameras_used: list[int]
    num_cameras: int
    detections: list[CameraDetection]
    image_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "timestamp": self.timestamp,
            "board_coordinates": {
                "x_mm": self.board_x,
                "y_mm": self.board_y,
            },
            "polar_coordinates": {
                "radius_mm": self.radius,
                "angle_rad": self.angle_rad,
                "angle_deg": self.angle_deg,
            },
            "score": self.score.to_dict(),
            "fusion": {
                "confidence": self.fusion_confidence,
                "cameras_used": self.cameras_used,
                "num_cameras": self.num_cameras,
            },
            "detections": [d.to_dict() for d in self.detections],
            "image_paths": self.image_paths,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DartHitEvent":
        """Deserialize from a dictionary."""
        return cls(
            timestamp=data["timestamp"],
            board_x=data["board_coordinates"]["x_mm"],
            board_y=data["board_coordinates"]["y_mm"],
            radius=data["polar_coordinates"]["radius_mm"],
            angle_rad=data["polar_coordinates"]["angle_rad"],
            angle_deg=data["polar_coordinates"]["angle_deg"],
            score=Score.from_dict(data["score"]),
            fusion_confidence=data["fusion"]["confidence"],
            cameras_used=data["fusion"]["cameras_used"],
            num_cameras=data["fusion"]["num_cameras"],
            detections=[CameraDetection.from_dict(d) for d in data["detections"]],
            image_paths=data.get("image_paths", {}),
        )
