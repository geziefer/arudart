"""
Property-based tests for HomographyCalculator.

# Feature: step-6-coordinate-mapping, Property 4: Calibration Serialization Round-Trip
# Feature: step-6-coordinate-mapping, Property 9: Reprojection Error Thresholds Met

Tests:
- Serialization round-trip: save to JSON then load produces equivalent matrices
- Reprojection error: computed homography meets error thresholds
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from src.calibration.homography_calculator import HomographyCalculator


# --- Strategies ---

def homography_matrices():
    """Generate valid (non-degenerate) 3x3 homography matrices."""
    return arrays(
        dtype=np.float64,
        shape=(3, 3),
        elements=st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False),
    ).filter(lambda H: abs(np.linalg.det(H)) > 1e-3)


def realistic_homography_matrices():
    """
    Generate realistic homography matrices similar to what manual calibration produces.
    
    A realistic homography maps ~800x600 pixel space to ~340x340mm board space.
    Scale factor ~0.4-0.6 mm/px, with small perspective terms.
    """
    return st.tuples(
        st.floats(min_value=0.2, max_value=1.0),   # scale_x
        st.floats(min_value=0.2, max_value=1.0),   # scale_y
        st.floats(min_value=-0.05, max_value=0.05), # shear
        st.floats(min_value=-300, max_value=300),    # tx
        st.floats(min_value=-300, max_value=300),    # ty
        st.floats(min_value=-1e-4, max_value=1e-4),  # perspective_x
        st.floats(min_value=-1e-4, max_value=1e-4),  # perspective_y
    ).map(lambda t: np.array([
        [t[0], t[2], t[3]],
        [t[2], t[1], t[4]],
        [t[5], t[6], 1.0],
    ]))


def point_pairs_from_homography(H, n_points=17):
    """Generate consistent point pairs from a known homography."""
    # Generate image points spread across 800x600
    rng = np.random.default_rng(42)
    image_pts = rng.uniform([100, 100], [700, 500], size=(n_points, 2)).astype(np.float32)
    
    # Compute board points using the homography
    ones = np.ones((n_points, 1), dtype=np.float32)
    image_h = np.hstack([image_pts, ones])
    board_h = (H @ image_h.T).T
    board_pts = board_h[:, :2] / board_h[:, 2:3]
    
    return [(tuple(ip), tuple(bp)) for ip, bp in zip(image_pts, board_pts)]


# --- Property 4: Calibration Serialization Round-Trip ---

class TestSerializationRoundTrip:
    """
    Property 4: Calibration Serialization Round-Trip
    
    For any valid homography matrix, saving to JSON then loading should
    produce numerically equivalent matrices within floating-point tolerance of 1e-6.
    """

    @given(H=homography_matrices())
    @settings(max_examples=100, deadline=None)
    def test_homography_save_load_roundtrip(self, H):
        """Save homography to JSON, load back, verify numerical equivalence."""
        # Feature: step-6-coordinate-mapping, Property 4: Calibration Serialization Round-Trip
        assume(not np.any(np.isnan(H)))
        assume(abs(np.linalg.det(H)) > 1e-3)
        
        calculator = HomographyCalculator({})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata = {
                'num_points': 17,
                'num_inliers': 15,
                'reprojection_error_mm': 2.5,
                'timestamp': '2026-03-15T10:00:00'
            }
            
            calculator.save(0, H, metadata, tmpdir)
            loaded = calculator.load(0, tmpdir)
            
            assert loaded is not None, "Failed to load saved homography"
            np.testing.assert_allclose(
                loaded, H, atol=1e-6,
                err_msg="Loaded homography differs from saved"
            )

    @given(H=realistic_homography_matrices())
    @settings(max_examples=100, deadline=None)
    def test_realistic_homography_roundtrip(self, H):
        """Round-trip with realistic calibration-like homographies."""
        # Feature: step-6-coordinate-mapping, Property 4: Calibration Serialization Round-Trip
        calculator = HomographyCalculator({})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata = {
                'num_points': 17,
                'num_inliers': 17,
                'reprojection_error_mm': 1.0,
                'timestamp': '2026-03-15T10:00:00'
            }
            
            calculator.save(0, H, metadata, tmpdir)
            loaded = calculator.load(0, tmpdir)
            
            assert loaded is not None
            np.testing.assert_allclose(loaded, H, atol=1e-6)

    def test_load_nonexistent_returns_none(self):
        """Loading from nonexistent file returns None."""
        calculator = HomographyCalculator({})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = calculator.load(0, tmpdir)
            assert result is None

    @given(camera_id=st.integers(min_value=0, max_value=2))
    @settings(max_examples=10, deadline=None)
    def test_save_load_any_camera_id(self, camera_id):
        """Serialization works for all valid camera IDs."""
        # Feature: step-6-coordinate-mapping, Property 4: Calibration Serialization Round-Trip
        H = np.array([
            [0.5, 0.01, -200],
            [0.01, 0.5, -150],
            [1e-5, 1e-5, 1.0]
        ])
        calculator = HomographyCalculator({})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata = {
                'num_points': 17,
                'num_inliers': 17,
                'reprojection_error_mm': 2.0,
                'timestamp': '2026-03-15T10:00:00'
            }
            
            calculator.save(camera_id, H, metadata, tmpdir)
            loaded = calculator.load(camera_id, tmpdir)
            
            assert loaded is not None
            np.testing.assert_allclose(loaded, H, atol=1e-6)


# --- Property 9: Reprojection Error Thresholds Met ---

class TestReprojectionError:
    """
    Property 9: Reprojection Error Thresholds Met
    
    For any valid homography calibration, average reprojection error
    should be < 5mm.
    """

    def test_perfect_points_zero_error(self):
        """Perfect point pairs should give near-zero reprojection error."""
        # Feature: step-6-coordinate-mapping, Property 9: Reprojection Error Thresholds Met
        H = np.array([
            [0.5, 0.0, -200.0],
            [0.0, 0.5, -150.0],
            [0.0, 0.0, 1.0]
        ])
        
        point_pairs = point_pairs_from_homography(H, n_points=17)
        calculator = HomographyCalculator({})
        result = calculator.compute(point_pairs)
        
        assert result is not None
        computed_H, metadata = result
        assert metadata['reprojection_error_mm'] < 1.0  # Near-zero for perfect points

    @given(noise_std=st.floats(min_value=0.1, max_value=2.0))
    @settings(max_examples=50, deadline=None)
    def test_noisy_points_within_threshold(self, noise_std):
        """Points with small noise should still produce error < 5mm."""
        # Feature: step-6-coordinate-mapping, Property 9: Reprojection Error Thresholds Met
        H = np.array([
            [0.5, 0.0, -200.0],
            [0.0, 0.5, -150.0],
            [0.0, 0.0, 1.0]
        ])
        
        rng = np.random.default_rng(42)
        point_pairs = point_pairs_from_homography(H, n_points=17)
        
        # Add small noise to image points (simulating click inaccuracy)
        noisy_pairs = []
        for (iu, iv), (bx, by) in point_pairs:
            nu = iu + rng.normal(0, noise_std)
            nv = iv + rng.normal(0, noise_std)
            noisy_pairs.append(((nu, nv), (bx, by)))
        
        calculator = HomographyCalculator({})
        result = calculator.compute(noisy_pairs)
        
        assert result is not None
        _, metadata = result
        # With noise_std up to 2px and scale 0.5mm/px, error should be < 5mm
        assert metadata['reprojection_error_mm'] < 5.0, (
            f"Reprojection error {metadata['reprojection_error_mm']:.2f}mm "
            f"exceeds 5mm threshold with noise_std={noise_std:.2f}px"
        )

    def test_insufficient_points_returns_none(self):
        """Fewer than 4 points should return None."""
        calculator = HomographyCalculator({})
        
        pairs = [((100, 100), (0, 0)), ((200, 200), (50, 50)), ((300, 100), (100, 0))]
        result = calculator.compute(pairs)
        assert result is None

    def test_verify_method_accuracy(self):
        """Verify method computes correct error for known transformation."""
        # Feature: step-6-coordinate-mapping, Property 9: Reprojection Error Thresholds Met
        H = np.array([
            [0.5, 0.0, -200.0],
            [0.0, 0.5, -150.0],
            [0.0, 0.0, 1.0]
        ])
        
        # Create perfect pairs
        point_pairs = [
            ((400, 300), (0, 0)),      # center
            ((600, 300), (100, 0)),     # right
            ((400, 500), (0, 100)),     # down
            ((200, 100), (-100, -100)), # upper-left
        ]
        
        calculator = HomographyCalculator({})
        error = calculator.verify(H, point_pairs)
        
        assert error < 0.01, f"Perfect pairs should have near-zero error, got {error}"
