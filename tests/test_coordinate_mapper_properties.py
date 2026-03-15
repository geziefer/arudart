"""
Property-based tests for CoordinateMapper.

# Feature: step-6-coordinate-mapping, Property 3: Homography Round-Trip Consistency
# Feature: step-6-coordinate-mapping, Property 5: Bounds Checking Returns None for Out-of-Bounds
# Feature: step-6-coordinate-mapping, Property 8: Thread Safety Under Concurrent Access

Tests:
- Round-trip: map_to_image then map_to_board returns original point (within 1mm)
- Bounds checking: points outside board (radius > 200mm) return None
- Thread safety: concurrent calls complete without corruption
"""

import json
import tempfile
import threading
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from src.calibration.coordinate_mapper import CoordinateMapper


# --- Shared mapper (module-level, read-only, safe for reuse) ---

_mapper_tmpdir = None
_mapper_instance = None


def _get_mapper():
    """Get or create a shared CoordinateMapper for property tests."""
    global _mapper_tmpdir, _mapper_instance
    if _mapper_instance is None:
        _mapper_tmpdir = tempfile.mkdtemp()
        tmpdir_path = Path(_mapper_tmpdir)
        _create_calibration_dir(tmpdir_path, scale=0.5)
        _mapper_instance = CoordinateMapper({}, str(tmpdir_path))
    return _mapper_instance


def _create_calibration_dir(tmpdir_path: Path, scale: float = 0.5):
    """
    Create calibration files with a known homography.
    
    The homography maps:
      image (400, 300) -> board (0, 0)  [center]
      scale: 1 pixel = `scale` mm
    """
    # Identity intrinsic (no distortion)
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
    
    # Homography: board = scale * (pixel - center)
    # x = scale * (u - 400), y = scale * (v - 300)
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


@pytest.fixture
def mapper_with_calibration():
    """Create a CoordinateMapper with known calibration data."""
    return _get_mapper()


# --- Strategies ---

def board_coordinates_within_bounds():
    """Generate board coordinates within the board (radius <= 170mm)."""
    return st.tuples(
        st.floats(min_value=-170, max_value=170),
        st.floats(min_value=-170, max_value=170),
    ).filter(lambda xy: np.sqrt(xy[0]**2 + xy[1]**2) <= 170)


def board_coordinates_out_of_bounds():
    """Generate board coordinates outside the board (radius > 200mm)."""
    # Use polar coordinates to guarantee radius > 200mm
    return st.tuples(
        st.floats(min_value=201, max_value=500),  # radius
        st.floats(min_value=0, max_value=2 * np.pi),  # angle
    ).map(lambda ra: (ra[0] * np.cos(ra[1]), ra[0] * np.sin(ra[1])))


# --- Property 3: Homography Round-Trip Consistency ---

class TestRoundTripConsistency:
    """
    Property 3: Homography Round-Trip Consistency
    
    For any board coordinate (x, y) within board bounds (radius <= 170mm),
    transforming to image coordinates then back to board coordinates should
    return approximately the same point within 1mm tolerance.
    """

    @given(coords=board_coordinates_within_bounds())
    @settings(max_examples=200, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_board_to_image_to_board_roundtrip(self, coords, mapper_with_calibration):
        """map_to_image then map_to_board should return original point."""
        # Feature: step-6-coordinate-mapping, Property 3: Homography Round-Trip Consistency
        x, y = coords
        mapper = mapper_with_calibration
        
        # Board -> Image
        image_result = mapper.map_to_image(0, x, y)
        assert image_result is not None, f"map_to_image returned None for ({x:.1f}, {y:.1f})"
        
        u, v = image_result
        
        # Image -> Board
        board_result = mapper.map_to_board(0, u, v)
        assert board_result is not None, (
            f"map_to_board returned None for pixel ({u:.1f}, {v:.1f}) "
            f"from board ({x:.1f}, {y:.1f})"
        )
        
        x2, y2 = board_result
        
        # Should be within 1mm of original
        distance = np.sqrt((x - x2)**2 + (y - y2)**2)
        assert distance < 1.0, (
            f"Round-trip error {distance:.3f}mm exceeds 1mm tolerance: "
            f"({x:.2f}, {y:.2f}) -> ({u:.1f}, {v:.1f}) -> ({x2:.2f}, {y2:.2f})"
        )

    def test_origin_roundtrip(self, mapper_with_calibration):
        """Bull center (0, 0) should round-trip perfectly."""
        # Feature: step-6-coordinate-mapping, Property 3: Homography Round-Trip Consistency
        mapper = mapper_with_calibration
        
        image_result = mapper.map_to_image(0, 0.0, 0.0)
        assert image_result is not None
        
        board_result = mapper.map_to_board(0, *image_result)
        assert board_result is not None
        
        x, y = board_result
        assert abs(x) < 0.01
        assert abs(y) < 0.01

    def test_known_points_roundtrip(self, mapper_with_calibration):
        """Known board positions should round-trip accurately."""
        # Feature: step-6-coordinate-mapping, Property 3: Homography Round-Trip Consistency
        mapper = mapper_with_calibration
        
        test_points = [
            (0, 0),       # bull
            (107, 0),     # triple ring right
            (0, 107),     # triple ring up
            (-170, 0),    # double ring left
            (0, -170),    # double ring down
            (50, 50),     # arbitrary inner
            (-80, 60),    # arbitrary inner
        ]
        
        for x, y in test_points:
            image_result = mapper.map_to_image(0, float(x), float(y))
            assert image_result is not None
            
            board_result = mapper.map_to_board(0, *image_result)
            assert board_result is not None
            
            x2, y2 = board_result
            distance = np.sqrt((x - x2)**2 + (y - y2)**2)
            assert distance < 0.1, (
                f"Round-trip error {distance:.4f}mm for point ({x}, {y})"
            )


# --- Property 5: Bounds Checking Returns None for Out-of-Bounds ---

class TestBoundsChecking:
    """
    Property 5: Bounds Checking Returns None for Out-of-Bounds
    
    For any pixel coordinate that maps to a board position with radius > 200mm,
    the map_to_board() function should return None.
    """

    @given(coords=board_coordinates_out_of_bounds())
    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_out_of_bounds_returns_none(self, coords, mapper_with_calibration):
        """Points mapping to radius > 200mm should return None."""
        # Feature: step-6-coordinate-mapping, Property 5: Bounds Checking Returns None
        x_board, y_board = coords
        mapper = mapper_with_calibration
        
        # Convert board coords to pixel coords using the known homography
        # H maps pixel -> board: board = 0.5 * (pixel - center)
        # So pixel = board / 0.5 + center = 2 * board + center
        u = 2 * x_board + 400
        v = 2 * y_board + 300
        
        result = mapper.map_to_board(0, u, v)
        assert result is None, (
            f"Expected None for out-of-bounds point "
            f"(radius={np.sqrt(x_board**2 + y_board**2):.1f}mm), "
            f"got {result}"
        )

    def test_far_pixel_returns_none(self, mapper_with_calibration):
        """Pixel far from board center should return None."""
        # Feature: step-6-coordinate-mapping, Property 5: Bounds Checking Returns None
        mapper = mapper_with_calibration
        
        # Pixel (1200, 300) -> board (400, 0) -> radius 400mm > 200mm
        result = mapper.map_to_board(0, 1200.0, 300.0)
        assert result is None

    def test_boundary_pixel_returns_value(self, mapper_with_calibration):
        """Pixel mapping to exactly 170mm radius should return a value."""
        mapper = mapper_with_calibration
        
        # board (170, 0) -> pixel = 2*170 + 400 = 740
        result = mapper.map_to_board(0, 740.0, 300.0)
        assert result is not None
        x, y = result
        radius = np.sqrt(x**2 + y**2)
        assert radius < 200  # Within bounds

    @given(coords=board_coordinates_within_bounds())
    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_in_bounds_returns_value(self, coords, mapper_with_calibration):
        """Points within board bounds should return valid coordinates."""
        # Feature: step-6-coordinate-mapping, Property 5: Bounds Checking Returns None
        x_board, y_board = coords
        mapper = mapper_with_calibration
        
        # Convert to pixel
        u = 2 * x_board + 400
        v = 2 * y_board + 300
        
        result = mapper.map_to_board(0, u, v)
        assert result is not None, (
            f"Expected valid result for in-bounds point "
            f"(radius={np.sqrt(x_board**2 + y_board**2):.1f}mm)"
        )


# --- Property 8: Thread Safety Under Concurrent Access ---

class TestThreadSafety:
    """
    Property 8: Thread Safety Under Concurrent Access
    
    For any concurrent calls to map_to_board() from multiple threads,
    all calls should complete without data corruption or race conditions,
    and each call should return consistent results.
    """

    def test_concurrent_map_to_board(self, mapper_with_calibration):
        """Concurrent map_to_board calls should all return consistent results."""
        # Feature: step-6-coordinate-mapping, Property 8: Thread Safety
        mapper = mapper_with_calibration
        
        results = []
        errors = []
        n_threads = 8
        n_iterations = 200
        
        def worker(thread_id):
            try:
                for _ in range(n_iterations):
                    result = mapper.map_to_board(0, 400.0, 300.0)
                    if result is not None:
                        results.append((thread_id, result))
                    else:
                        errors.append((thread_id, "Unexpected None"))
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Thread errors: {errors[:5]}"
        assert len(results) == n_threads * n_iterations
        
        # All results should be consistent (same input -> same output)
        for thread_id, (x, y) in results:
            assert abs(x) < 1.0, f"Thread {thread_id}: x={x} not near 0"
            assert abs(y) < 1.0, f"Thread {thread_id}: y={y} not near 0"

    def test_concurrent_mixed_operations(self, mapper_with_calibration):
        """Mixed map_to_board and map_to_image calls should not corrupt state."""
        # Feature: step-6-coordinate-mapping, Property 8: Thread Safety
        mapper = mapper_with_calibration
        
        errors = []
        n_threads = 6
        n_iterations = 100
        
        def board_worker(thread_id):
            try:
                for _ in range(n_iterations):
                    result = mapper.map_to_board(0, 400.0, 300.0)
                    assert result is not None
                    x, y = result
                    assert abs(x) < 1.0 and abs(y) < 1.0
            except Exception as e:
                errors.append((thread_id, "board", str(e)))
        
        def image_worker(thread_id):
            try:
                for _ in range(n_iterations):
                    result = mapper.map_to_image(0, 0.0, 0.0)
                    assert result is not None
                    u, v = result
                    assert abs(u - 400) < 1.0 and abs(v - 300) < 1.0
            except Exception as e:
                errors.append((thread_id, "image", str(e)))
        
        def status_worker(thread_id):
            try:
                for _ in range(n_iterations):
                    assert mapper.is_calibrated(0)
                    cams = mapper.get_calibrated_cameras()
                    assert 0 in cams
            except Exception as e:
                errors.append((thread_id, "status", str(e)))
        
        threads = []
        for i in range(n_threads // 3):
            threads.append(threading.Thread(target=board_worker, args=(i,)))
            threads.append(threading.Thread(target=image_worker, args=(i + 100,)))
            threads.append(threading.Thread(target=status_worker, args=(i + 200,)))
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Thread errors: {errors[:5]}"

    @given(
        x=st.floats(min_value=-150, max_value=150),
        y=st.floats(min_value=-150, max_value=150),
    )
    @settings(max_examples=50, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_concurrent_varied_inputs(self, x, y, mapper_with_calibration):
        """Concurrent calls with varied inputs should all succeed."""
        # Feature: step-6-coordinate-mapping, Property 8: Thread Safety
        assume(np.sqrt(x**2 + y**2) <= 150)
        mapper = mapper_with_calibration
        
        # Convert to pixel
        u = 2 * x + 400
        v = 2 * y + 300
        
        errors = []
        results = []
        
        def worker():
            try:
                result = mapper.map_to_board(0, u, v)
                results.append(result)
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        # All threads should get the same result
        for r in results:
            assert r is not None
            rx, ry = r
            assert abs(rx - results[0][0]) < 0.001
            assert abs(ry - results[0][1]) < 0.001
