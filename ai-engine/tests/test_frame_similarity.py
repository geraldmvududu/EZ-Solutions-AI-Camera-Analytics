"""Real tests for the aHash-based frame comparison in app/core/frame_similarity.py —
requested by the user to catch a looping test video showing the same footage
repeatedly, which the existing time-based cooldowns (OBJECT_EVENT_COOLDOWN_SECONDS/
TRIPWIRE_VIOLATION_COOLDOWN_SECONDS) can't: they throttle by elapsed time, not by
whether the picture actually changed."""

import numpy as np

from app.core.frame_similarity import average_hash, frames_are_duplicates, hamming_distance


def _checkerboard_frame() -> np.ndarray:
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[:60, :80] = 255
    frame[60:, 80:] = 255
    return frame


def _inverted_checkerboard_frame() -> np.ndarray:
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[:60, 80:] = 255
    frame[60:, :80] = 255
    return frame


def test_identical_frames_produce_the_same_hash():
    frame = _checkerboard_frame()
    assert average_hash(frame) == average_hash(frame.copy())


def test_identical_frames_are_flagged_as_duplicates():
    frame = _checkerboard_frame()
    h1 = average_hash(frame)
    h2 = average_hash(frame.copy())
    assert hamming_distance(h1, h2) == 0
    assert frames_are_duplicates(h1, h2)


def test_a_frame_with_light_compression_style_noise_is_still_a_duplicate():
    """A looping video file's own decode/re-encode introduces small per-pixel noise —
    this must not be mistaken for a genuinely new scene."""
    base = _checkerboard_frame()
    rng = np.random.default_rng(42)
    noisy = base.astype(np.int16) + rng.integers(-8, 9, size=base.shape)
    noisy = np.clip(noisy, 0, 255).astype(np.uint8)

    h1 = average_hash(base)
    h2 = average_hash(noisy)
    assert frames_are_duplicates(h1, h2)


def test_genuinely_different_scenes_are_not_duplicates():
    h1 = average_hash(_checkerboard_frame())
    h2 = average_hash(_inverted_checkerboard_frame())
    assert not frames_are_duplicates(h1, h2)


def test_hamming_distance_is_symmetric():
    a, b = average_hash(_checkerboard_frame()), average_hash(_inverted_checkerboard_frame())
    assert hamming_distance(a, b) == hamming_distance(b, a)
