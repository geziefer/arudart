"""
Calibration module for ARU-DART coordinate mapping.

This module provides manual control point calibration as the primary method,
with optional automatic feature detection. Each camera gets its own homography
computed from user-clicked control points or detected features.

Main components:
- CoordinateMapper: Main interface for pixel-to-board coordinate transformation
- BoardGeometry: Dartboard dimensions and spiderweb projection
- ManualCalibrator: Interactive control point selection (PRIMARY METHOD)
- HomographyCalculator: Computes homography matrix from matched points
- FeatureDetector: Detects dartboard features (bull, rings, sector boundaries via color) [OPTIONAL]
- FeatureMatcher: Maps detected features to known board coordinates [OPTIONAL]
- CalibrationManager: Orchestrates calibration lifecycle with continuous validation
- IntrinsicCalibrator: Handles chessboard-based intrinsic calibration
"""

from .board_geometry import BoardGeometry
from .calibration_manager import CalibrationManager, CalibrationStatus
from .coordinate_mapper import CoordinateMapper
from .feature_detector import FeatureDetector, FeatureDetectionResult, SectorBoundary, BoundaryIntersection
from .feature_matcher import FeatureMatcher, PointPair
from .homography_calculator import HomographyCalculator
from .manual_calibrator import ManualCalibrator

__all__ = [
    'BoardGeometry',
    'CalibrationManager',
    'CalibrationStatus',
    'CoordinateMapper',
    'ManualCalibrator',
    'HomographyCalculator',
    'FeatureDetector',
    'FeatureDetectionResult',
    'SectorBoundary',
    'BoundaryIntersection',
    'FeatureMatcher',
    'PointPair',
]
