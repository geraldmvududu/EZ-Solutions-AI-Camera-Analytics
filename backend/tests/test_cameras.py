from tests.conftest import auth_headers, login


def test_create_camera_excludes_credentials_from_response(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.post(
        "/api/cameras",
        json={
            "name": "Front Gate",
            "source_type": "RTSP",
            "stream_url": "rtsp://192.168.1.50:554/stream",
            "username": "admin",
            "password": "supersecret",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "password" not in body
    assert "stream_url" not in body
    assert "username" not in body


def test_camera_password_is_encrypted_at_rest(client, db_session, admin_user):
    import uuid

    from app.models.camera import Camera

    token = login(client, admin_user.email)
    created = client.post(
        "/api/cameras",
        json={"name": "Front Gate", "source_type": "RTSP", "stream_url": "rtsp://host/x", "password": "supersecret"},
        headers=auth_headers(token),
    ).json()

    camera = db_session.get(Camera, uuid.UUID(created["id"]))
    assert camera.password_encrypted != "supersecret"
    assert camera.password_encrypted != ""


def test_camera_code_auto_increments(client, admin_user):
    token = login(client, admin_user.email)
    first = client.post("/api/cameras", json={"name": "Cam A", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    second = client.post("/api/cameras", json={"name": "Cam B", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    assert first["camera_code"] == "CAM-001"
    assert second["camera_code"] == "CAM-002"


def test_update_camera_partial_fields(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Cam A", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = client.patch(f"/api/cameras/{cam['id']}", json={"ai_fps": 10}, headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["ai_fps"] == 10
    assert resp.json()["name"] == "Cam A"


def test_delete_camera(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Cam A", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = client.delete(f"/api/cameras/{cam['id']}", headers=auth_headers(token))
    assert resp.status_code == 204

    resp = client.get(f"/api/cameras/{cam['id']}", headers=auth_headers(token))
    assert resp.status_code == 404


def test_video_file_test_connection_reports_missing_file(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post(
        "/api/cameras",
        json={"name": "Cam A", "source_type": "VIDEO_FILE", "video_file_path": "/nonexistent/video.mp4"},
        headers=auth_headers(token),
    ).json()

    resp = client.post(f"/api/cameras/{cam['id']}/test-connection", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["success"] is False


def test_internal_active_cameras_includes_tenant_liveness_setting(client, admin_user):
    """GET /cameras/internal/active flattens the tenant's FaceRecognitionSettings.
    liveness_detection_enabled onto each camera — ai-engine's FaceRecognizer has no
    other way to read a tenant-level (not camera-level) setting."""
    token = login(client, admin_user.email)
    client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token))
    client.put("/api/face-settings", json={"liveness_detection_enabled": True}, headers=auth_headers(token))

    resp = client.get("/api/cameras/internal/active", headers={"X-Internal-Token": "test-internal-token"})
    assert resp.status_code == 200
    cameras = resp.json()
    assert len(cameras) == 1
    assert cameras[0]["liveness_detection_enabled"] is True


def test_internal_active_cameras_default_liveness_is_false(client, admin_user):
    token = login(client, admin_user.email)
    client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token))

    resp = client.get("/api/cameras/internal/active", headers={"X-Internal-Token": "test-internal-token"})
    assert resp.json()[0]["liveness_detection_enabled"] is False


def test_internal_active_cameras_includes_tenant_recognition_cooldown(client, admin_user):
    """GET /cameras/internal/active flattens the tenant's FaceRecognitionSettings.
    recognition_cooldown_seconds onto each camera — without this, an admin's cooldown
    change in Settings would never reach ai-engine's FaceRecognizer, which would keep
    using its own static FACE_EVENT_COOLDOWN env var regardless of what's configured."""
    token = login(client, admin_user.email)
    client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token))
    client.put("/api/face-settings", json={"recognition_cooldown_seconds": 90}, headers=auth_headers(token))

    resp = client.get("/api/cameras/internal/active", headers={"X-Internal-Token": "test-internal-token"})
    assert resp.status_code == 200
    cameras = resp.json()
    assert len(cameras) == 1
    assert cameras[0]["recognition_cooldown_seconds"] == 90


def test_internal_active_cameras_default_recognition_cooldown_matches_model_default(client, admin_user):
    token = login(client, admin_user.email)
    client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token))

    resp = client.get("/api/cameras/internal/active", headers={"X-Internal-Token": "test-internal-token"})
    assert resp.json()[0]["recognition_cooldown_seconds"] == 30
