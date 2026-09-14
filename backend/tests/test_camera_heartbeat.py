"""POST /api/cameras/{id}/heartbeat — real gap found by direct code read: CAMERA_OFFLINE/
CAMERA_ONLINE already existed as EventType values, and this endpoint's own docstring
already said it was "used to derive real ONLINE/OFFLINE status," but nothing ever actually
flipped a stale camera to OFFLINE or reported either event. This file covers the
OFFLINE -> ONLINE transition this endpoint is now responsible for (the ONLINE -> OFFLINE
direction lives in worker.py::check_camera_health, covered in worker/tests/test_app.py)."""

import uuid

from app.models.camera import Camera, CameraStatus
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _create_camera(client, token) -> str:
    return client.post(
        "/api/cameras",
        json={"name": "Gate Cam", "source_type": "SIMULATED"},
        headers=auth_headers(token),
    ).json()["id"]


def test_heartbeat_sets_online_and_updates_timestamp(client, admin_user):
    token = login(client, admin_user.email)
    camera_id = _create_camera(client, token)

    resp = client.post(f"/api/cameras/{camera_id}/heartbeat", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200, resp.text

    camera = client.get(f"/api/cameras/{camera_id}", headers=auth_headers(token)).json()
    assert camera["status"] == "ONLINE"


def test_heartbeat_from_offline_creates_a_camera_online_event(client, admin_user, db_session):
    token = login(client, admin_user.email)
    camera_id = _create_camera(client, token)

    db_camera = db_session.get(Camera, uuid.UUID(camera_id))
    db_camera.status = CameraStatus.OFFLINE
    db_session.commit()

    resp = client.post(f"/api/cameras/{camera_id}/heartbeat", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200, resp.text

    events = client.get(f"/api/events?camera_id={camera_id}", headers=auth_headers(token)).json()
    online_events = [e for e in events if e["event_type"] == "CAMERA_ONLINE"]
    assert len(online_events) == 1
    assert online_events[0]["severity"] == "LOW"


def test_heartbeat_while_already_online_does_not_create_a_second_event(client, admin_user):
    """A brand-new camera defaults to OFFLINE, so its first-ever heartbeat legitimately
    transitions OFFLINE -> ONLINE and creates one CAMERA_ONLINE event. Repeated heartbeats
    after that (the normal, common case — ai-engine posts one every ~10s while running)
    must not spam a fresh event every time, which is what would happen if this only
    checked "is the camera ONLINE now" instead of "was it OFFLINE a moment ago"."""
    token = login(client, admin_user.email)
    camera_id = _create_camera(client, token)

    client.post(f"/api/cameras/{camera_id}/heartbeat", headers=INTERNAL_HEADERS)  # first-ever: OFFLINE -> ONLINE
    client.post(f"/api/cameras/{camera_id}/heartbeat", headers=INTERNAL_HEADERS)
    client.post(f"/api/cameras/{camera_id}/heartbeat", headers=INTERNAL_HEADERS)

    events = client.get(f"/api/events?camera_id={camera_id}", headers=auth_headers(token)).json()
    assert len([e for e in events if e["event_type"] == "CAMERA_ONLINE"]) == 1


def test_heartbeat_requires_internal_token(client, admin_user):
    token = login(client, admin_user.email)
    camera_id = _create_camera(client, token)

    resp = client.post(f"/api/cameras/{camera_id}/heartbeat", headers=auth_headers(token))
    assert resp.status_code in (401, 403)


def test_heartbeat_404_for_unknown_camera(client):
    resp = client.post(f"/api/cameras/{uuid.uuid4()}/heartbeat", headers=INTERNAL_HEADERS)
    assert resp.status_code == 404
