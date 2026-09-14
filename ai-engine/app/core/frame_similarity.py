"""Real, transparent perceptual-hash frame comparison (average hash / aHash) — used to
detect when a newly-captured frame is visually the same scene as the last snapshot
already saved for a camera. Requested by the user directly: a looping test/demo video
file replays the exact same footage over and over, and the existing cooldowns
(worker.py's OBJECT_EVENT_COOLDOWN_SECONDS/TRIPWIRE_VIOLATION_COOLDOWN_SECONDS) only
throttle by elapsed TIME — once the loop period exceeds the cooldown window, a "new"
event fires again for content that is visually identical to what was already saved.

Deliberately NOT exact byte/pixel equality: JPEG re-encoding and a video file's own
decode both introduce tiny per-frame noise, so byte-for-byte comparison would almost
never match even for genuinely identical source footage. This is an approximate
visual-similarity heuristic (a coarse 8x8 grayscale average hash + Hamming distance),
not a trained/learned model — see CLAUDE.md's "do not hallucinate accuracy we don't
have" convention. It will not catch a genuinely different scene that merely looks
similar in a coarse sense (e.g. two different empty-driveway frames), nor is it meant
to — the goal is only to catch the same footage replaying, not general scene
classification.
"""

import cv2
import numpy as np

_HASH_SIZE = 8  # 8x8 grayscale -> a 64-bit hash, the standard aHash size


def average_hash(frame: np.ndarray) -> int:
    """Computes a 64-bit average hash: downscale to 8x8 grayscale, then set each bit
    based on whether that pixel is brighter than the image's own mean brightness.
    Two frames of the same scene (even after re-encoding/decoding noise) produce
    hashes that differ in only a handful of bits; two genuinely different scenes
    typically differ in many more."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    small = cv2.resize(gray, (_HASH_SIZE, _HASH_SIZE), interpolation=cv2.INTER_AREA)
    mean = small.mean()
    value = 0
    for bit in (small > mean).flatten():
        value = (value << 1) | int(bit)
    return value


def hamming_distance(hash_a: int, hash_b: int) -> int:
    return bin(hash_a ^ hash_b).count("1")


def frames_are_duplicates(hash_a: int, hash_b: int, threshold: int = 5) -> bool:
    """threshold=5 (out of 64 bits) is a conservative, commonly-used aHash cutoff for
    "visually the same image" — tolerant of minor compression/decode noise between two
    captures of the same real content, while still strict enough not to conflate two
    actually-different scenes."""
    return hamming_distance(hash_a, hash_b) <= threshold
