"""Real bug found live on the deployed VM: one camera produced 535 TRIPWIRE_VIOLATION
events in ~2 hours, all attached to the SAME recording (535 "videos" reported for what
was really one continuous scene). A tracked object jittering right at the tripwire line
got reassigned a fresh track_id every ~10-25s — the same CentroidTracker churn
test_object_event_cooldown.py already covers for plain detections — and
_check_tripwires had NO debounce of its own at all: every crossing by every fresh
track_id fired its own event, unlike LoiteringTracker's "once per continuous stay" gate.

Seeds the tracker's history directly via Track objects rather than driving the full
capture loop, since only _check_tripwires' cooldown gate is under test here — the
tracker's own churn behavior is covered by test_tracker.py."""

import numpy as np
import pytest

from app import worker as worker_module
from app.core import snapshotter as snapshotter_module
from app.core.tracker import Track
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

TRIPWIRE = {"id": "wire-1", "camera_id": "cam-1", "line": [[0.0, 0.5], [1.0, 0.5]], "is_enabled": True}


@pytest.fixture(autouse=True)
def tmp_snapshot_path(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshotter_module.settings, "snapshot_path", str(tmp_path))


def _worker(tripwires=None) -> CameraWorker:
    return CameraWorker(dict(CAMERA), zones=[], tripwires=tripwires if tripwires is not None else [dict(TRIPWIRE)])


def _frame() -> np.ndarray:
    return np.zeros((10, 10, 3), dtype=np.uint8)


def _detection(y: float) -> Detection:
    return Detection(object_type="PERSON", confidence=0.9, x=0.4, y=y, width=0.1, height=0.05)


def _give_track_a_crossing(worker: CameraWorker, track_id: int) -> tuple[float, float]:
    """Seeds the tracker with a track whose last two history points straddle the
    tripwire's line (y=0.5) — a real crossing — and returns the centroid
    _check_tripwires needs."""
    track = Track(track_id, _detection(0.3))  # starts above the line
    track.update(_detection(0.7))  # ends below it: a genuine crossing
    worker._tracker._tracks[track_id] = track
    return track.centroid


def _mock_backend(monkeypatch, events):
    monkeypatch.setattr(worker_module.backend_client, "create_event", lambda payload: events.append(payload) or None)
    monkeypatch.setattr(worker_module.backend_client, "create_snapshot", lambda payload: {"id": "snap-1"})


def test_second_new_track_crossing_the_same_tripwire_within_cooldown_is_suppressed(monkeypatch):
    events = []
    _mock_backend(monkeypatch, events)
    worker = _worker()

    centroid = _give_track_a_crossing(worker, 1)
    worker._check_tripwires(1, centroid, _frame(), "det-1")
    assert len(events) == 1

    # A completely different track_id crosses the SAME tripwire moments later — e.g.
    # the tracker lost and re-acquired the same physical object under a new id.
    centroid = _give_track_a_crossing(worker, 2)
    worker._check_tripwires(2, centroid, _frame(), "det-2")
    assert len(events) == 1, "a second crossing of the same tripwire within the cooldown window must not spam a second event"


def test_crossing_after_cooldown_expires_emits_again(monkeypatch):
    events = []
    _mock_backend(monkeypatch, events)
    worker = _worker()

    centroid = _give_track_a_crossing(worker, 1)
    worker._check_tripwires(1, centroid, _frame(), "det-1")
    assert len(events) == 1

    worker._last_tripwire_violation_sent["wire-1"] -= worker_module.TRIPWIRE_VIOLATION_COOLDOWN_SECONDS + 1

    centroid = _give_track_a_crossing(worker, 2)
    worker._check_tripwires(2, centroid, _frame(), "det-2")
    assert len(events) == 2, "a genuinely new crossing after the cooldown has elapsed must still be reported"


def test_cooldown_does_not_block_the_very_first_crossing(monkeypatch):
    events = []
    _mock_backend(monkeypatch, events)
    worker = _worker()

    centroid = _give_track_a_crossing(worker, 1)
    worker._check_tripwires(1, centroid, _frame(), "det-1")
    assert len(events) == 1


def test_different_tripwires_have_independent_cooldowns(monkeypatch):
    events = []
    _mock_backend(monkeypatch, events)
    worker = _worker(tripwires=[dict(TRIPWIRE), {**TRIPWIRE, "id": "wire-2"}])

    centroid = _give_track_a_crossing(worker, 1)
    worker._check_tripwires(1, centroid, _frame(), "det-1")

    assert len(events) == 2, "two distinct tripwires crossed by the same movement must each report their own event"
