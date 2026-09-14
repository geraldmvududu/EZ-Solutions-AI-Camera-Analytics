import numpy as np

from app.core.camera_health import CameraObstructionTracker, is_frame_obstructed


def _uniform_frame(value: int, size: int = 240) -> np.ndarray:
    """A perfectly flat frame — zero Laplacian variance regardless of brightness. Stands
    in for a lens fully covered by a dark cloth (value near 0) or a bright object pressed
    against it (value near 255)."""
    return np.full((size, size, 3), value, dtype=np.uint8)


def _textured_frame(size: int = 240) -> np.ndarray:
    """A real, high-variance synthetic scene — plenty of edges, nothing "obstructed"."""
    rng = np.random.default_rng(42)
    return rng.integers(0, 256, (size, size, 3), dtype=np.uint8)


def test_uniform_dark_frame_is_obstructed():
    assert is_frame_obstructed(_uniform_frame(5)) is True


def test_uniform_mid_gray_frame_is_obstructed_by_low_variance():
    # Not dark, but a perfectly flat frame has zero texture either way — still a real
    # obstruction signal (e.g. something opaque pressed directly against the lens).
    assert is_frame_obstructed(_uniform_frame(128)) is True


def test_textured_frame_is_not_obstructed():
    assert is_frame_obstructed(_textured_frame()) is False


def test_tracker_does_not_fire_on_a_brief_dip():
    tracker = CameraObstructionTracker()
    dark = _uniform_frame(5)
    assert tracker.observe(dark, sustained_seconds=5.0, cooldown_seconds=300, now=0.0) is False
    assert tracker.observe(dark, sustained_seconds=5.0, cooldown_seconds=300, now=2.0) is False


def test_tracker_fires_once_the_obstruction_is_sustained():
    tracker = CameraObstructionTracker()
    dark = _uniform_frame(5)
    tracker.observe(dark, sustained_seconds=5.0, cooldown_seconds=300, now=0.0)
    assert tracker.observe(dark, sustained_seconds=5.0, cooldown_seconds=300, now=6.0) is True


def test_tracker_respects_cooldown_after_firing():
    tracker = CameraObstructionTracker()
    dark = _uniform_frame(5)
    tracker.observe(dark, sustained_seconds=5.0, cooldown_seconds=300, now=0.0)
    assert tracker.observe(dark, sustained_seconds=5.0, cooldown_seconds=300, now=6.0) is True
    # Still obstructed a moment later — must not re-fire until the cooldown elapses.
    assert tracker.observe(dark, sustained_seconds=5.0, cooldown_seconds=300, now=10.0) is False


def test_tracker_resets_streak_when_a_real_frame_returns():
    tracker = CameraObstructionTracker()
    dark = _uniform_frame(5)
    real = _textured_frame()
    tracker.observe(dark, sustained_seconds=5.0, cooldown_seconds=300, now=0.0)
    # A real frame in between must reset the streak — this is not "sustained" anymore.
    tracker.observe(real, sustained_seconds=5.0, cooldown_seconds=300, now=3.0)
    assert tracker.observe(dark, sustained_seconds=5.0, cooldown_seconds=300, now=6.0) is False
