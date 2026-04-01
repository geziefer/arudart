"""Property-based tests for the Web API layer.

Uses Hypothesis to verify correctness properties across all valid inputs.

Properties tested:
- Property 3: dart_scored payload correctness
- Property 4: Sequential dart numbering
- Property 5: Round completion ordering and emission
- Property 6: round_complete payload correctness
"""

import re

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.api.round_tracker import RoundTracker, score_to_label
from src.fusion.dart_hit_event import DartHitEvent, Score


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

RING_TYPES = ["triple", "double", "single", "bull", "single_bull", "miss"]

@st.composite
def dart_score_strategy(draw):
    """Generate a valid Score with consistent ring/sector/total values."""
    ring = draw(st.sampled_from(RING_TYPES))

    if ring == "miss":
        return Score(base=0, multiplier=0, total=0, ring="miss", sector=None)
    elif ring == "bull":
        return Score(base=50, multiplier=2, total=50, ring="bull", sector=None)
    elif ring == "single_bull":
        return Score(base=25, multiplier=1, total=25, ring="single_bull", sector=None)
    else:
        sector = draw(st.integers(min_value=1, max_value=20))
        if ring == "triple":
            return Score(base=sector, multiplier=3, total=sector * 3, ring="triple", sector=sector)
        elif ring == "double":
            return Score(base=sector, multiplier=2, total=sector * 2, ring="double", sector=sector)
        else:  # single
            return Score(base=sector, multiplier=1, total=sector, ring="single", sector=sector)


@st.composite
def dart_hit_strategy(draw):
    """Generate a valid DartHitEvent with a random score."""
    score = draw(dart_score_strategy())
    return DartHitEvent(
        timestamp="2025-01-01T00:00:00Z",
        board_x=draw(st.floats(min_value=-200, max_value=200)),
        board_y=draw(st.floats(min_value=-200, max_value=200)),
        radius=50.0,
        angle_rad=0.0,
        angle_deg=0.0,
        score=score,
        fusion_confidence=0.9,
        cameras_used=[0],
        num_cameras=1,
        detections=[],
    )


LABEL_PATTERN = re.compile(r"^(T[1-9][0-9]?|D[1-9][0-9]?|S[1-9][0-9]?|SB|DB|Miss)$")


# ---------------------------------------------------------------------------
# Property 3: dart_scored payload correctness
# Feature: step-9-web-api, Property 3: dart_scored payload correctness
# ---------------------------------------------------------------------------

@given(dart_hit=dart_hit_strategy())
@settings(max_examples=100)
def test_property3_dart_scored_payload_correctness(dart_hit):
    """**Validates: Requirements 2.1, 2.2, 2.4**

    For any valid DartHitEvent, process_hit() returns a dart_scored dict with:
    - dart_number: int 1-3
    - label: string matching T{sector}|D{sector}|S{sector}|SB|DB|Miss
    - points: int equal to score.total
    """
    # Feature: step-9-web-api, Property 3: dart_scored payload correctness
    tracker = RoundTracker()
    result = tracker.process_hit(dart_hit)

    assert len(result) >= 1
    dart_scored = result[0]

    assert dart_scored["event"] == "dart_scored"
    assert isinstance(dart_scored["dart_number"], int)
    assert 1 <= dart_scored["dart_number"] <= 3
    assert isinstance(dart_scored["label"], str)
    assert LABEL_PATTERN.match(dart_scored["label"]), (
        f"Label '{dart_scored['label']}' does not match expected format"
    )
    assert isinstance(dart_scored["points"], int)
    assert dart_scored["points"] == dart_hit.score.total


# ---------------------------------------------------------------------------
# Property 4: Sequential dart numbering
# Feature: step-9-web-api, Property 4: Sequential dart numbering
# ---------------------------------------------------------------------------

@given(hits=st.lists(dart_hit_strategy(), min_size=1, max_size=3))
@settings(max_examples=100)
def test_property4_sequential_dart_numbering(hits):
    """**Validates: Requirements 2.5**

    For any sequence of DartHitEvents processed by a fresh RoundTracker,
    dart_number in successive dart_scored outputs is 1, 2, 3 in order.
    After reset(), numbering restarts from 1.
    """
    # Feature: step-9-web-api, Property 4: Sequential dart numbering
    tracker = RoundTracker()
    for expected_number, hit in enumerate(hits, start=1):
        result = tracker.process_hit(hit)
        dart_scored = result[0]
        assert dart_scored["dart_number"] == expected_number

    # After reset, numbering restarts
    tracker.reset()
    result = tracker.process_hit(hits[0])
    assert result[0]["dart_number"] == 1


# ---------------------------------------------------------------------------
# Property 5: Round completion ordering and emission
# Feature: step-9-web-api, Property 5: Round completion ordering and emission
# ---------------------------------------------------------------------------

@given(
    hit1=dart_hit_strategy(),
    hit2=dart_hit_strategy(),
    hit3=dart_hit_strategy(),
)
@settings(max_examples=100)
def test_property5_round_completion_ordering(hit1, hit2, hit3):
    """**Validates: Requirements 2.3, 3.1**

    For exactly 3 DartHitEvents:
    - First two calls return only [dart_scored]
    - Third call returns [dart_scored, round_complete] in that order
    """
    # Feature: step-9-web-api, Property 5: Round completion ordering and emission
    tracker = RoundTracker()

    r1 = tracker.process_hit(hit1)
    assert len(r1) == 1
    assert r1[0]["event"] == "dart_scored"

    r2 = tracker.process_hit(hit2)
    assert len(r2) == 1
    assert r2[0]["event"] == "dart_scored"

    r3 = tracker.process_hit(hit3)
    assert len(r3) == 2
    assert r3[0]["event"] == "dart_scored"
    assert r3[1]["event"] == "round_complete"


# ---------------------------------------------------------------------------
# Property 6: round_complete payload correctness
# Feature: step-9-web-api, Property 6: round_complete payload correctness
# ---------------------------------------------------------------------------

@given(
    hit1=dart_hit_strategy(),
    hit2=dart_hit_strategy(),
    hit3=dart_hit_strategy(),
)
@settings(max_examples=100)
def test_property6_round_complete_payload_correctness(hit1, hit2, hit3):
    """**Validates: Requirements 3.2, 3.3, 3.4**

    For any 3 DartHitEvents, round_complete contains:
    - throws: array with exactly 3 entries in input order
    - total: sum of the 3 individual points values
    """
    # Feature: step-9-web-api, Property 6: round_complete payload correctness
    tracker = RoundTracker()
    tracker.process_hit(hit1)
    tracker.process_hit(hit2)
    result = tracker.process_hit(hit3)

    round_complete = result[1]
    assert round_complete["event"] == "round_complete"

    throws = round_complete["throws"]
    assert len(throws) == 3

    # Verify order
    assert throws[0]["dart_number"] == 1
    assert throws[1]["dart_number"] == 2
    assert throws[2]["dart_number"] == 3

    # Verify each throw has required fields
    for throw in throws:
        assert "dart_number" in throw
        assert "label" in throw
        assert "points" in throw

    # Verify total equals sum of points
    expected_total = hit1.score.total + hit2.score.total + hit3.score.total
    assert round_complete["total"] == expected_total

    # Verify individual points match input
    assert throws[0]["points"] == hit1.score.total
    assert throws[1]["points"] == hit2.score.total
    assert throws[2]["points"] == hit3.score.total
