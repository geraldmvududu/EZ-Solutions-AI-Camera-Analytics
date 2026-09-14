"""Real user request: a finite/looping video file kept producing genuinely "new"
events every time it looped back to the start, since each crossing is more than
OBJECT_EVENT_COOLDOWN_SECONDS/TRIPWIRE_VIOLATION_COOLDOWN_SECONDS apart from the last
and looks like a distinct occurrence to those time-based cooldowns — there was no way
to tell the platform "this is the same footage replaying, stop analyzing it."

worker.py._run() now reports back to the backend (via the new
backend_client.mark_video_processed) the moment a VIDEO_FILE camera with
loop_video=False genuinely reaches end-of-file, so main.py's discovery loop stops
restarting it. Scoped tightly: a live source (RTSP/webcam/...) or a still-looping
VIDEO_FILE camera returning no frame is a transient glitch, never "done," and must
never be marked processed."""

import numpy as np
import pytest

from app import worker as worker_module
from app.sources.base import FrameSource
from app.worker import CameraWorker


class _ImmediateEOFSource(FrameSource):
    def read(self):
        return None

    def release(self) -> None:
        pass

    @property
    def fps_hint(self) -> float:
        return 15.0


def _worker(camera: dict) -> CameraWorker:
    return CameraWorker(dict(camera), zones=[], tripwires=[])


def _mock_source(monkeypatch):
    monkeypatch.setattr(worker_module, "build_source", lambda camera: _ImmediateEOFSource())


def _mock_mark_processed(monkeypatch):
    calls = []
    monkeypatch.setattr(worker_module.backend_client, "mark_video_processed", lambda camera_id: calls.append(camera_id))
    return calls


@pytest.fixture(autouse=True)
def no_streaming(monkeypatch):
    # _run()'s finally block touches app.streaming — keep these tests focused on the
    # EOF-handling logic, not the real MJPEG publisher.
    monkeypatch.setattr(worker_module.streaming, "clear_frame", lambda camera_id: None)


CAMERA_BASE = {
    "id": "cam-1",
    "camera_code": "CAM-1",
    "name": "Front Gate",
    "ai_enabled": False,
    "motion_detection_enabled": False,
    "recording_enabled": False,
    "face_recognition_enabled": False,
    "source_type": "VIDEO_FILE",
}


def test_non_looping_video_file_reaching_eof_is_marked_processed(monkeypatch):
    _mock_source(monkeypatch)
    calls = _mock_mark_processed(monkeypatch)
    worker = _worker({**CAMERA_BASE, "loop_video": False})

    worker._run()

    assert calls == ["cam-1"]


def test_looping_video_file_reaching_eof_is_not_marked_processed(monkeypatch):
    """loop_video defaults to True — the existing/default behavior (keep looping)
    must be completely unaffected by this feature."""
    _mock_source(monkeypatch)
    calls = _mock_mark_processed(monkeypatch)
    worker = _worker({**CAMERA_BASE, "loop_video": True})

    worker._run()

    assert calls == []


def test_a_live_source_returning_no_frame_is_never_marked_processed(monkeypatch):
    """A non-VIDEO_FILE source (RTSP/webcam/...) returning no frame is a transient
    glitch, not "finished footage" — must never be marked processed even if
    loop_video happens to be False on that row."""
    _mock_source(monkeypatch)
    calls = _mock_mark_processed(monkeypatch)
    worker = _worker({**CAMERA_BASE, "source_type": "RTSP", "loop_video": False})

    worker._run()

    assert calls == []
