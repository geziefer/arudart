"""
Calibration module for ARU-DART coordinate mapping.

This module provides color-based calibration using the dartboard's natural
color patterns (bull, rings, sector boundaries) as reference points. Each camera
gets its own homography computed from features visible in its perspective.

Main components:
- CoordinateMapper: Main interface for pixel-to-board coordinate transformation
- FeatureDetector: Detects dartboard features (bull, rings, sector boundaries via color)
- FeatureMatcher: Maps detected features to known board coordinates
- HomographyCalculator: Computes homography matrix from matched points
- CalibrationManager: Orchestrates calibration lifecycle with continuous validation
- IntrinsicCalibrator: Handles chessboard-based intrinsic calibration
"""

from .feature_detector import FeatureDetector, FeatureDetectionResult, SectorBoundary, BoundaryIntersection
from .feature_matcher import FeatureMatcher, PointPair

__all__ = [
    'FeatureDetector',
    'FeatureDetectionResult',
    'SectorBoundary',
    'BoundaryIntersection',
    'FeatureMatcher',
    'PointPair',
]
