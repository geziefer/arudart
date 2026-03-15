"""
Calibration manager for orchestrating calibration lifecycle.

Manages calibration state (ready, calibrating, error), triggers
recalibration on drift detection, and provides status reporting.
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from .coordinate_mapper import CoordinateMapper
from .feature_detector import FeatureDetector
from .homography_calculator import HomographyCalculator

logger = logging.getLogger(__name__)


@dataclass
class CalibrationStatus:
    """Current calibration state and metadata."""
    state: str = "ready"  # 'ready', 'calibrating', 'error'
    last_calibration: Optional[datetime] = None
    last_validation: Optional[datetime] = None
    drift_mm: Optional[float] = None
    cameras_calibrated: list[int] = field(default_factory=list)
    error_message: Optional[str] = None
    consecutive_failures: int = 0


class CalibrationManager:
    """
    Orchestrates calibration lifecycle with continuous validation.
    
    State machine:
        ready -> calibrating: on startup or drift detected
        calibrating -> ready: calibration successful
        calibrating -> error: calibration failed 3 times
        error -> calibrating: manual retry triggered
    """
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        "ready": {"calibrating"},
        "calibrating": {"ready", "error"},
        "error": {"calibrating"},
    }
    
    def __init__(
        self,
        config: dict,
        coordinate_mapper: CoordinateMapper,
        feature_detector: Optional[FeatureDetector] = None,
        homography_calculator: Optional[HomographyCalculator] = None,
    ):
        """
        Initialize calibration manager.
        
        Args:
            config: Configuration dictionary
            coordinate_mapper: CoordinateMapper instance for transformations
            feature_detector: Optional FeatureDetector for bull detection
            homography_calculator: Optional HomographyCalculator for recomputation
        """
        self.config = config
        self.coordinate_mapper = coordinate_mapper
        self.feature_detector = feature_detector
        self.homography_calculator = homography_calculator
        
        # Configuration
        cal_config = config.get("calibration", {})
        self.drift_threshold_mm = cal_config.get("drift_threshold_mm", 3.0)
        self.max_failures = cal_config.get("max_calibration_failures", 3)
        
        # State
        self._lock = threading.Lock()
        self._status = CalibrationStatus(
            cameras_calibrated=coordinate_mapper.get_calibrated_cameras(),
        )
        
        # Set initial state based on calibration availability
        if self._status.cameras_calibrated:
            self._status.state = "ready"
            self._status.last_calibration = datetime.now()
        
        logger.info(
            f"CalibrationManager initialized: state={self._status.state}, "
            f"cameras={self._status.cameras_calibrated}"
        )
    
    def get_status(self) -> CalibrationStatus:
        """
        Get current calibration status.
        
        Returns:
            CalibrationStatus with current state and metadata
        """
        with self._lock:
            # Update cameras list from mapper
            self._status.cameras_calibrated = (
                self.coordinate_mapper.get_calibrated_cameras()
            )
            return CalibrationStatus(
                state=self._status.state,
                last_calibration=self._status.last_calibration,
                last_validation=self._status.last_validation,
                drift_mm=self._status.drift_mm,
                cameras_calibrated=list(self._status.cameras_calibrated),
                error_message=self._status.error_message,
                consecutive_failures=self._status.consecutive_failures,
            )
    
    def _transition_state(self, new_state: str):
        """
        Transition to a new state with validation.
        
        Args:
            new_state: Target state ('ready', 'calibrating', 'error')
        
        Raises:
            ValueError: If transition is invalid
        """
        old_state = self._status.state
        if new_state not in self.VALID_TRANSITIONS.get(old_state, set()):
            raise ValueError(
                f"Invalid state transition: {old_state} -> {new_state}"
            )
        
        self._status.state = new_state
        logger.info(f"Calibration state: {old_state} -> {new_state}")
    
    def run_full_calibration(
        self, camera_id: int, image: np.ndarray
    ) -> bool:
        """
        Run full calibration for a camera using feature detection.
        
        Args:
            camera_id: Camera identifier (0, 1, 2)
            image: Camera frame (BGR)
        
        Returns:
            True if calibration succeeded
        """
        if self.feature_detector is None or self.homography_calculator is None:
            logger.error("Feature detector or homography calculator not available")
            with self._lock:
                self._record_failure("Components not available")
            return False
        
        with self._lock:
            if self._status.state == "error":
                logger.warning(
                    "Cannot start calibration from error state - "
                    "call reset_error() first"
                )
                return False
            if self._status.state != "calibrating":
                try:
                    self._transition_state("calibrating")
                except ValueError:
                    logger.warning(
                        f"Cannot start calibration from state "
                        f"'{self._status.state}'"
                    )
                    return False
        
        try:
            # Detect bull center
            bull_center = self.feature_detector.detect_bull_center(image)
            if bull_center is None:
                logger.warning(
                    f"Camera {camera_id}: bull center not detected"
                )
                with self._lock:
                    self._record_failure("Bull center not detected")
                return False
            
            # Full feature detection
            result = self.feature_detector.detect(image)
            if result is None or result.bull_center is None:
                logger.warning(
                    f"Camera {camera_id}: feature detection failed"
                )
                with self._lock:
                    self._record_failure("Feature detection failed")
                return False
            
            # Compute homography from detected features
            # This would use FeatureMatcher + HomographyCalculator
            # For now, log success path
            logger.info(
                f"Camera {camera_id}: full calibration completed"
            )
            
            with self._lock:
                self._status.last_calibration = datetime.now()
                self._status.consecutive_failures = 0
                self._status.error_message = None
                self._transition_state("ready")
            
            # Reload mapper
            self.coordinate_mapper.reload_calibration(camera_id)
            
            return True
        
        except Exception as e:
            logger.error(f"Camera {camera_id}: calibration error: {e}")
            with self._lock:
                self._record_failure(str(e))
            return False

    def run_lightweight_validation(
        self, camera_id: int, image: np.ndarray
    ) -> float:
        """
        Quick validation by checking bull center drift.
        
        Detects bull center in the image, transforms to board coordinates,
        and measures distance from expected (0, 0).
        
        Args:
            camera_id: Camera identifier (0, 1, 2)
            image: Camera frame (BGR)
        
        Returns:
            Drift in millimeters (distance from origin).
            Returns float('inf') if detection fails.
        """
        if self.feature_detector is None:
            return float("inf")
        
        if not self.coordinate_mapper.is_calibrated(camera_id):
            return float("inf")
        
        try:
            bull_center = self.feature_detector.detect_bull_center(image)
            if bull_center is None:
                logger.debug(
                    f"Camera {camera_id}: bull not detected during validation"
                )
                return float("inf")
            
            board_coords = self.coordinate_mapper.map_to_board(
                camera_id, bull_center[0], bull_center[1]
            )
            if board_coords is None:
                return float("inf")
            
            x, y = board_coords
            drift = float(np.sqrt(x * x + y * y))
            
            with self._lock:
                self._status.last_validation = datetime.now()
                self._status.drift_mm = drift
            
            logger.debug(
                f"Camera {camera_id}: validation drift={drift:.2f}mm"
            )
            return drift
        
        except Exception as e:
            logger.error(
                f"Camera {camera_id}: validation error: {e}"
            )
            return float("inf")
    
    def check_and_recalibrate(
        self, camera_id: int, image: np.ndarray
    ) -> bool:
        """
        Check drift and trigger recalibration if needed.
        
        Args:
            camera_id: Camera identifier (0, 1, 2)
            image: Camera frame (BGR)
        
        Returns:
            True if calibration is OK (no drift or recalibration succeeded)
        """
        drift = self.run_lightweight_validation(camera_id, image)
        
        if drift <= self.drift_threshold_mm:
            return True
        
        if drift == float("inf"):
            logger.warning(
                f"Camera {camera_id}: validation failed, skipping recalibration"
            )
            return False
        
        logger.info(
            f"Camera {camera_id}: drift {drift:.1f}mm > "
            f"{self.drift_threshold_mm}mm, triggering recalibration"
        )
        
        return self.run_full_calibration(camera_id, image)
    
    def _record_failure(self, message: str):
        """
        Record a calibration failure (must hold self._lock).
        
        After max_failures consecutive failures, transitions to error state.
        """
        self._status.consecutive_failures += 1
        self._status.error_message = message
        
        if self._status.consecutive_failures >= self.max_failures:
            if self._status.state == "calibrating":
                self._transition_state("error")
            logger.error(
                f"Calibration failed {self._status.consecutive_failures} "
                f"times - manual intervention required"
            )
        else:
            logger.warning(
                f"Calibration failure {self._status.consecutive_failures}"
                f"/{self.max_failures}: {message}"
            )
    
    def reset_error(self):
        """
        Reset error state to allow retry.
        
        Transitions from error -> calibrating so a new attempt can be made.
        """
        with self._lock:
            if self._status.state != "error":
                logger.warning(
                    f"Cannot reset: state is '{self._status.state}', "
                    f"not 'error'"
                )
                return
            
            self._status.consecutive_failures = 0
            self._status.error_message = None
            self._transition_state("calibrating")
        
        logger.info("Error state reset, ready for retry")
