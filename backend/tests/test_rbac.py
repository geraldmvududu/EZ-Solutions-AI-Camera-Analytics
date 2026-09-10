from tests.conftest import auth_headers, login


def test_viewer_can_list_cameras(client, viewer_user):
    token = login(client, viewer_user.email)
    resp = client.get("/api/cameras", headers=auth_headers(token))
    assert resp.status_code == 200


def test_viewer_cannot_create_camera(client, viewer_user):
    token = login(client, viewer_user.email)
    resp = client.post(
        "/api/cameras",
        json={"name": "Hack Cam", "source_type": "SIMULATED"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


def test_viewer_cannot_manage_users(client, viewer_user):
    token = login(client, viewer_user.email)
    resp = client.get("/api/users", headers=auth_headers(token))
    assert resp.status_code == 403


def test_admin_can_create_camera(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.post(
        "/api/cameras",
        json={"name": "Front Gate", "source_type": "SIMULATED"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    assert resp.json()["camera_code"] == "CAM-001"


def test_admin_can_manage_users(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.get("/api/users", headers=auth_headers(token))
    assert resp.status_code == 200


def test_internal_endpoint_rejects_missing_token(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post(
        "/api/cameras", json={"name": "Warehouse", "source_type": "SIMULATED"}, headers=auth_headers(token)
    ).json()

    resp = client.post(
        "/api/detections",
        json={
            "camera_id": cam["id"],
            "object_type": "PERSON",
            "confidence": 0.9,
            "bbox_x": 0.1,
            "bbox_y": 0.1,
            "bbox_width": 0.2,
            "bbox_height": 0.4,
            "tracking_id": 1,
            "detected_at": "2026-01-01T00:00:00Z",
        },
    )
    assert resp.status_code == 401


def test_internal_endpoint_accepts_valid_service_token(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post(
        "/api/cameras", json={"name": "Warehouse", "source_type": "SIMULATED"}, headers=auth_headers(token)
    ).json()

    resp = client.post(
        "/api/detections",
        json={
            "camera_id": cam["id"],
            "object_type": "PERSON",
            "confidence": 0.9,
            "bbox_x": 0.1,
            "bbox_y": 0.1,
            "bbox_width": 0.2,
            "bbox_height": 0.4,
            "tracking_id": 1,
            "detected_at": "2026-01-01T00:00:00Z",
        },
        headers={"X-Internal-Token": "test-internal-token"},
    )
    assert resp.status_code == 201
