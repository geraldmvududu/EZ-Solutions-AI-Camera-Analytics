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
    monkeypatch.setattr(recorder_module.backend_client, "get_pending_evidence_clips", lambda recording_id: [])

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
    monkeypatch.setattr(recorder_module.backend_client, "get_pending_evidence_clips", lambda recording_id: [])

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
    monkeypatch.setattr(recorder_module.backend_client, "get_pending_evidence_clips", lambda recording_id: [])

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
    monkeypatch.setattr(recorder_module.backend_client, "get_pending_evidence_clips", lambda recording_id: [])
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
    monkeypatch.setattr(recorder_module.backend_client, "get_pending_evidence_clips", lambda recording_id: [])
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


def _fake_run_creating_output_file(cmd, capture_output, timeout):
    """Shared fake ffmpeg for evidence-clip tests: works for both the transcode step
    and the trim step (both invoke ffmpeg with the real output path as the last arg)."""
    output_path = cmd[-1]
    with open(output_path, "wb") as f:
        f.write(b"fake clip bytes")
    return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")


def test_generates_evidence_clip_for_a_pending_incident(tmp_recording_path, monkeypatch):
    """AI Video Intelligence Phase 1 (section 21): stop() asks the backend for any
    Incident still waiting on an evidence clip from this now-finalized recording, trims
    a real ffmpeg clip around the event's real timestamp, and reports the clip path
    back."""
    monkeypatch.setattr(recorder_module.backend_client, "create_recording", lambda payload: {"id": "rec-123"})
    monkeypatch.setattr(recorder_module.backend_client, "finalize_recording", lambda rid, payload: None)
    monkeypatch.setattr(
        recorder_module.backend_client, "get_pending_evidence_clips",
        lambda recording_id: [{
            "incident_id": "incident-1",
            "event_occurred_at": "2026-01-01T12:00:10+00:00",
            "recording_started_at": "2026-01-01T12:00:00+00:00",
            "recording_file_path": "",
            "recording_duration_seconds": 30,
            "pre_event_seconds": 5,
            "post_event_seconds": 5,
        }],
    )
    trim_calls = []
    monkeypatch.setattr(recorder_module.backend_client, "set_incident_evidence_clip", lambda incident_id, payload: trim_calls.append((incident_id, payload)))

    run_calls = []

    def fake_run(cmd, capture_output, timeout):
        run_calls.append(cmd)
        return _fake_run_creating_output_file(cmd, capture_output, timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    rec = SegmentRecorder("cam-1")
    rec.start(_frame(), fps=15, trigger_type="MANUAL")
    original_path = rec._file_path
    rec.write(_frame())
    rec.stop()

    # Two ffmpeg invocations: the H.264 transcode, then the evidence-clip trim.
    assert len(run_calls) == 2
    trim_cmd = run_calls[1]
    assert trim_cmd[0] == "ffmpeg"
    ss_index = trim_cmd.index("-ss")
    assert float(trim_cmd[ss_index + 1]) == pytest.approx(5.0)  # event at 10s - 5s pre-roll
    t_index = trim_cmd.index("-t")
    assert float(trim_cmd[t_index + 1]) == pytest.approx(10.0)  # (10+5) - (10-5) = 10s

    assert len(trim_calls) == 1
    incident_id, payload = trim_calls[0]
    assert incident_id == "incident-1"
    assert payload["evidence_clip_path"] == f"{original_path}.incident-incident-1.mp4"


def test_evidence_clip_offsets_are_clamped_to_recording_bounds(tmp_recording_path, monkeypatch):
    """An event near the very start of the segment can't have a full pre-roll window
    (there is no live ring buffer — see this module's own pre-roll limitation) — the
    clip must start at 0, not a negative offset, and never extend past the recording's
    actual duration."""
    monkeypatch.setattr(recorder_module.backend_client, "create_recording", lambda payload: {"id": "rec-123"})
    monkeypatch.setattr(recorder_module.backend_client, "finalize_recording", lambda rid, payload: None)
    monkeypatch.setattr(
        recorder_module.backend_client, "get_pending_evidence_clips",
        lambda recording_id: [{
            "incident_id": "incident-2",
            "event_occurred_at": "2026-01-01T12:00:01+00:00",  # only 1s into the segment
            "recording_started_at": "2026-01-01T12:00:00+00:00",
            "recording_file_path": "",
            "recording_duration_seconds": 8,  # segment is short — post-roll would overrun it
            "pre_event_seconds": 30,
            "post_event_seconds": 30,
        }],
    )
    monkeypatch.setattr(recorder_module.backend_client, "set_incident_evidence_clip", lambda incident_id, payload: None)

    run_calls = []

    def fake_run(cmd, capture_output, timeout):
        run_calls.append(cmd)
        return _fake_run_creating_output_file(cmd, capture_output, timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    rec = SegmentRecorder("cam-1")
    rec.start(_frame(), fps=15, trigger_type="MANUAL")
    rec.write(_frame())
    rec.stop()

    trim_cmd = run_calls[1]
    ss_index = trim_cmd.index("-ss")
    assert float(trim_cmd[ss_index + 1]) == pytest.approx(0.0)  # clamped, not negative
    t_index = trim_cmd.index("-t")
    assert float(trim_cmd[t_index + 1]) == pytest.approx(8.0)  # clamped to the recording's own duration


def test_evidence_clip_trim_failure_does_not_crash_or_report_a_path(tmp_recording_path, monkeypatch):
    monkeypatch.setattr(recorder_module.backend_client, "create_recording", lambda payload: {"id": "rec-123"})
    monkeypatch.setattr(recorder_module.backend_client, "finalize_recording", lambda rid, payload: None)
    monkeypatch.setattr(
        recorder_module.backend_client, "get_pending_evidence_clips",
        lambda recording_id: [{
            "incident_id": "incident-3",
            "event_occurred_at": "2026-01-01T12:00:05+00:00",
            "recording_started_at": "2026-01-01T12:00:00+00:00",
            "recording_file_path": "",
            "recording_duration_seconds": 20,
            "pre_event_seconds": 5,
            "post_event_seconds": 5,
        }],
    )
    reported = []
    monkeypatch.setattr(recorder_module.backend_client, "set_incident_evidence_clip", lambda incident_id, payload: reported.append((incident_id, payload)))

    def fake_run(cmd, capture_output, timeout):
        if "-ss" in cmd:  # the trim step — fail it; let the transcode step succeed
            return subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"trim failed")
        return _fake_run_creating_output_file(cmd, capture_output, timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    rec = SegmentRecorder("cam-1")
    rec.start(_frame(), fps=15, trigger_type="MANUAL")
    original_path = rec._file_path
    rec.write(_frame())
    rec.stop()  # must not raise

    assert reported == []
    assert not os.path.exists(f"{original_path}.incident-incident-3.mp4")
