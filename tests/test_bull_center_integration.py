"""
Integration test for bull center detection with realistic scenarios.

Tests the detect_bull_center() method with various image conditions
that might occur in real camera captures.
"""

import numpy as np
import cv2
import pytest

from src.calibration.feature_detector import FeatureDetector


@pytest.fixture
def config():
    """Provide test configuration."""
    return {
        'calibration': {
            'feature_detection': {
                'bull_min_radius_px': 10,
                'bull_max_radius_px': 30,
                'canny_threshold_low': 50,
                'canny_threshold_high': 150,
                'hough_line_threshold': 50,
                'min_wire_length_px': 50
            }
        }
    }


@pytest.fixture
def detector(config):
    """Create a FeatureDetector instance."""
    return FeatureDetector(config)


def test_bull_detection_with_noise(detector):
    """Test bull center detection with noisy image."""
    # Create synthetic dartboard
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    
    # Draw bull at center
    center = (400, 300)
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    cv2.circle(image, center, 10, (10, 10, 10), -1)
    
    # Add Gaussian noise
    noise = np.random.normal(0, 15, image.shape).astype(np.int16)
    noisy_image = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Detect bull center
    bull_center = detector.detect_bull_center(noisy_image)
    
    # Should still detect despite noise
    assert bull_center is not None, "Should detect bull even with noise"
    
    detected_x, detected_y = bull_center
    distance = np.sqrt((detected_x - center[0])**2 + (detected_y - center[1])**2)
    
    # Allow larger tolerance due to noise
    assert distance < 10, f"Detection should be within 10px with noise, got {distance:.1f}px"


def test_bull_detection_with_varying_brightness(detector):
    """Test bull center detection with different brightness levels."""
    for brightness in [100, 150, 200, 250]:
        # Create image with specific brightness
        image = np.ones((600, 800, 3), dtype=np.uint8) * brightness
        
        # Draw bull (darker than background)
        center = (400, 300)
        bull_color = max(10, brightness - 100)
        cv2.circle(image, center, 20, (bull_color, bull_color, bull_color), -1)
        cv2.circle(image, center, 10, (max(5, bull_color - 20), max(5, bull_color - 20), max(5, bull_color - 20)), -1)
        
        # Detect bull center
        bull_center = detector.detect_bull_center(image)
        
        # Should detect at various brightness levels
        assert bull_center is not None, f"Should detect bull at brightness {brightness}"
        
        detected_x, detected_y = bull_center
        distance = np.sqrt((detected_x - center[0])**2 + (detected_y - center[1])**2)
        
        assert distance < 5, f"Detection at brightness {brightness} should be accurate, got {distance:.1f}px"


def test_bull_detection_at_radius_boundaries(detector):
    """Test bull detection at minimum and maximum radius boundaries."""
    # Test near minimum radius (12px, slightly above 10px min)
    image_min = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    cv2.circle(image_min, center, 12, (30, 30, 30), -1)
    
    bull_center_min = detector.detect_bull_center(image_min)
    assert bull_center_min is not None, "Should detect bull near minimum radius"
    
    # Test near maximum radius (28px, slightly below 30px max)
    image_max = np.ones((600, 800, 3), dtype=np.uint8) * 200
    cv2.circle(image_max, center, 28, (30, 30, 30), -1)
    
    bull_center_max = detector.detect_bull_center(image_max)
    assert bull_center_max is not None, "Should detect bull near maximum radius"


def test_bull_detection_rejects_too_small_circle(detector):
    """Test that circles smaller than min_radius are rejected."""
    # Create image with circle smaller than minimum (5px < 10px min)
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    cv2.circle(image, center, 5, (30, 30, 30), -1)
    
    # Should not detect (too small)
    bull_center = detector.detect_bull_center(image)
    assert bull_center is None, "Should reject circles smaller than min_radius"


def test_bull_detection_rejects_too_large_circle(detector):
    """Test that circles larger than max_radius are rejected."""
    # Create image with circle larger than maximum (40px > 30px max)
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    cv2.circle(image, center, 40, (30, 30, 30), -1)
    
    # Should not detect (too large)
    bull_center = detector.detect_bull_center(image)
    assert bull_center is None, "Should reject circles larger than max_radius"


def test_bull_detection_with_partial_occlusion(detector):
    """Test bull detection with partial occlusion (e.g., dart in the way)."""
    # Create dartboard with bull
    image = np.ones((600, 800, 3), dtype=np.uint8) * 200
    center = (400, 300)
    cv2.circle(image, center, 20, (30, 30, 30), -1)
    cv2.circle(image, center, 10, (10, 10, 10), -1)
    
    # Add partial occlusion (simulating dart or shadow)
    cv2.rectangle(image, (390, 290), (410, 310), (100, 100, 100), -1)
    
    # Detect bull center
    bull_center = detector.detect_bull_center(image)
    
    # May or may not detect depending on occlusion severity
    # This test documents the behavior rather than enforcing it
    if bull_center is not None:
        detected_x, detected_y = bull_center
        distance = np.sqrt((detected_x - center[0])**2 + (detected_y - center[1])**2)
        # If detected, should still be reasonably accurate
        assert distance < 15, f"If detected with occlusion, should be within 15px, got {distance:.1f}px"
