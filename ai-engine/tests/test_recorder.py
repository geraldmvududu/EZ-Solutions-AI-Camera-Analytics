"""SegmentRecorder (Facial Recognition Phase 2): a Recording row is created the moment
a segment STARTS (not when it closes), so a real recording_id exists to attach to a
face-recognition/violation event that fires while the segment is still being written."""

import os
import subprocess

import numpy as np
import pytest

from app.core import recorder as recorder_module
from app.core.recorder import SegmentRecorder


def _frame() -> np.ndarray:
    return np.zeros((100, 100, 3), dtype=np.uint8)


@pytest.fixture
def tmp_recording_path(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder_module.settings, "recording_path", str(tmp_path))
    return tmp_path


def test_start_creates_recording_immediately_and_stores_id(tmp_recording_path, monkeypatch):
    calls = []
    monkeypatch.setattr(recorder_module.backend_client, "create_recording", lambda payload: calls.append(payload) or {"id": "rec-123"})

    rec = SegmentRecorder("cam-1")
    rec.start(_frame(), fps=15, trigger_type="MANUAL")

    assert rec.recording_id == "rec-123"
    assert len(calls) == 1
    assert calls[0]["camera_id"] == "cam-1"
    assert calls[0]["trigger_type"] == "MANUAL"
    assert "ended_at" not in calls[0]  # not knowable yet — that's the whole point

    rec.stop()


def test_stop_finalizes_the_same_recording_not_a_new_one(tmp_recording_path, monkeypatch):
    monkeypatch.setattr(recorder_module.backend_client, "create_recording", lambda payload: {"id": "rec-123"})
    finalize_calls = []
    monkeypatch.setattr(recorder_module.backend_client, "finalize_recording", lambda rid, payload: finalize_calls.append((rid, payload)))

    rec = SegmentRecorder("cam-1")
    rec.start(_frame(), fps=15, trigger_type="MANUAL")
    rec.write(_frame())
    rec.write(_frame())
    rec.stop()

    assert len(finalize_calls) == 1
    recording_id, payload = finalize_calls[0]
    assert recording_id == "rec-123"
    assert payload["duration_seconds"] == pytest.approx(2 / 15, rel=0.01)
    assert "file_size_bytes" in payload
    assert rec.recording_id is None  # reset after stop


def test_stop_does_not_finalize_if_create_recording_failed(tmp_recording_path, monkeypatch):
    """If the backend was unreachable at start time (create_recording returns None,
    same fail-open convention as every other backend_client call), there is no
    recording_id to finalize — must not crash or call finalize with None."""
    monkeypatch.setattr(recorder_module.backend_client, "create_recording", lambda payload: None)
    finalize_calls = []
    monkeypatch.setattr(recorder_module.backend_client, "finalize_recording", lambda rid, payload: finalize_calls.append((rid, payload)))

    rec = SegmentRecorder("cam-1")
    rec.start(_frame(), fps=15, trigger_type="MANUAL")
    assert rec.recording_id is None
    rec.write(_frame())
    rec.stop()

    assert finalize_calls == []


def test_start_survives_create_recording_raising(tmp_recording_path, monkeypatch):
    """A face-recognition/recording outage must never stop the camera's own capture
    loop (spec section 19) — an exception from create_recording (not just an HTTP
    error, which _safe_post already swallows) must not propagate out of start()."""
    def boom(payload):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(recorder_module.backend_client, "create_recording", boom)

    rec = SegmentRecorder("cam-1")
    rec.start(_frame(), fps=15, trigger_type="MANUAL")  # must not raise
    assert rec.recording_id is None
    assert rec.is_recording is True  # local recording still proceeds regardless

    rec.stop()


def test_transcode_replaces_the_file_on_success(tmp_recording_path, monkeypatch):
    """cv2.VideoWriter's mp4v output isn't browser-playable (see this module's
    docstring — confirmed directly against a real file in a real browser) — stop()
    must re-encode via ffmpeg and replace the original file with the H.264 result."""
    monkeypatch.setattr(recorder_module.backend_client, "create_recording", lambda payload: {"id": "rec-123"})
    monkeypatch.setattr(recorder_module.backend_client, "finalize_recording", lambda rid, payload: None)

    calls = []

    def fake_run(cmd, capture_output, timeout):
        calls.append(cmd)
        # Simulate ffmpeg producing the transcoded sibling file real ffmpeg would —
        # the output path is always the last argument in the command built by
        # _transcode_to_h264.
        transcoded_path = cmd[-1]
        with open(transcoded_path, "wb") as f:
            f.write(b"fake h264 bytes")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    rec = SegmentRecorder("cam-1")
    rec.start(_frame(), fps=15, trigger_type="MANUAL")
    original_path = rec._file_path
    rec.write(_frame())
    rec.stop()

    assert len(calls) == 1
    assert calls[0][0] == "ffmpeg"
    assert "libx264" in calls[0]
    with open(original_path, "rb") as f:
        assert f.read() == b"fake h264 bytes"  # original replaced with the transcoded content
    assert not os.path.exists(original_path + ".h264.mp4")  # temp file cleaned up


def test_transcode_keeps_original_file_when_ffmpeg_missing(tmp_recording_path, monkeypatch):
    monkeypatch.setattr(recorder_module.backend_client, "create_recording", lambda payload: {"id": "rec-123"})
    monkeypatch.setattr(recorder_module.backend_client, "finalize_recording", lambda rid, payload: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("no ffmpeg")))

    rec = SegmentRecorder("cam-1")
    rec.start(_frame(), fps=15, trigger_type="MANUAL")
    original_path = rec._file_path
    rec.write(_frame())
    rec.stop()

    assert os.path.exists(original_path)  # the real (mp4v) recording is preserved, not lost


def test_transcode_keeps_original_file_when_ffmpeg_exits_nonzero(tmp_recording_path, monkeypatch):
    monkeypatch.setattr(recorder_module.backend_client, "create_recording", lambda payload: {"id": "rec-123"})
    monkeypatch.setattr(recorder_module.backend_client, "finalize_recording", lambda rid, payload: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], returncode=1, stdout=b"", stderr=b"unsupported codec"))

    rec = SegmentRecorder("cam-1")
    rec.start(_frame(), fps=15, trigger_type="MANUAL")
    original_path = rec._file_path
    rec.write(_frame())
    rec.stop()

    # The real (mp4v) recording is preserved — ffmpeg reporting failure must not lose
    # it — and no leftover temp file from the failed attempt.
    assert os.path.exists(original_path)
    assert os.path.getsize(original_path) > 0
    assert not os.path.exists(original_path + ".h264.mp4")
