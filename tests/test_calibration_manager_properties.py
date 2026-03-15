"""
Property-based tests for CalibrationManager.

# Feature: step-6-coordinate-mapping, Property 6: Drift Detection Triggers Recalibration
# Feature: step-6-coordinate-mapping, Property 7: State Machine Transitions Are Valid

Tests:
- Drift detection: drift > 3mm triggers recalibration (state -> calibrating)
- State machine: only valid transitions occur, 3 failures -> error state
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from src.calibration.calibration_manager import CalibrationManager, CalibrationStatus
from src.calibration.coordinate_mapper import CoordinateMapper


# --- Helpers ---

def _create_calibration_dir(tmpdir_path: Path, scale: float = 0.5):
    """Create calibration files with a known homography (same as coordinate mapper tests)."""
    intrinsic_data = {
        'camera_id': 0,
        'camera_matrix': [
            [800.0, 0.0, 400.0],
            [0.0, 800.0, 300.0],
            [0.0, 0.0, 1.0]
        ],
        'distortion_coeffs': [0.0, 0.0, 0.0, 0.0, 0.0],
        'reprojection_error': 0.0,
        'image_size': [800, 600],
        'calibration_date': '2026-03-15T10:00:00'
    }
    with open(tmpdir_path / 'intrinsic_cam0.json', 'w') as f:
        json.dump(intrinsic_data, f)

    H = np.array([
        [scale, 0.0, -scale * 400],
        [0.0, scale, -scale * 300],
        [0.0, 0.0, 1.0]
    ])
    homography_data = {
        'camera_id': 0,
        'homography': H.tolist(),
        'num_points': 17,
        'num_inliers': 17,
        'reprojection_error_mm': 0.0,
        'timestamp': '2026-03-15T10:00:00'
    }
    with open(tmpdir_path / 'homography_cam0.json', 'w') as f:
        json.dump(homography_data, f)


def _make_manager(tmpdir_path: Path, drift_threshold: float = 3.0, max_failures: int = 3):
    """Create a CalibrationManager with mocked feature detector."""
    mapper = CoordinateMapper({}, str(tmpdir_path))
    detector = MagicMock()
    calculator = MagicMock()

    config = {
        "calibration": {
            "drift_threshold_mm": drift_threshold,
            "max_calibration_failures": max_failures,
        }
    }
    manager = CalibrationManager(
        config=config,
        coordinate_mapper=mapper,
        feature_detector=detector,
        homography_calculator=calculator,
    )
    return manager, detector


@pytest.fixture
def calibration_dir():
    """Create a temp dir with calibration files."""
    tmpdir = tempfile.mkdtemp()
    tmpdir_path = Path(tmpdir)
    _create_calibration_dir(tmpdir_path)
    return tmpdir_path


@pytest.fixture
def manager_and_detector(calibration_dir):
    """Create a CalibrationManager with calibration data and mocked detector."""
    return _make_manager(calibration_dir)


# --- Property 6: Drift Detection Triggers Recalibration ---

class TestDriftDetection:
    """
    Property 6: Drift Detection Triggers Recalibration

    For any lightweight validation result where drift exceeds 3mm,
    the CalibrationManager should transition to 'calibrating' state
    and trigger full recalibration.
    """

    @given(drift_mm=st.floats(min_value=3.01, max_value=100.0))
    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_drift_above_threshold_triggers_recalibration(
        self, drift_mm, calibration_dir
    ):
        """Drift > 3mm should trigger recalibration attempt."""
        # Feature: step-6-coordinate-mapping, Property 6: Drift Detection Triggers Recalibration
        manager, detector = _make_manager(calibration_dir)

        # Mock bull detection at a pixel that maps to (drift_mm, 0) on the board
        # With our homography: board = 0.5 * (pixel - center)
        # So pixel_u = drift_mm / 0.5 + 400 = 2 * drift_mm + 400
        pixel_u = 2 * drift_mm + 400
        pixel_v = 300.0  # center y
        detector.detect_bull_center.return_value = (pixel_u, pixel_v)

        # Mock full calibration to fail (so we can observe state change)
        detector.detect.return_value = None

        dummy_image = np.zeros((600, 800, 3), dtype=np.uint8)
        result = manager.check_and_recalibrate(0, dummy_image)

        # Should have attempted recalibration (returned False since detect failed)
        assert result is False
        # State should reflect the calibration attempt
        status = manager.get_status()
        assert status.state in ("calibrating", "error")
        assert status.drift_mm is not None
        assert status.drift_mm > 3.0

    @given(drift_mm=st.floats(min_value=0.0, max_value=2.99))
    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_drift_below_threshold_no_recalibration(
        self, drift_mm, calibration_dir
    ):
        """Drift <= 3mm should NOT trigger recalibration."""
        # Feature: step-6-coordinate-mapping, Property 6: Drift Detection Triggers Recalibration
        manager, detector = _make_manager(calibration_dir)

        # Mock bull detection at pixel mapping to (drift_mm, 0)
        pixel_u = 2 * drift_mm + 400
        pixel_v = 300.0
        detector.detect_bull_center.return_value = (pixel_u, pixel_v)

        dummy_image = np.zeros((600, 800, 3), dtype=np.uint8)
        result = manager.check_and_recalibrate(0, dummy_image)

        assert result is True
        status = manager.get_status()
        assert status.state == "ready"

    def test_exact_threshold_no_recalibration(self, manager_and_detector):
        """Drift exactly at threshold (3.0mm) should NOT trigger recalibration."""
        # Feature: step-6-coordinate-mapping, Property 6: Drift Detection Triggers Recalibration
        manager, detector = manager_and_detector

        # 3.0mm drift -> pixel = 2*3 + 400 = 406
        detector.detect_bull_center.return_value = (406.0, 300.0)

        dummy_image = np.zeros((600, 800, 3), dtype=np.uint8)
        result = manager.check_and_recalibrate(0, dummy_image)

        assert result is True
        assert manager.get_status().state == "ready"

    def test_bull_not_detected_returns_false(self, manager_and_detector):
        """If bull center can't be detected, validation returns inf and no recalibration."""
        # Feature: step-6-coordinate-mapping, Property 6: Drift Detection Triggers Recalibration
        manager, detector = manager_and_detector
        detector.detect_bull_center.return_value = None

        dummy_image = np.zeros((600, 800, 3), dtype=np.uint8)
        drift = manager.run_lightweight_validation(0, dummy_image)

        assert drift == float("inf")


# --- Property 7: State Machine Transitions Are Valid ---

class TestStateMachineTransitions:
    """
    Property 7: State Machine Transitions Are Valid

    For any sequence of calibration events, the CalibrationManager state
    should only transition through valid paths:
        ready -> calibrating -> ready
        ready -> calibrating -> error
        error -> calibrating -> ready
    After 3 consecutive calibration failures, state should be 'error'.
    """

    def test_initial_state_ready_when_calibrated(self, manager_and_detector):
        """Manager starts in 'ready' state when calibration files exist."""
        # Feature: step-6-coordinate-mapping, Property 7: State Machine Transitions Are Valid
        manager, _ = manager_and_detector
        assert manager.get_status().state == "ready"

    def test_initial_state_ready_when_uncalibrated(self):
        """Manager starts in 'ready' state even without calibration (no cameras)."""
        # Feature: step-6-coordinate-mapping, Property 7: State Machine Transitions Are Valid
        tmpdir = tempfile.mkdtemp()
        mapper = CoordinateMapper({}, tmpdir)
        manager = CalibrationManager(
            config={}, coordinate_mapper=mapper
        )
        # No cameras calibrated, but state is still ready (just no cameras)
        assert manager.get_status().state == "ready"

    def test_ready_to_calibrating_on_full_calibration(self, manager_and_detector):
        """Full calibration transitions ready -> calibrating."""
        # Feature: step-6-coordinate-mapping, Property 7: State Machine Transitions Are Valid
        manager, detector = manager_and_detector
        detector.detect_bull_center.return_value = (400.0, 300.0)
        detector.detect.return_value = MagicMock(bull_center=(400.0, 300.0))

        dummy_image = np.zeros((600, 800, 3), dtype=np.uint8)
        result = manager.run_full_calibration(0, dummy_image)

        # Calibration succeeds -> state back to ready
        assert result is True
        assert manager.get_status().state == "ready"

    def test_three_failures_enter_error_state(self, calibration_dir):
        """3 consecutive failures should transition to error state."""
        # Feature: step-6-coordinate-mapping, Property 7: State Machine Transitions Are Valid
        manager, detector = _make_manager(calibration_dir, max_failures=3)
        detector.detect_bull_center.return_value = None
        detector.detect.return_value = None

        dummy_image = np.zeros((600, 800, 3), dtype=np.uint8)

        for i in range(3):
            manager.run_full_calibration(0, dummy_image)

        status = manager.get_status()
        assert status.state == "error"
        assert status.consecutive_failures >= 3

    @given(n_failures=st.integers(min_value=1, max_value=2))
    @settings(max_examples=10, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_fewer_than_max_failures_stays_calibrating(
        self, n_failures, calibration_dir
    ):
        """Fewer than max_failures should NOT enter error state."""
        # Feature: step-6-coordinate-mapping, Property 7: State Machine Transitions Are Valid
        manager, detector = _make_manager(calibration_dir, max_failures=3)
        detector.detect_bull_center.return_value = None
        detector.detect.return_value = None

        dummy_image = np.zeros((600, 800, 3), dtype=np.uint8)

        for _ in range(n_failures):
            manager.run_full_calibration(0, dummy_image)

        status = manager.get_status()
        assert status.state == "calibrating"
        assert status.consecutive_failures == n_failures

    @given(max_failures=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_error_after_exactly_max_failures(
        self, max_failures, calibration_dir
    ):
        """Error state should occur after exactly max_failures consecutive failures."""
        # Feature: step-6-coordinate-mapping, Property 7: State Machine Transitions Are Valid
        manager, detector = _make_manager(
            calibration_dir, max_failures=max_failures
        )
        detector.detect_bull_center.return_value = None
        detector.detect.return_value = None

        dummy_image = np.zeros((600, 800, 3), dtype=np.uint8)

        for _ in range(max_failures):
            manager.run_full_calibration(0, dummy_image)

        assert manager.get_status().state == "error"

    def test_error_to_calibrating_via_reset(self, calibration_dir):
        """reset_error() should transition error -> calibrating."""
        # Feature: step-6-coordinate-mapping, Property 7: State Machine Transitions Are Valid
        manager, detector = _make_manager(calibration_dir, max_failures=1)
        detector.detect_bull_center.return_value = None
        detector.detect.return_value = None

        dummy_image = np.zeros((600, 800, 3), dtype=np.uint8)
        manager.run_full_calibration(0, dummy_image)
        assert manager.get_status().state == "error"

        manager.reset_error()
        assert manager.get_status().state == "calibrating"

    def test_success_after_reset_returns_to_ready(self, calibration_dir):
        """After reset, successful calibration returns to ready."""
        # Feature: step-6-coordinate-mapping, Property 7: State Machine Transitions Are Valid
        manager, detector = _make_manager(calibration_dir, max_failures=1)
        detector.detect_bull_center.return_value = None
        detector.detect.return_value = None

        dummy_image = np.zeros((600, 800, 3), dtype=np.uint8)

        # Fail once -> error
        manager.run_full_calibration(0, dummy_image)
        assert manager.get_status().state == "error"

        # Reset -> calibrating
        manager.reset_error()
        assert manager.get_status().state == "calibrating"

        # Now succeed
        detector.detect_bull_center.return_value = (400.0, 300.0)
        detector.detect.return_value = MagicMock(bull_center=(400.0, 300.0))
        result = manager.run_full_calibration(0, dummy_image)

        assert result is True
        assert manager.get_status().state == "ready"
        assert manager.get_status().consecutive_failures == 0

    def test_success_resets_failure_counter(self, manager_and_detector):
        """Successful calibration resets consecutive failure counter."""
        # Feature: step-6-coordinate-mapping, Property 7: State Machine Transitions Are Valid
        manager, detector = manager_and_detector
        detector.detect_bull_center.return_value = None
        detector.detect.return_value = None

        dummy_image = np.zeros((600, 800, 3), dtype=np.uint8)

        # Fail twice
        manager.run_full_calibration(0, dummy_image)
        manager.run_full_calibration(0, dummy_image)
        assert manager.get_status().consecutive_failures == 2

        # Succeed
        detector.detect_bull_center.return_value = (400.0, 300.0)
        detector.detect.return_value = MagicMock(bull_center=(400.0, 300.0))
        manager.run_full_calibration(0, dummy_image)

        assert manager.get_status().consecutive_failures == 0
        assert manager.get_status().state == "ready"

    def test_cannot_calibrate_from_error_without_reset(self, calibration_dir):
        """Cannot start calibration from error state without reset."""
        # Feature: step-6-coordinate-mapping, Property 7: State Machine Transitions Are Valid
        manager, detector = _make_manager(calibration_dir, max_failures=1)
        detector.detect_bull_center.return_value = None
        detector.detect.return_value = None

        dummy_image = np.zeros((600, 800, 3), dtype=np.uint8)

        # Fail -> error
        manager.run_full_calibration(0, dummy_image)
        assert manager.get_status().state == "error"

        # Try again without reset -> should fail
        detector.detect_bull_center.return_value = (400.0, 300.0)
        detector.detect.return_value = MagicMock(bull_center=(400.0, 300.0))
        result = manager.run_full_calibration(0, dummy_image)

        assert result is False
        assert manager.get_status().state == "error"
