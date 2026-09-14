"""Real bug/feature request from the user: testing against a looping demo video, the
same footage keeps replaying, and the existing cooldowns (OBJECT_EVENT_COOLDOWN_SECONDS/
TRIPWIRE_VIOLATION_COOLDOWN_SECONDS) only throttle by elapsed TIME — once a loop's
period exceeds the cooldown window, a "new" event fires for a frame that's visually
identical to one already saved, writing another near-duplicate JPEG to disk.
_save_and_report_snapshot now compares the actual pixels (app/core/frame_similarity.py)
against the last snapshot taken for this camera and reuses it instead of saving a new
one when the picture hasn't actually changed — mirrors test_object_event_cooldown.py's
convention: a real CameraWorker, cheap to construct (ai_enabled=False means no I/O in
__init__), with only backend_client mocked."""

import numpy as np
import pytest

from app import worker as worker_module
from app.core import snapshotter as snapshotter_module
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


def _mock_backend(monkeypatch):
    created = []

    def _create_snapshot(payload):
        snapshot_id = f"snap-{len(created) + 1}"
        created.append((snapshot_id, payload))
        return {"id": snapshot_id}

    monkeypatch.setattr(worker_module.backend_client, "create_snapshot", _create_snapshot)
    return created


def test_a_repeated_identical_frame_reuses_the_previous_snapshot_instead_of_saving_a_new_one(monkeypatch):
    created = _mock_backend(monkeypatch)
    worker = _worker()
    frame = _checkerboard_frame()

    first_id = worker._save_and_report_snapshot(frame, None)
    second_id = worker._save_and_report_snapshot(frame.copy(), None)

    assert first_id == second_id
    assert len(created) == 1, "a visually-identical frame must not write/report a second snapshot"


def test_a_genuinely_different_frame_still_gets_its_own_snapshot(monkeypatch):
    created = _mock_backend(monkeypatch)
    worker = _worker()

    first_id = worker._save_and_report_snapshot(_checkerboard_frame(), None)
    second_id = worker._save_and_report_snapshot(_inverted_checkerboard_frame(), None)

    assert first_id != second_id
    assert len(created) == 2


def test_the_very_first_snapshot_is_never_treated_as_a_duplicate(monkeypatch):
    created = _mock_backend(monkeypatch)
    worker = _worker()

    snapshot_id = worker._save_and_report_snapshot(_checkerboard_frame(), None)

    assert snapshot_id is not None
    assert len(created) == 1


def test_a_repeated_frame_after_a_genuinely_different_one_is_not_treated_as_a_duplicate(monkeypatch):
    """Dedup only compares against the immediately-previous snapshot (not a full
    history) — a real, disclosed scope limit, exercised here so it stays honest."""
    created = _mock_backend(monkeypatch)
    worker = _worker()

    worker._save_and_report_snapshot(_checkerboard_frame(), None)
    worker._save_and_report_snapshot(_inverted_checkerboard_frame(), None)
    third_id = worker._save_and_report_snapshot(_checkerboard_frame(), None)

    assert third_id is not None
    assert len(created) == 3
