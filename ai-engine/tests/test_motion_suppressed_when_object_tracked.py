"""Real user request: a busy camera logged MOTION_DETECTED and PERSON_DETECTED within
a second or two of each other for the same passage — each event type's own cooldown
was individually correct, but together they still produced two events (often sharing
a near-identical snapshot) for one real occurrence, which read as duplication.
_on_motion_detected now skips creating an event whenever the AI detector recently
confirmed something tracked (self._last_detection_time, within a short grace window) —
that more specific PERSON_DETECTED/VEHICLE_DETECTED/AI_DETECTION event already covers
the same motion. A plain MOTION_DETECTED is still reported when nothing was recently
detected (no AI detector configured, or motion the detector doesn't recognize as any
tracked object).

Deliberately keyed on self._last_detection_time, NOT self._last_tracked: an earlier
version of this fix used self._last_tracked and looked correct in isolated unit tests,
but checking it against the real deployed camera showed motion still firing constantly
— self._last_tracked gets reset to `{}` on every AI-frame-skip cycle between actual
detection passes (see worker.py's `elif self._detector: self._last_tracked =
self._tracker.update([])`), so it reads as "empty" most of the time even while a real
track is still alive. self._last_detection_time only updates on a genuine detection
pass and isn't clobbered by skip frames, which is what these tests exercise directly."""

import time

import pytest

from app import worker as worker_module
from app.worker import CameraWorker

CAMERA = {
    "id": "cam-1",
    "camera_code": "CAM-1",
    "ai_enabled": False,
    "motion_detection_enabled": False,
    "recording_enabled": False,
    "face_recognition_enabled": False,
}


def _worker() -> CameraWorker:
    return CameraWorker(dict(CAMERA), zones=[], tripwires=[])


def _mock_backend(monkeypatch):
    events = []
    monkeypatch.setattr(worker_module.backend_client, "create_event", lambda payload: events.append(payload) or None)
    return events


def test_motion_is_suppressed_right_after_a_real_detection_pass(monkeypatch):
    events = _mock_backend(monkeypatch)
    worker = _worker()
    worker._last_detection_time = time.time()

    worker._on_motion_detected()

    assert events == []


def test_motion_still_fires_when_nothing_was_recently_detected(monkeypatch):
    events = _mock_backend(monkeypatch)
    worker = _worker()
    assert worker._last_detection_time == 0.0

    worker._on_motion_detected()

    assert len(events) == 1
    assert events[0]["event_type"] == "MOTION_DETECTED"


def test_motion_suppression_survives_a_skip_frame_resetting_last_tracked(monkeypatch):
    """The exact real bug this fix corrects: _last_tracked flickers to `{}` on every
    AI-frame-skip cycle even while a track is genuinely still alive — the suppression
    decision must not be fooled by that."""
    events = _mock_backend(monkeypatch)
    worker = _worker()
    worker._last_detection_time = time.time()
    worker._last_tracked = {}  # exactly what a skip-frame cycle leaves behind

    worker._on_motion_detected()

    assert events == []


def test_the_per_type_cooldown_still_applies_regardless_of_detection_state(monkeypatch):
    events = _mock_backend(monkeypatch)
    worker = _worker()

    worker._on_motion_detected()
    assert len(events) == 1

    worker._on_motion_detected()  # immediately again — still within the 30s cooldown
    assert len(events) == 1


def test_motion_resumes_once_the_detection_grace_window_expires(monkeypatch):
    events = _mock_backend(monkeypatch)
    worker = _worker()
    worker._last_detection_time = time.time()

    worker._on_motion_detected()
    assert events == []

    # The tracked object is long gone (well past the ~3s detection grace window), and
    # enough time passes for the (never-set, still 0.0) motion cooldown to allow a
    # fresh report.
    worker._last_detection_time -= 10
    worker._on_motion_detected()

    assert len(events) == 1
