"""AI Video Intelligence Phase 2 wiring test: CameraWorker._check_zones's ASSET_ZONE
branch. Constructs a real CameraWorker (cheap — __init__ does no I/O when ai_enabled
is False, matching how SegmentRecorder/build_source are only touched inside _run())
and calls the real zone-check method directly with synthetic detections, mocking only
backend_client — the same granularity Phase 1's tripwire_analysis tests used (pure
logic, no full capture-loop integration harness exists in this codebase).
"""

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

ASSET_ZONE = {
    "id": "zone-1",
    "camera_id": "cam-1",
    "zone_type": "ASSET_ZONE",
    "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    "is_enabled": True,
    "loitering_threshold_seconds": 10,
}


@pytest.fixture(autouse=True)
def tmp_snapshot_path(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshotter_module.settings, "snapshot_path", str(tmp_path))


def _worker(camera_overrides: dict | None = None) -> CameraWorker:
    camera = {**CAMERA, **(camera_overrides or {})}
    return CameraWorker(camera, zones=[ASSET_ZONE], tripwires=[])


def _frame() -> np.ndarray:
    return np.zeros((10, 10, 3), dtype=np.uint8)


def _backpack(x: float = 0.5, y: float = 0.5) -> Detection:
    return Detection(object_type="BACKPACK", confidence=0.8, x=x, y=y, width=0.05, height=0.05)


def test_backpack_removed_after_sufficient_dwell_fires_potential_theft(monkeypatch):
    events = []
    monkeypatch.setattr(worker_module.backend_client, "create_event", lambda payload: events.append(payload) or None)
    monkeypatch.setattr(worker_module.backend_client, "create_snapshot", lambda payload: {"id": "snap-1"})

    worker = _worker()
    detection = _backpack()
    centroid = (detection.x + detection.width / 2, detection.y + detection.height / 2)
    tracked = {1: detection}

    # Frame 1: inside the zone (polygon covers the whole frame).
    worker._check_zones(1, centroid, _frame(), "det-1", detection, tracked)
    assert events == []

    # Force the tracker's internal clock backward so the next "outside" observation
    # looks like it happened well after the configured 10s threshold.
    worker._asset_zone._entered_at[(1, "zone-1")] -= 15

    outside_centroid = (1.5, 1.5)  # outside the [0,1]x[0,1] polygon
    worker._check_zones(1, outside_centroid, _frame(), "det-1", detection, tracked)

    assert len(events) == 1
    assert events[0]["event_type"] == "POTENTIAL_THEFT_DETECTED"
    assert events[0]["event_metadata"]["object_type"] == "BACKPACK"
    assert events[0]["zone_id"] == "zone-1"


def test_backpack_removed_before_threshold_does_not_fire(monkeypatch):
    events = []
    monkeypatch.setattr(worker_module.backend_client, "create_event", lambda payload: events.append(payload) or None)
    monkeypatch.setattr(worker_module.backend_client, "create_snapshot", lambda payload: {"id": "snap-1"})

    worker = _worker()
    detection = _backpack()
    tracked = {1: detection}

    worker._check_zones(1, (0.5, 0.5), _frame(), "det-1", detection, tracked)
    worker._check_zones(1, (1.5, 1.5), _frame(), "det-1", detection, tracked)

    assert events == []


def test_theft_detection_disabled_tenant_wide_does_not_fire(monkeypatch):
    events = []
    monkeypatch.setattr(worker_module.backend_client, "create_event", lambda payload: events.append(payload) or None)
    monkeypatch.setattr(worker_module.backend_client, "create_snapshot", lambda payload: {"id": "snap-1"})

    worker = _worker({"theft_detection_enabled": False})
    detection = _backpack()
    tracked = {1: detection}

    # Disabled tenant-wide: the branch never even starts tracking dwell time, so
    # there's nothing to shift the clock on — both calls are no-ops for this feature.
    worker._check_zones(1, (0.5, 0.5), _frame(), "det-1", detection, tracked)
    worker._check_zones(1, (1.5, 1.5), _frame(), "det-1", detection, tracked)

    assert events == []
    assert worker._asset_zone._entered_at == {}


def test_person_object_types_never_trigger_asset_zone_check(monkeypatch):
    events = []
    monkeypatch.setattr(worker_module.backend_client, "create_event", lambda payload: events.append(payload) or None)
    monkeypatch.setattr(worker_module.backend_client, "create_snapshot", lambda payload: {"id": "snap-1"})

    worker = _worker()
    person = Detection(object_type="PERSON", confidence=0.9, x=0.5, y=0.5, width=0.1, height=0.2)
    tracked = {1: person}

    worker._check_zones(1, (0.5, 0.5), _frame(), "det-1", person, tracked)
    worker._check_zones(1, (1.5, 1.5), _frame(), "det-1", person, tracked)

    assert events == []


def test_nearby_person_identity_is_attached_when_recognized(monkeypatch):
    events = []
    monkeypatch.setattr(worker_module.backend_client, "create_event", lambda payload: events.append(payload) or None)
    monkeypatch.setattr(worker_module.backend_client, "create_snapshot", lambda payload: {"id": "snap-1"})

    worker = _worker({"face_recognition_enabled": True})

    class _FakeRecognizer:
        def identity_for(self, track_id):
            if track_id == 2:
                return {"person_id": "person-1", "person_name": "Jane Doe", "confidence_score": 0.95}
            return None

    worker._face_recognizer = _FakeRecognizer()

    backpack = _backpack(x=0.50, y=0.50)
    person_at_entry = Detection(object_type="PERSON", confidence=0.9, x=0.48, y=0.48, width=0.1, height=0.2)
    backpack_centroid = (backpack.x + backpack.width / 2, backpack.y + backpack.height / 2)

    worker._check_zones(1, backpack_centroid, _frame(), "det-1", backpack, {1: backpack, 2: person_at_entry})
    worker._asset_zone._entered_at[(1, "zone-1")] -= 15

    # The person is still near the item's new (outside-the-zone) position when it's
    # observed leaving — this is what makes the "who was nearby" attribution honest.
    exit_centroid = (1.5, 1.5)
    person_at_exit = Detection(object_type="PERSON", confidence=0.9, x=1.45, y=1.45, width=0.1, height=0.2)
    worker._check_zones(1, exit_centroid, _frame(), "det-1", backpack, {1: backpack, 2: person_at_exit})

    assert len(events) == 1
    assert events[0]["event_metadata"]["person_id"] == "person-1"
    assert events[0]["event_metadata"]["person_name"] == "Jane Doe"
