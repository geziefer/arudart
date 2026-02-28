"""
Calibration module for ARU-DART coordinate mapping.

This module provides spiderweb-based calibration using the dartboard's natural
wire structure (bull, rings, radial wires) as reference points. Each camera
gets its own homography computed from features visible in its perspective.

Main components:
- CoordinateMapper: Main interface for pixel-to-board coordinate transformation
- FeatureDetector: Detects dartboard features (bull, rings, wires)
- FeatureMatcher: Maps detected features to known board coordinates
- HomographyCalculator: Computes homography matrix from matched points
- CalibrationManager: Orchestrates calibration lifecycle with continuous validation
- IntrinsicCalibrator: Handles chessboard-based intrinsic calibration
"""

from .feature_detector import FeatureDetector, FeatureDetectionResult, RadialWire, WireIntersection
from .feature_matcher import FeatureMatcher, PointPair

__all__ = [
    'FeatureDetector',
    'FeatureDetectionResult',
    'RadialWire',
    'WireIntersection',
    'FeatureMatcher',
    'PointPair',
]
