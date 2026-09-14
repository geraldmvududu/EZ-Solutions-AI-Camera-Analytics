"""Real user request: a busy camera logged MOTION_DETECTED and PERSON_DETECTED within
a second or two of each other for the same passage — each event type's own cooldown
was individually correct, but together they still produced two events (often sharing
a near-identical snapshot) for one real occurrence, which read as duplication.
_on_motion_detected now skips creating an event whenever the AI detector already has
something actively tracked (self._last_tracked) — that more specific PERSON_DETECTED/
VEHICLE_DETECTED/AI_DETECTION event already covers the same motion. A plain
MOTION_DETECTED is still reported when nothing is currently tracked (no AI detector
configured, or motion the detector doesn't recognize as any tracked object)."""

import pytest

from app import worker as worker_module
from app.detectors.base import Detection
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


def test_motion_is_suppressed_when_something_is_actively_tracked(monkeypatch):
    events = _mock_backend(monkeypatch)
    worker = _worker()
    worker._last_tracked = {1: Detection(object_type="PERSON", confidence=0.9, x=0.4, y=0.4, width=0.1, height=0.2)}

    worker._on_motion_detected()

    assert events == []


def test_motion_still_fires_when_nothing_is_tracked(monkeypatch):
    events = _mock_backend(monkeypatch)
    worker = _worker()
    assert worker._last_tracked == {}

    worker._on_motion_detected()

    assert len(events) == 1
    assert events[0]["event_type"] == "MOTION_DETECTED"


def test_the_per_type_cooldown_still_applies_regardless_of_tracking_state(monkeypatch):
    events = _mock_backend(monkeypatch)
    worker = _worker()

    worker._on_motion_detected()
    assert len(events) == 1

    worker._on_motion_detected()  # immediately again — still within the 30s cooldown
    assert len(events) == 1


def test_motion_resumes_once_tracking_ends_and_cooldown_allows_it(monkeypatch):
    events = _mock_backend(monkeypatch)
    worker = _worker()
    worker._last_tracked = {1: Detection(object_type="PERSON", confidence=0.9, x=0.4, y=0.4, width=0.1, height=0.2)}

    worker._on_motion_detected()
    assert events == []

    # The tracked object leaves frame, and enough time passes for the (never-set,
    # still 0.0) motion cooldown to allow a fresh report.
    worker._last_tracked = {}
    worker._on_motion_detected()

    assert len(events) == 1
