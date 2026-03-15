"""
Fusion module for ARU-DART multi-camera coordinate fusion and score derivation.

This module combines per-camera dart detections into a single fused position,
converts to polar coordinates, determines ring and sector, and calculates
the final dart score.

Main components:
- DartHitEvent: Complete dart throw event dataclass
- Score: Score dataclass (base, multiplier, total, ring, sector)
- CameraDetection: Per-camera detection dataclass
"""

from .coordinate_fusion import CoordinateFusion
from .dart_hit_event import CameraDetection, DartHitEvent, Score
from .polar_converter import PolarConverter
from .ring_detector import RingDetector
from .score_calculator import ScoreCalculator
from .sector_detector import SectorDetector

__all__ = [
    "CameraDetection",
    "CoordinateFusion",
    "DartHitEvent",
    "PolarConverter",
    "RingDetector",
    "Score",
    "ScoreCalculator",
    "SectorDetector",
]
