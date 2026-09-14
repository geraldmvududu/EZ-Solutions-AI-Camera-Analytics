"""Master Development Prompt Phase 1, "Camera & System Health": a real, disclosed
heuristic for lens obstruction/tampering — NOT a trained tamper-detection classifier (no
such model exists in this offline-build environment, same honest limitation already
applied to gate-jump/theft detection). Reuses the exact brightness/Laplacian-variance
primitives already proven in face_embedding.py's quality scoring
(ai-engine/app/core/face_embedding.py::_blur_score/_brightness_score), applied to the
WHOLE frame instead of a face crop.

Real, honest limitation: a sustained near-zero-texture or near-total-darkness frame is a
strong signal that something is covering/blocking the lens, but it is also exactly what a
camera legitimately pointed at a blank wall, or operating in true darkness with no IR
illumination, looks like. This heuristic cannot tell those apart — every
CAMERA_OBSTRUCTED event should be treated as needing human review (same
`requires_human_review` convention already used for AI Video Intelligence incidents), not
as confirmed proof of tampering.
"""

import cv2
import numpy as np

_REFERENCE_SIZE = 200
# Empirical: a genuinely blank/covered/lens-capped frame's Laplacian variance (computed
# on a normalized 200x200 grayscale frame, same reference size as face_embedding.py's
# blur score) lands near 0-10; an ordinary scene with any real detail scores in the
# hundreds to thousands.
LOW_VARIANCE_THRESHOLD = 15.0
# Near-total darkness — a hand/cloth fully over the lens, or the lens cap left on.
LOW_BRIGHTNESS_THRESHOLD = 0.03


def is_frame_obstructed(frame_bgr: np.ndarray) -> bool:
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY) if frame_bgr.ndim == 3 else frame_bgr
    resized = cv2.resize(gray, (_REFERENCE_SIZE, _REFERENCE_SIZE))
    variance = float(cv2.Laplacian(resized, cv2.CV_64F).var())
    brightness = float(resized.mean()) / 255.0
    return bool(variance < LOW_VARIANCE_THRESHOLD or brightness < LOW_BRIGHTNESS_THRESHOLD)


class CameraObstructionTracker:
    """Tracks how long a camera's frame has been CONTINUOUSLY flagged as obstructed and
    reports True only once that streak reaches sustained_seconds — a single dark/blurry
    frame (a light flicker, fast motion blur, a brief compression artifact) must not
    trigger a false alarm; only a genuinely sustained block should. cooldown_seconds then
    throttles repeat reports while the camera stays obstructed, the same
    sustain-then-cooldown idiom already used by worker.py's _on_motion_detected and
    object_tracking.py's AssetZoneTracker."""

    def __init__(self) -> None:
        self._obstructed_since: float | None = None
        # -inf, not 0.0: `now` in a fresh worker process starts at a real epoch timestamp
        # (or, in tests, small values near 0) — comparing against a 0.0 default made the
        # cooldown check falsely look "still active" the very first time this ever fires,
        # since `now - 0.0` can easily be smaller than cooldown_seconds. A tracker that has
        # never reported anything must never be treated as being in a cooldown.
        self._last_reported_at: float = float("-inf")

    def observe(self, frame_bgr: np.ndarray, sustained_seconds: float, cooldown_seconds: float, now: float) -> bool:
        if not is_frame_obstructed(frame_bgr):
            self._obstructed_since = None
            return False

        if self._obstructed_since is None:
            self._obstructed_since = now

        if now - self._obstructed_since < sustained_seconds:
            return False

        if now - self._last_reported_at < cooldown_seconds:
            return False

        self._last_reported_at = now
        return True
