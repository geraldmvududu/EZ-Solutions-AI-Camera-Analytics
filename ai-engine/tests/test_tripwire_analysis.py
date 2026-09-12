"""AI Video Intelligence Phase 1: gate-jumping heuristic and tailgating window logic
(app/core/tripwire_analysis.py). Both operate purely on data the platform already
produces (centroid history, crossing timestamps) — no new detector/model involved.
"""

from app.core.tripwire_analysis import TailgatingTracker, gate_jump_confidence


def _walk_through(steps: int = 8, y: float = 0.5) -> list[tuple[float, float]]:
    """A normal horizontal walk-through: steady x progression, near-constant y (small
    camera-angle noise) — must NOT look like a climb."""
    return [(0.1 + i * 0.05, y + (0.005 if i % 2 else -0.005)) for i in range(steps)]


def _climb_over(steps: int = 8) -> list[tuple[float, float]]:
    """A sharp vertical excursion with little horizontal drift — a real climb/jump
    tends to look like this: up over the top, then down the other side. Each vertical
    step (0.2) clearly exceeds GATE_JUMP_MIN_VERTICAL_STEP (0.12) and the near-zero
    horizontal drift (0.01/step) clearly satisfies the velocity-ratio check."""
    path = []
    x = 0.5
    y = 0.8
    for i in range(steps):
        y -= 0.2 if i < steps // 2 else -0.2
        path.append((x + i * 0.01, y))
    return path


def test_normal_walk_through_does_not_look_like_a_climb():
    assert gate_jump_confidence(_walk_through()) is None


def test_sharp_vertical_excursion_is_flagged_as_a_climb():
    confidence = gate_jump_confidence(_climb_over())
    assert confidence is not None
    assert 0.5 <= confidence <= 0.99


def test_too_short_a_history_is_never_flagged():
    assert gate_jump_confidence([(0.5, 0.5)]) is None
    assert gate_jump_confidence([]) is None


def test_fast_diagonal_walk_is_not_flagged_when_proportional_to_pace():
    # Vertical motion exceeds the minimum step threshold on its own, but is still
    # proportional to a correspondingly large horizontal stride each step — must not
    # be confused with a climb (which is disproportionately vertical relative to the
    # track's own horizontal pace, not just vertical in absolute terms).
    path = [(0.1 + i * 0.2, 0.3 + i * 0.15) for i in range(8)]
    assert gate_jump_confidence(path) is None


def test_tailgating_flags_a_second_different_track_within_window(monkeypatch):
    tracker = TailgatingTracker()
    assert tracker.observe("tw1", track_id=1, now=100.0, window_seconds=5) is None  # first crossing, nothing to compare
    assert tracker.observe("tw1", track_id=2, now=102.0, window_seconds=5) == 1  # different track, within window


def test_tailgating_does_not_fire_outside_the_window():
    tracker = TailgatingTracker()
    tracker.observe("tw1", track_id=1, now=100.0, window_seconds=5)
    assert tracker.observe("tw1", track_id=2, now=110.0, window_seconds=5) is None


def test_tailgating_does_not_fire_for_the_same_track_recrossing():
    tracker = TailgatingTracker()
    tracker.observe("tw1", track_id=1, now=100.0, window_seconds=5)
    assert tracker.observe("tw1", track_id=1, now=101.0, window_seconds=5) is None


def test_tailgating_is_scoped_per_tripwire():
    tracker = TailgatingTracker()
    tracker.observe("tw1", track_id=1, now=100.0, window_seconds=5)
    # A crossing on a DIFFERENT tripwire must not be treated as tailgating the first.
    assert tracker.observe("tw2", track_id=2, now=101.0, window_seconds=5) is None
