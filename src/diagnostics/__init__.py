"""Diagnostics package for ARU-DART scoring pipeline.

Provides structured diagnostic records for dart detections,
including per-camera deviation analysis.
"""

from src.diagnostics.accuracy_test_runner import AccuracyTestRunner
from src.diagnostics.detection_record import CameraDiagnostic, DetectionRecord
from src.diagnostics.diagnostic_logger import DiagnosticLogger
from src.diagnostics.known_positions import KnownPosition
from src.diagnostics.test_report import TestReport, TestReportGenerator

__all__ = [
    "AccuracyTestRunner",
    "CameraDiagnostic",
    "DetectionRecord",
    "DiagnosticLogger",
    "KnownPosition",
    "TestReport",
    "TestReportGenerator",
]
