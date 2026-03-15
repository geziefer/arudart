"""
Unit tests for CoordinateFusion class.

Tests specific scenarios for coordinate fusion including single camera,
multi-camera weighted average, outlier rejection, and edge cases.

**Validates: Requirements AC-7.1.2, AC-7.1.3, AC-7.1.4**
"""

import pytest

from src.fusion.coordinate_fusion import CoordinateFusion


DEFAULT_CONFIG = {"fusion": {"outlier_threshold_mm": 50.0, "min_confidence": 0.3}}


def make_detection(camera_id: int, x: float, y: float, confidence: float) -> dict:
    """Create a detection dict."""
    return {"camera_id": camera_id, "board": (x, y), "confidence": confidence}


class TestSingleCameraDetection:
    """Test single camera detection is used directly.

    **Validates: Requirements AC-7.1.2**
    """

    def test_single_detection_returned_directly(self) -> None:
        """Single camera detection should be returned as-is."""
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        detections = [make_detection(0, 10.0, 20.0, 0.85)]

        result = fusion.fuse_detections(detections)

        assert result is not None
        x, y, conf, cameras = result
        assert x == 10.0
        assert y == 20.0
        assert conf == 0.85
        assert cameras == [0]

    def test_single_detection_after_confidence_filter(self) -> None:
        """If only one detection passes confidence filter, use it directly."""
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        detections = [
            make_detection(0, 10.0, 20.0, 0.1),  # Below threshold
            make_detection(1, 30.0, 40.0, 0.9),  # Above threshold
        ]

        result = fusion.fuse_detections(detections)

        assert result is not None
        x, y, conf, cameras = result
        assert x == 30.0
        assert y == 40.0
        assert conf == 0.9
        assert cameras == [1]


class TestTwoCameraFusion:
    """Test two camera fusion with weighted average.

    **Validates: Requirements AC-7.1.3**
    """

    def test_equal_confidence_averages_positions(self) -> None:
        """Two detections with equal confidence should average positions."""
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        detections = [
            make_detection(0, 10.0, 20.0, 0.8),
            make_detection(1, 20.0, 40.0, 0.8),
        ]

        result = fusion.fuse_detections(detections)

        assert result is not None
        x, y, conf, cameras = result
        assert abs(x - 15.0) < 1e-6
        assert abs(y - 30.0) < 1e-6
        assert abs(conf - 0.8) < 1e-6
        assert sorted(cameras) == [0, 1]

    def test_unequal_confidence_weights_toward_higher(self) -> None:
        """Higher confidence detection should pull the fused position."""
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        detections = [
            make_detection(0, 0.0, 0.0, 0.9),
            make_detection(1, 10.0, 10.0, 0.3),
        ]

        result = fusion.fuse_detections(detections)

        assert result is not None
        x, y, conf, cameras = result
        # Weighted average: (0*0.9 + 10*0.3) / (0.9+0.3) = 3/1.2 = 2.5
        assert abs(x - 2.5) < 1e-6
        assert abs(y - 2.5) < 1e-6
        # Average confidence: (0.9 + 0.3) / 2 = 0.6
        assert abs(conf - 0.6) < 1e-6


class TestThreeCameraFusionWithOutliers:
    """Test three camera fusion with outlier rejection.

    **Validates: Requirements AC-7.1.3, AC-7.1.4**
    """

    def test_outlier_rejected_inliers_fused(self) -> None:
        """One outlier should be rejected, remaining two fused."""
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        detections = [
            make_detection(0, 100.0, 100.0, 0.8),
            make_detection(1, 105.0, 102.0, 0.9),
            make_detection(2, 200.0, 200.0, 0.7),  # Outlier: >50mm from median
        ]

        result = fusion.fuse_detections(detections)

        assert result is not None
        x, y, conf, cameras = result
        # Only cameras 0 and 1 should be used
        assert sorted(cameras) == [0, 1]
        # Weighted average of inliers: (100*0.8 + 105*0.9) / (0.8+0.9)
        expected_x = (100.0 * 0.8 + 105.0 * 0.9) / (0.8 + 0.9)
        expected_y = (100.0 * 0.8 + 102.0 * 0.9) / (0.8 + 0.9)
        assert abs(x - expected_x) < 1e-6
        assert abs(y - expected_y) < 1e-6

    def test_three_close_detections_all_kept(self) -> None:
        """Three close detections should all be kept."""
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        detections = [
            make_detection(0, 50.0, 50.0, 0.8),
            make_detection(1, 52.0, 48.0, 0.7),
            make_detection(2, 51.0, 51.0, 0.9),
        ]

        result = fusion.fuse_detections(detections)

        assert result is not None
        _, _, _, cameras = result
        assert sorted(cameras) == [0, 1, 2]


class TestAllOutliersRejected:
    """Test that all outliers being rejected returns None.

    **Validates: Requirements AC-7.1.4**
    """

    def test_all_detections_are_outliers_returns_none(self) -> None:
        """When all detections are far apart, all get rejected → None."""
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        # Three detections each >50mm from the median
        detections = [
            make_detection(0, 0.0, 0.0, 0.8),
            make_detection(1, 100.0, 0.0, 0.8),
            make_detection(2, 0.0, 100.0, 0.8),
        ]
        # Median is (0, 0). Camera 1 is 100mm away, camera 2 is 100mm away.
        # Camera 0 is at median (0mm). So camera 0 stays, 1 and 2 rejected.
        # Actually this won't return None. Let me use truly spread-out points.

        # All three are equidistant from median — need all >50mm
        detections = [
            make_detection(0, 0.0, 0.0, 0.8),
            make_detection(1, 200.0, 0.0, 0.8),
            make_detection(2, 400.0, 0.0, 0.8),
        ]
        # Median x=200, y=0. Cam0: 200mm away, Cam1: 0mm, Cam2: 200mm away
        # Only cam1 survives. That's not "all rejected" either.

        # To get all rejected: all must be >50mm from median
        detections = [
            make_detection(0, -100.0, 0.0, 0.8),
            make_detection(1, 0.0, 100.0, 0.8),
            make_detection(2, 100.0, 0.0, 0.8),
        ]
        # Median: x=0, y=0. Distances: 100, 100, 100 — all >50mm

        result = fusion.fuse_detections(detections)
        assert result is None


class TestLowConfidenceFiltering:
    """Test that low confidence detections are filtered out.

    **Validates: Requirements AC-7.1.2, AC-7.1.3**
    """

    def test_all_below_confidence_returns_none(self) -> None:
        """All detections below min_confidence should return None."""
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        detections = [
            make_detection(0, 10.0, 20.0, 0.1),
            make_detection(1, 30.0, 40.0, 0.2),
            make_detection(2, 50.0, 60.0, 0.29),
        ]

        result = fusion.fuse_detections(detections)
        assert result is None

    def test_mixed_confidence_filters_low(self) -> None:
        """Only detections above min_confidence should be used."""
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        detections = [
            make_detection(0, 10.0, 20.0, 0.1),   # Filtered
            make_detection(1, 30.0, 40.0, 0.8),   # Kept
            make_detection(2, 32.0, 42.0, 0.7),   # Kept
        ]

        result = fusion.fuse_detections(detections)

        assert result is not None
        _, _, _, cameras = result
        assert sorted(cameras) == [1, 2]


class TestEmptyDetectionList:
    """Test empty detection list.

    **Validates: Requirements AC-7.1.2**
    """

    def test_empty_list_returns_none(self) -> None:
        """Empty detection list should return None."""
        fusion = CoordinateFusion(DEFAULT_CONFIG)
        result = fusion.fuse_detections([])
        assert result is None
