"""
Calibration module for ARU-DART coordinate mapping.

This module provides camera calibration and coordinate transformation
from pixel coordinates to board-plane coordinates in millimeters.

Classes:
    CoordinateMapper: Main interface for coordinate transformation
    IntrinsicCalibrator: Intrinsic camera calibration using chessboard
    ExtrinsicCalibrator: Extrinsic calibration using ARUCO markers
    ArucoDetector: ARUCO marker detection utility

Module Structure:
    src/calibration/
    ├── __init__.py              # This file
    ├── coordinate_mapper.py     # CoordinateMapper class (main interface)
    ├── intrinsic_calibrator.py  # IntrinsicCalibrator class
    ├── extrinsic_calibrator.py  # ExtrinsicCalibrator class
    └── aruco_detector.py        # ArucoDetector class

    calibration/
    ├── generate_aruco_markers.py    # Marker generation script
    ├── calibrate_intrinsic.py       # Intrinsic calibration script
    ├── calibrate_extrinsic.py       # Extrinsic calibration script
    ├── verify_calibration.py        # Verification script
    ├── intrinsic_cam*.json          # Intrinsic calibration data
    ├── homography_cam*.json         # Homography matrices
    └── markers/                     # Generated ARUCO marker images
"""

# Lazy imports to avoid errors until classes are implemented
# Classes will be imported when accessed via:
#   from src.calibration import CoordinateMapper
#   from src.calibration.coordinate_mapper import CoordinateMapper

__all__ = [
    'CoordinateMapper',
    'IntrinsicCalibrator',
    'ExtrinsicCalibrator',
    'ArucoDetector',
]


def __getattr__(name):
    """Lazy import of calibration classes."""
    if name == 'CoordinateMapper':
        from .coordinate_mapper import CoordinateMapper
        return CoordinateMapper
    elif name == 'IntrinsicCalibrator':
        from .intrinsic_calibrator import IntrinsicCalibrator
        return IntrinsicCalibrator
    elif name == 'ExtrinsicCalibrator':
        from .extrinsic_calibrator import ExtrinsicCalibrator
        return ExtrinsicCalibrator
    elif name == 'ArucoDetector':
        from .aruco_detector import ArucoDetector
        return ArucoDetector
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
