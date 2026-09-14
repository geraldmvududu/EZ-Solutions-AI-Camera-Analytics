"""Master Development Prompt Phase 1, "Crowd/Occupancy Counting": worker.py posts a
real +1/-1 occupancy delta for any tripwire with occupancy_counting_enabled, on every
genuine ENTERING/EXITING crossing crossed_line() detects — deliberately independent of
that tripwire's own `direction` filter (which only gates VIOLATION-style reporting) and
of TRIPWIRE_VIOLATION_COOLDOWN_SECONDS (a real queue of people must all be counted, not
throttled like violation events are). See test_tripwire_violation_cooldown.py for the
identical track-seeding technique this file reuses."""

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


@pytest.fixture(autouse=True)
def tmp_snapshot_path(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshotter_module.settings, "snapshot_path", str(tmp_path))


def _worker(tripwire_overrides=None) -> CameraWorker:
    tripwire = {"id": "wire-1", "camera_id": "cam-1", "line": [[0.0, 0.5], [1.0, 0.5]], "is_enabled": True}
    tripwire.update(tripwire_overrides or {})
    return CameraWorker(dict(CAMERA), zones=[], tripwires=[tripwire])


def _frame() -> np.ndarray:
    return np.zeros((10, 10, 3), dtype=np.uint8)


def _detection(y: float) -> Detection:
    return Detection(object_type="PERSON", confidence=0.9, x=0.4, y=y, width=0.1, height=0.05)


def _cross(worker: CameraWorker, track_id: int, entering: bool) -> tuple[float, float]:
    """ENTERING per crossed_line's convention is a move from the positive side to the
    negative side of the line (see zones.py::crossed_line): for this horizontal
    line at y=0.5, _side_of_line == y - 0.5, so y: 0.7 -> 0.3 (positive -> negative)
    is ENTERING; 0.3 -> 0.7 is EXITING."""
    start, end = (0.7, 0.3) if entering else (0.3, 0.7)
    track = Track(track_id, _detection(start))
    track.update(_detection(end))
    worker._tracker._tracks[track_id] = track
    return track.centroid


def _mock_backend(monkeypatch):
    deltas = []
    monkeypatch.setattr(worker_module.backend_client, "report_occupancy_delta", lambda camera_id, delta: deltas.append(delta))
    monkeypatch.setattr(worker_module.backend_client, "create_event", lambda payload: None)
    monkeypatch.setattr(worker_module.backend_client, "create_snapshot", lambda payload: {"id": "snap-1"})
    return deltas


def test_entering_crossing_reports_positive_one(monkeypatch):
    deltas = _mock_backend(monkeypatch)
    worker = _worker({"occupancy_counting_enabled": True})

    centroid = _cross(worker, 1, entering=True)
    worker._check_tripwires(1, centroid, _frame(), "det-1")

    assert deltas == [1]


def test_exiting_crossing_reports_negative_one(monkeypatch):
    deltas = _mock_backend(monkeypatch)
    worker = _worker({"occupancy_counting_enabled": True})

    centroid = _cross(worker, 1, entering=False)
    worker._check_tripwires(1, centroid, _frame(), "det-1")

    assert deltas == [-1]


def test_disabled_tripwire_never_reports_a_delta(monkeypatch):
    deltas = _mock_backend(monkeypatch)
    worker = _worker({"occupancy_counting_enabled": False})

    centroid = _cross(worker, 1, entering=True)
    worker._check_tripwires(1, centroid, _frame(), "det-1")

    assert deltas == []


def test_occupancy_counting_ignores_the_tripwires_own_direction_filter(monkeypatch):
    """A tripwire configured direction=ENTERING only (for violation reporting) must
    still count an EXITING crossing — counting cares about both directions regardless
    of that unrelated filter."""
    deltas = _mock_backend(monkeypatch)
    worker = _worker({"occupancy_counting_enabled": True, "direction": "ENTERING"})

    centroid = _cross(worker, 1, entering=False)
    worker._check_tripwires(1, centroid, _frame(), "det-1")

    assert deltas == [-1]


def test_occupancy_counting_ignores_the_tripwire_violation_cooldown(monkeypatch):
    """A real queue of several different people crossing within
    TRIPWIRE_VIOLATION_COOLDOWN_SECONDS of each other must ALL be counted — unlike
    violation reporting, counting has no debounce of its own."""
    deltas = _mock_backend(monkeypatch)
    worker = _worker({"occupancy_counting_enabled": True})

    for track_id in (1, 2, 3):
        centroid = _cross(worker, track_id, entering=True)
        worker._check_tripwires(track_id, centroid, _frame(), f"det-{track_id}")

    assert deltas == [1, 1, 1]
