"""Real bug found live on the deployed VM: CentroidTracker briefly losing and
re-acquiring the same physical object hands out a new track_id, and the old
_emit_object_event fired a brand-new event+snapshot for every one of those, flooding
disk with near-duplicate snapshots (~30k in under a day on one camera). This mirrors
test_theft_detection.py's convention: a real CameraWorker, cheap to construct
(ai_enabled=False means no I/O in __init__), with only backend_client mocked."""

import numpy as np
import pytest

from app import worker as worker_module
from app.core import snapshotter as snapshotter_module
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


@pytest.fixture(autouse=True)
def tmp_snapshot_path(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshotter_module.settings, "snapshot_path", str(tmp_path))


def _worker() -> CameraWorker:
    return CameraWorker(dict(CAMERA), zones=[], tripwires=[])


def _frame() -> np.ndarray:
    return np.zeros((10, 10, 3), dtype=np.uint8)


def _person() -> Detection:
    return Detection(object_type="PERSON", confidence=0.9, x=0.4, y=0.4, width=0.1, height=0.2)


def _mock_backend(monkeypatch, events):
    monkeypatch.setattr(worker_module.backend_client, "create_event", lambda payload: events.append(payload) or None)
    monkeypatch.setattr(worker_module.backend_client, "create_snapshot", lambda payload: {"id": "snap-1"})
    monkeypatch.setattr(worker_module.backend_client, "create_detection", lambda payload: {"id": "det-1"})


def test_second_new_track_within_cooldown_does_not_emit_a_second_event(monkeypatch):
    events = []
    _mock_backend(monkeypatch, events)
    worker = _worker()

    detection = _person()
    worker._process_tracked_detections(_frame(), {1: detection})
    assert len(events) == 1

    # A different track_id appears immediately after — e.g. the tracker briefly lost
    # and re-acquired the same physical person — well within the cooldown window.
    worker._process_tracked_detections(_frame(), {2: detection})
    assert len(events) == 1, "a second 'new' track within the cooldown window must not spam a second event"


def test_new_track_after_cooldown_expires_emits_again(monkeypatch):
    events = []
    _mock_backend(monkeypatch, events)
    worker = _worker()

    detection = _person()
    worker._process_tracked_detections(_frame(), {1: detection})
    assert len(events) == 1

    # Simulate real time passing past the cooldown window.
    worker._last_object_event_sent -= worker_module.OBJECT_EVENT_COOLDOWN_SECONDS + 1

    worker._process_tracked_detections(_frame(), {2: detection})
    assert len(events) == 2, "a genuinely new appearance after the cooldown has elapsed must still be reported"


def test_cooldown_does_not_block_the_very_first_event(monkeypatch):
    """Regression guard: _last_object_event_sent starts at 0.0, and time.time() minus
    0.0 is always >= the cooldown in practice — but assert it explicitly so a future
    refactor (e.g. switching to None-as-sentinel) can't silently swallow the first
    real detection a camera ever makes."""
    events = []
    _mock_backend(monkeypatch, events)
    worker = _worker()

    worker._process_tracked_detections(_frame(), {1: _person()})
    assert len(events) == 1
