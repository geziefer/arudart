"""
Score calculation and event creation for dart hit scoring pipeline.

Orchestrates the complete fusion and scoring pipeline: coordinate fusion,
polar conversion, ring/sector determination, score calculation, and
DartHitEvent creation.
"""

import datetime
import logging
from typing import Optional

from .coordinate_fusion import CoordinateFusion
from .dart_hit_event import CameraDetection, DartHitEvent, Score
from .polar_converter import PolarConverter
from .ring_detector import RingDetector
from .sector_detector import SectorDetector

logger = logging.getLogger(__name__)


class ScoreCalculator:
    """Orchestrate fusion and scoring pipeline to produce DartHitEvents.

    Combines per-camera detections into a single fused position, converts
    to polar coordinates, determines ring and sector, calculates the score,
    and assembles a complete DartHitEvent.

    Args:
        config: Configuration dictionary with 'fusion', 'board', and
            'board.sectors' sections.
    """

    def __init__(self, config: dict) -> None:
        self.coordinate_fusion = CoordinateFusion(config)
        self.polar_converter = PolarConverter(config)
        self.ring_detector = RingDetector(config)
        self.sector_detector = SectorDetector(config)

    def process_detections(
        self,
        detections: list[dict],
        image_paths: Optional[dict[str, str]] = None,
    ) -> Optional[DartHitEvent]:
        """Run the full scoring pipeline on a set of camera detections.

        Pipeline: fusion -> polar -> ring -> sector -> score -> event.

        Args:
            detections: List of detection dicts, each with keys:
                - camera_id: int
                - pixel: tuple (u, v)
                - board: tuple (x, y) in mm
                - confidence: float in [0, 1]
            image_paths: Optional mapping of camera_id to image file path.

        Returns:
            A DartHitEvent with all scoring data, or None if fusion fails.
        """
        # 1. Fuse coordinates
        fusion_result = self.coordinate_fusion.fuse_detections(detections)
        if fusion_result is None:
            logger.warning("No valid detections after fusion")
            return None

        fused_x, fused_y, confidence, cameras_used = fusion_result

        # 2. Convert to polar
        r, theta = self.polar_converter.cartesian_to_polar(fused_x, fused_y)
        angle_deg = self.polar_converter.radians_to_degrees(theta)

        # 3. Determine ring
        ring_name, multiplier, base_score = self.ring_detector.determine_ring(r)

        # 4. Determine sector (only needed for regular rings)
        if ring_name in ("bull", "single_bull", "out_of_bounds"):
            sector = None
        else:
            sector = self.sector_detector.determine_sector(theta)

        # 5. Calculate score
        score = self.calculate_score(ring_name, multiplier, base_score, sector)

        # 6. Create event
        event = self._create_event(
            fused_x=fused_x,
            fused_y=fused_y,
            r=r,
            theta=theta,
            angle_deg=angle_deg,
            score=score,
            confidence=confidence,
            cameras_used=cameras_used,
            detections=detections,
            image_paths=image_paths,
        )

        logger.info(
            "Scored %d (%s %s) at (%.1f, %.1f) r=%.1f θ=%.1f°",
            score.total,
            ring_name,
            sector if sector is not None else "",
            fused_x,
            fused_y,
            r,
            angle_deg,
        )

        return event

    def calculate_score(
        self,
        ring_name: str,
        multiplier: int,
        base_score: int,
        sector: Optional[int],
    ) -> Score:
        """Calculate the final score from ring and sector information.

        Args:
            ring_name: Ring classification name.
            multiplier: Ring multiplier (0, 1, 2, or 3).
            base_score: Base score from ring (50 for bull, 25 for single bull).
            sector: Sector number (1-20), or None for bulls/miss.

        Returns:
            Score object with all fields populated.
        """
        if ring_name == "bull":
            return Score(base=50, multiplier=0, total=50, ring="bull", sector=None)
        elif ring_name == "single_bull":
            return Score(
                base=25, multiplier=0, total=25, ring="single_bull", sector=None
            )
        elif ring_name == "out_of_bounds":
            return Score(
                base=0, multiplier=0, total=0, ring="out_of_bounds", sector=None
            )
        else:
            total = sector * multiplier
            return Score(
                base=sector,
                multiplier=multiplier,
                total=total,
                ring=ring_name,
                sector=sector,
            )

    def _create_event(
        self,
        fused_x: float,
        fused_y: float,
        r: float,
        theta: float,
        angle_deg: float,
        score: Score,
        confidence: float,
        cameras_used: list[int],
        detections: list[dict],
        image_paths: Optional[dict[str, str]],
    ) -> DartHitEvent:
        """Assemble a DartHitEvent from pipeline results.

        Args:
            fused_x: Fused board X coordinate in mm.
            fused_y: Fused board Y coordinate in mm.
            r: Radius from board center in mm.
            theta: Angle in radians.
            angle_deg: Angle in degrees.
            score: Calculated Score object.
            confidence: Combined fusion confidence.
            cameras_used: List of camera IDs that contributed.
            detections: Original detection dicts.
            image_paths: Optional camera_id to image path mapping.

        Returns:
            Fully populated DartHitEvent.
        """
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        camera_detections = [
            CameraDetection(
                camera_id=d["camera_id"],
                pixel_x=d["pixel"][0],
                pixel_y=d["pixel"][1],
                board_x=d["board"][0],
                board_y=d["board"][1],
                confidence=d["confidence"],
            )
            for d in detections
        ]

        return DartHitEvent(
            timestamp=timestamp,
            board_x=fused_x,
            board_y=fused_y,
            radius=r,
            angle_rad=theta,
            angle_deg=angle_deg,
            score=score,
            fusion_confidence=confidence,
            cameras_used=cameras_used,
            num_cameras=len(cameras_used),
            detections=camera_detections,
            image_paths=image_paths if image_paths is not None else {},
        )
