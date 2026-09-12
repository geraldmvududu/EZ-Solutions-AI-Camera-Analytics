"""AI Video Intelligence Phase 1: the new RESTRICTED_AREA zone type and the new
gate-jump/tailgating opt-in fields on Tripwire (sections 4/5/8) — confirming they
actually round-trip through the real API, since ai-engine's worker.py reads them
straight off the dicts returned by GET /zones/internal/all and
GET /tripwires/internal/all."""

from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def test_create_restricted_area_zone(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Server Room", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = client.post(
        "/api/zones",
        json={"camera_id": cam["id"], "name": "Server Room", "zone_type": "RESTRICTED_AREA", "polygon": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]], "loitering_threshold_seconds": 10},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["zone_type"] == "RESTRICTED_AREA"
    assert resp.json()["loitering_threshold_seconds"] == 10


def test_internal_zones_endpoint_includes_restricted_area(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Server Room", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    client.post(
        "/api/zones",
        json={"camera_id": cam["id"], "name": "Server Room", "zone_type": "RESTRICTED_AREA", "polygon": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]]},
        headers=auth_headers(token),
    )

    resp = client.get("/api/zones/internal/all", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    assert any(z["zone_type"] == "RESTRICTED_AREA" for z in resp.json())


def test_create_tripwire_with_gate_jump_and_tailgating_flags(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Main Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = client.post(
        "/api/tripwires",
        json={
            "camera_id": cam["id"], "name": "Gate Line", "line": [[0.0, 0.5], [1.0, 0.5]],
            "gate_jump_detection_enabled": True, "tailgating_detection_enabled": True, "tailgating_window_seconds": 3,
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["gate_jump_detection_enabled"] is True
    assert body["tailgating_detection_enabled"] is True
    assert body["tailgating_window_seconds"] == 3


def test_tripwire_gate_jump_and_tailgating_default_to_disabled(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Main Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = client.post(
        "/api/tripwires",
        json={"camera_id": cam["id"], "name": "Gate Line", "line": [[0.0, 0.5], [1.0, 0.5]]},
        headers=auth_headers(token),
    )
    body = resp.json()
    assert body["gate_jump_detection_enabled"] is False
    assert body["tailgating_detection_enabled"] is False
    assert body["tailgating_window_seconds"] == 5


def test_internal_tripwires_endpoint_includes_the_new_flags(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Main Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    client.post(
        "/api/tripwires",
        json={"camera_id": cam["id"], "name": "Gate Line", "line": [[0.0, 0.5], [1.0, 0.5]], "gate_jump_detection_enabled": True},
        headers=auth_headers(token),
    )

    resp = client.get("/api/tripwires/internal/all", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    tripwire = next(t for t in resp.json() if t["name"] == "Gate Line")
    assert tripwire["gate_jump_detection_enabled"] is True


def test_update_tripwire_can_toggle_tailgating(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Main Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    tripwire = client.post(
        "/api/tripwires",
        json={"camera_id": cam["id"], "name": "Gate Line", "line": [[0.0, 0.5], [1.0, 0.5]]},
        headers=auth_headers(token),
    ).json()

    resp = client.patch(f"/api/tripwires/{tripwire['id']}", json={"tailgating_detection_enabled": True, "tailgating_window_seconds": 8}, headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["tailgating_detection_enabled"] is True
    assert resp.json()["tailgating_window_seconds"] == 8
