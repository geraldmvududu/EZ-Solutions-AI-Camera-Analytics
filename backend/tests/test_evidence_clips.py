"""AI Video Intelligence Phase 1 (section 21): the two internal endpoints ai-engine's
SegmentRecorder.stop() calls to trim a real evidence clip from a now-finalized
recording, plus the query-token-authenticated playback endpoint the frontend's
<video> tag uses. See app/services/violation_service.py (always-incident event types)
and app/core/recorder.py (the trim step itself, ai-engine side)."""

import os
import tempfile

from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _create_recording(client, cam_id: str) -> dict:
    resp = client.post(
        "/api/recordings",
        json={"camera_id": cam_id, "file_path": "/data/recordings/clip.mp4", "started_at": "2026-01-01T12:00:00Z", "trigger_type": "MANUAL"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_gate_jumping_incident(client, token, cam_id: str, recording_id: str) -> dict:
    # Deliberately no AIRule configured here — evidence-clip lookup goes through
    # Incident.source_event_id -> Event.recording_id directly, not through
    # related_alerts, precisely so a tenant with no matching rule (and therefore no
    # Alert at all) still gets a real evidence clip for an always-incident event type.
    resp = client.post(
        "/api/events",
        json={
            "camera_id": cam_id, "event_type": "GATE_JUMPING_DETECTED", "severity": "HIGH",
            "occurred_at": "2026-01-01T12:00:10Z", "recording_id": recording_id,
            "event_metadata": {"tracking_id": 1, "confidence": 0.9},
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1
    return incidents[0]


def test_pending_evidence_clips_lists_an_incident_linked_to_the_recording(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    recording = _create_recording(client, cam["id"])
    incident = _create_gate_jumping_incident(client, token, cam["id"], recording["id"])

    resp = client.get(f"/api/incidents/internal/pending-evidence-clips?recording_id={recording['id']}", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    pending = resp.json()
    assert len(pending) == 1
    assert pending[0]["incident_id"] == incident["id"]
    assert pending[0]["event_occurred_at"].startswith("2026-01-01T12:00:10")
    assert pending[0]["recording_started_at"].startswith("2026-01-01T12:00:00")
    assert pending[0]["pre_event_seconds"] == 30  # VideoIntelligenceSettings default
    assert pending[0]["post_event_seconds"] == 30


def test_pending_evidence_clips_excludes_incidents_that_already_have_one(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    recording = _create_recording(client, cam["id"])
    incident = _create_gate_jumping_incident(client, token, cam["id"], recording["id"])

    client.patch(
        f"/api/incidents/{incident['id']}/internal/evidence-clip",
        json={"evidence_clip_path": "/data/recordings/clip.mp4.incident-1.mp4"},
        headers=INTERNAL_HEADERS,
    )

    resp = client.get(f"/api/incidents/internal/pending-evidence-clips?recording_id={recording['id']}", headers=INTERNAL_HEADERS)
    assert resp.json() == []


def test_pending_evidence_clips_requires_internal_token(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    recording = _create_recording(client, cam["id"])

    resp = client.get(f"/api/incidents/internal/pending-evidence-clips?recording_id={recording['id']}", headers=auth_headers(token))
    assert resp.status_code == 401


def test_set_evidence_clip_persists_the_path(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    recording = _create_recording(client, cam["id"])
    incident = _create_gate_jumping_incident(client, token, cam["id"], recording["id"])

    resp = client.patch(
        f"/api/incidents/{incident['id']}/internal/evidence-clip",
        json={"evidence_clip_path": "/data/recordings/clip.mp4.incident-1.mp4"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200

    updated = client.get(f"/api/incidents/{incident['id']}", headers=auth_headers(token)).json()
    assert updated["evidence_clip_path"] == "/data/recordings/clip.mp4.incident-1.mp4"


def test_evidence_clip_playback_returns_404_before_a_clip_exists(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    recording = _create_recording(client, cam["id"])
    incident = _create_gate_jumping_incident(client, token, cam["id"], recording["id"])

    resp = client.get(f"/api/incidents/{incident['id']}/evidence-clip?token={token}")
    assert resp.status_code == 404


def test_evidence_clip_playback_serves_the_real_file_inline(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    recording = _create_recording(client, cam["id"])
    incident = _create_gate_jumping_incident(client, token, cam["id"], recording["id"])

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"fake evidence clip bytes")
        clip_path = f.name
    try:
        client.patch(
            f"/api/incidents/{incident['id']}/internal/evidence-clip",
            json={"evidence_clip_path": clip_path},
            headers=INTERNAL_HEADERS,
        )

        resp = client.get(f"/api/incidents/{incident['id']}/evidence-clip?token={token}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "video/mp4"
        assert "content-disposition" not in resp.headers  # plays inline, doesn't force a download
        assert resp.content == b"fake evidence clip bytes"
    finally:
        os.remove(clip_path)


def test_evidence_clip_playback_requires_a_valid_token(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    recording = _create_recording(client, cam["id"])
    incident = _create_gate_jumping_incident(client, token, cam["id"], recording["id"])

    resp = client.get(f"/api/incidents/{incident['id']}/evidence-clip?token=not-a-real-token")
    assert resp.status_code == 401
