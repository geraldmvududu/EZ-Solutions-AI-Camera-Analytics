"""POST /api/cameras/{id}/internal/mark-video-processed — real user request: a finite/
looping video file kept producing genuinely "new" events every time it looped back to
the start (each crossing is more than the cooldown window apart from the last, so it
looks like a distinct occurrence). This lets worker.py report back once a VIDEO_FILE
camera with loop_video=False genuinely reaches end-of-file, so main.py's discovery
loop stops restarting it and re-analyzing the same footage forever."""

from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _create_video_file_camera(client, token, loop_video: bool = False) -> str:
    return client.post(
        "/api/cameras",
        json={"name": "External Footage", "source_type": "VIDEO_FILE", "video_file_path": "/data/uploads/x.mp4", "loop_video": loop_video},
        headers=auth_headers(token),
    ).json()["id"]


def test_mark_video_processed_sets_timestamp_and_deactivates_camera(client, admin_user):
    token = login(client, admin_user.email)
    camera_id = _create_video_file_camera(client, token)

    resp = client.post(f"/api/cameras/{camera_id}/internal/mark-video-processed", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200, resp.text

    camera = client.get(f"/api/cameras/{camera_id}", headers=auth_headers(token)).json()
    assert camera["video_processed_at"] is not None
    assert camera["is_active"] is False


def test_mark_video_processed_requires_internal_token(client, admin_user):
    token = login(client, admin_user.email)
    camera_id = _create_video_file_camera(client, token)

    resp = client.post(f"/api/cameras/{camera_id}/internal/mark-video-processed", headers=auth_headers(token))
    assert resp.status_code in (401, 403)


def test_mark_video_processed_404_for_unknown_camera(client):
    import uuid

    resp = client.post(f"/api/cameras/{uuid.uuid4()}/internal/mark-video-processed", headers=INTERNAL_HEADERS)
    assert resp.status_code == 404


def test_mark_video_processed_is_idempotent(client, admin_user):
    """Calling it twice must not overwrite the original timestamp — worker.py could
    plausibly call this more than once (e.g. a restart racing the exact same EOF)."""
    token = login(client, admin_user.email)
    camera_id = _create_video_file_camera(client, token)

    client.post(f"/api/cameras/{camera_id}/internal/mark-video-processed", headers=INTERNAL_HEADERS)
    first = client.get(f"/api/cameras/{camera_id}", headers=auth_headers(token)).json()["video_processed_at"]

    client.post(f"/api/cameras/{camera_id}/internal/mark-video-processed", headers=INTERNAL_HEADERS)
    second = client.get(f"/api/cameras/{camera_id}", headers=auth_headers(token)).json()["video_processed_at"]

    assert first == second


def test_marked_processed_camera_no_longer_appears_in_active_cameras(client, admin_user):
    """The actual mechanism that stops main.py's discovery loop from restarting it."""
    token = login(client, admin_user.email)
    camera_id = _create_video_file_camera(client, token)

    active_before = client.get("/api/cameras/internal/active", headers=INTERNAL_HEADERS).json()
    assert any(c["id"] == camera_id for c in active_before)

    client.post(f"/api/cameras/{camera_id}/internal/mark-video-processed", headers=INTERNAL_HEADERS)

    active_after = client.get("/api/cameras/internal/active", headers=INTERNAL_HEADERS).json()
    assert not any(c["id"] == camera_id for c in active_after)
