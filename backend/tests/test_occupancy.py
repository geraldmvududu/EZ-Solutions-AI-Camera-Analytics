"""POST /api/cameras/{id}/internal/occupancy-delta — Master Development Prompt Phase 1,
"Crowd/Occupancy Counting". Real gap found by direct code read: zero occupancy/crowd
code existed anywhere in this codebase. ai-engine posts a real +1/-1 delta per genuine
ENTERING/EXITING tripwire crossing (see ai-engine/tests/test_occupancy_counting.py for
that side); this endpoint maintains the running Camera.current_occupancy counter and
fires MAXIMUM_OCCUPANCY_EXCEEDED only on the transition from at-or-under to over
Camera.max_occupancy."""

import uuid

from app.models.camera import Camera
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _create_camera(client, token, max_occupancy=None) -> str:
    payload = {"name": "Lobby", "source_type": "SIMULATED"}
    if max_occupancy is not None:
        payload["max_occupancy"] = max_occupancy
    return client.post("/api/cameras", json=payload, headers=auth_headers(token)).json()["id"]


def _delta(client, camera_id, delta):
    return client.post(f"/api/cameras/{camera_id}/internal/occupancy-delta", json={"delta": delta}, headers=INTERNAL_HEADERS)


def test_deltas_increment_and_decrement_current_occupancy(client, admin_user):
    token = login(client, admin_user.email)
    camera_id = _create_camera(client, token)

    assert _delta(client, camera_id, 1).json()["current_occupancy"] == 1
    assert _delta(client, camera_id, 1).json()["current_occupancy"] == 2
    assert _delta(client, camera_id, -1).json()["current_occupancy"] == 1


def test_occupancy_never_goes_negative(client, admin_user):
    """An EXITING delta arriving before its matching ENTERING one was ever recorded
    (e.g. a worker restart lost the running count) must clamp at 0, not go negative."""
    token = login(client, admin_user.email)
    camera_id = _create_camera(client, token)

    assert _delta(client, camera_id, -1).json()["current_occupancy"] == 0
    assert _delta(client, camera_id, -5).json()["current_occupancy"] == 0


def test_fires_maximum_occupancy_exceeded_only_on_the_crossing_transition(client, admin_user):
    token = login(client, admin_user.email)
    camera_id = _create_camera(client, token, max_occupancy=2)

    _delta(client, camera_id, 1)  # 1: at/under
    _delta(client, camera_id, 1)  # 2: at/under (== max, not yet over)
    events = client.get(f"/api/events?camera_id={camera_id}", headers=auth_headers(token)).json()
    assert not [e for e in events if e["event_type"] == "MAXIMUM_OCCUPANCY_EXCEEDED"]

    _delta(client, camera_id, 1)  # 3: the actual crossing into "over"
    events = client.get(f"/api/events?camera_id={camera_id}", headers=auth_headers(token)).json()
    exceeded = [e for e in events if e["event_type"] == "MAXIMUM_OCCUPANCY_EXCEEDED"]
    assert len(exceeded) == 1
    assert exceeded[0]["severity"] == "HIGH"

    _delta(client, camera_id, 1)  # 4: still over, must NOT refire
    events = client.get(f"/api/events?camera_id={camera_id}", headers=auth_headers(token)).json()
    assert len([e for e in events if e["event_type"] == "MAXIMUM_OCCUPANCY_EXCEEDED"]) == 1


def test_no_max_occupancy_configured_never_fires(client, admin_user):
    token = login(client, admin_user.email)
    camera_id = _create_camera(client, token)  # max_occupancy left unset (None)

    for _ in range(10):
        _delta(client, camera_id, 1)

    events = client.get(f"/api/events?camera_id={camera_id}", headers=auth_headers(token)).json()
    assert not [e for e in events if e["event_type"] == "MAXIMUM_OCCUPANCY_EXCEEDED"]


def test_dropping_back_under_and_exceeding_again_refires(client, admin_user):
    token = login(client, admin_user.email)
    camera_id = _create_camera(client, token, max_occupancy=1)

    _delta(client, camera_id, 1)
    _delta(client, camera_id, 1)  # crosses to 2, over max=1 -> fires
    _delta(client, camera_id, -2)  # back down to 0
    _delta(client, camera_id, 1)
    _delta(client, camera_id, 1)  # crosses to 2 again -> fires again

    events = client.get(f"/api/events?camera_id={camera_id}", headers=auth_headers(token)).json()
    assert len([e for e in events if e["event_type"] == "MAXIMUM_OCCUPANCY_EXCEEDED"]) == 2


def test_requires_internal_token(client, admin_user):
    token = login(client, admin_user.email)
    camera_id = _create_camera(client, token)

    resp = client.post(f"/api/cameras/{camera_id}/internal/occupancy-delta", json={"delta": 1}, headers=auth_headers(token))
    assert resp.status_code in (401, 403)


def test_404_for_unknown_camera(client):
    resp = _delta(client, uuid.uuid4(), 1)
    assert resp.status_code == 404


def test_max_occupancy_is_admin_settable_and_returned(client, admin_user):
    token = login(client, admin_user.email)
    camera_id = _create_camera(client, token, max_occupancy=50)

    camera = client.get(f"/api/cameras/{camera_id}", headers=auth_headers(token)).json()
    assert camera["max_occupancy"] == 50
    assert camera["current_occupancy"] == 0

    resp = client.patch(f"/api/cameras/{camera_id}", json={"max_occupancy": 100}, headers=auth_headers(token))
    assert resp.json()["max_occupancy"] == 100
