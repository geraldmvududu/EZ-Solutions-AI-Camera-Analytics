"""Recording linkage (Facial Recognition Phase 2): a Recording row now exists from the
moment a segment STARTS (not just when it closes), specifically so a real recording_id
can be attached to a face-recognition/violation event that happens while the segment
is still being written. See app/schemas/recording.py::RecordingFinalize and
app/api/routes/recordings.py::play_recording."""

import os
import tempfile
import uuid

import cv2
import numpy as np

from app.services import face_embedding
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _create_recording(client, cam_id: str) -> dict:
    resp = client.post(
        "/api/recordings",
        json={"camera_id": cam_id, "file_path": "/tmp/fake.mp4", "started_at": "2026-01-01T12:00:00Z", "trigger_type": "MANUAL"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_recording_created_at_start_has_no_end_time(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    recording = _create_recording(client, cam["id"])
    assert recording["ended_at"] is None
    assert recording["duration_seconds"] == 0


def test_finalize_sets_end_time_and_duration(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    recording = _create_recording(client, cam["id"])

    resp = client.patch(
        f"/api/recordings/{recording['id']}/internal",
        json={"ended_at": "2026-01-01T12:05:00Z", "duration_seconds": 300.0, "file_size_bytes": 1024},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ended_at"] is not None
    assert body["duration_seconds"] == 300.0
    assert body["file_size_bytes"] == 1024


def test_finalize_requires_internal_token(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    recording = _create_recording(client, cam["id"])

    resp = client.patch(
        f"/api/recordings/{recording['id']}/internal",
        json={"ended_at": "2026-01-01T12:05:00Z", "duration_seconds": 300.0, "file_size_bytes": 1024},
        headers=auth_headers(token),
    )
    assert resp.status_code == 401


def test_play_endpoint_streams_the_real_file_inline(client, admin_user, tmp_path):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    real_file = tmp_path / "segment.mp4"
    real_file.write_bytes(b"not a real mp4 but a real file on disk")
    resp = client.post(
        "/api/recordings",
        json={"camera_id": cam["id"], "file_path": str(real_file), "started_at": "2026-01-01T12:00:00Z", "trigger_type": "MANUAL"},
        headers=INTERNAL_HEADERS,
    )
    recording_id = resp.json()["id"]

    play_resp = client.get(f"/api/recordings/{recording_id}/play", params={"token": token})
    assert play_resp.status_code == 200
    assert play_resp.headers["content-type"] == "video/mp4"
    # Inline, not a forced download — unlike /download, no attachment disposition.
    assert "attachment" not in play_resp.headers.get("content-disposition", "")


def test_play_endpoint_rejects_invalid_token(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    recording = _create_recording(client, cam["id"])

    resp = client.get(f"/api/recordings/{recording['id']}/play", params={"token": "garbage"})
    assert resp.status_code == 401


def test_face_recognition_recording_id_propagates_to_event_and_alert(client, db_session, admin_user, tenant, monkeypatch):
    face = face_embedding.DetectedFace(40, 30, 100, 100)
    monkeypatch.setattr(face_embedding, "detect_faces", lambda frame: [face])

    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    recording = _create_recording(client, cam["id"])

    rng = np.random.default_rng(1)
    frame = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    enrolled = client.post(
        "/api/faces/enroll",
        data={"first_name": "Jane", "last_name": "Doe", "category": "EMPLOYEE"},
        files={"photo": ("face.jpg", buf.tobytes(), "image/jpeg")},
        headers=auth_headers(token),
    ).json()
    decoded = face_embedding.decode_image_bytes(buf.tobytes())
    embedding = face_embedding.compute_embedding(decoded, face).tolist()

    client.post(
        "/api/rules",
        json={"name": "Recognized", "conditions": {"event_type": "FACE_RECOGNIZED"}, "action_severity": "HIGH", "action_alert_type": "FACE_MATCH"},
        headers=auth_headers(token),
    )

    resp = client.post(
        "/api/faces/recognize",
        json={
            "camera_id": cam["id"], "tracking_id": 1, "embedding": embedding,
            "model_version": "lbph-v1", "quality_score": 0.9, "recording_id": recording["id"],
            "occurred_at": "2026-01-01T12:00:30Z",
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    event_id = resp.json()["event_id"]

    event = client.get(f"/api/events/{event_id}", headers=auth_headers(token)).json()
    assert event["recording_id"] == recording["id"]

    face_events = client.get("/api/face-events", headers=auth_headers(token)).json()
    assert face_events[0]["recording_id"] == recording["id"]

    alerts = client.get("/api/alerts", headers=auth_headers(token)).json()
    assert alerts[0]["recording_id"] == recording["id"]
