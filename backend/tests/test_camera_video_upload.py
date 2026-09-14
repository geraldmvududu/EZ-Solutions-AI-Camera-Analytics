"""POST /api/cameras/upload-video — requested by the user directly: a way to feed in
footage from an external source (a hard drive, an old DVR export) as a VIDEO_FILE
camera's source instead of typing a server-side path by hand. The browser reads the
file from wherever it's actually stored and streams it here; the returned path is used
exactly like any manually-typed video_file_path."""

import io
import os

import pytest

from app.api.routes import cameras as cameras_module
from tests.conftest import auth_headers, login


@pytest.fixture(autouse=True)
def tmp_upload_path(tmp_path, monkeypatch):
    monkeypatch.setattr(cameras_module.settings, "upload_path", str(tmp_path))
    return tmp_path


def test_upload_video_streams_the_file_and_returns_its_path(client, admin_user, tmp_upload_path):
    token = login(client, admin_user.email)
    content = b"fake mp4 bytes" * 1000

    resp = client.post(
        "/api/cameras/upload-video",
        headers=auth_headers(token),
        files={"video": ("footage.mp4", io.BytesIO(content), "video/mp4")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["size_bytes"] == len(content)
    assert os.path.isfile(body["video_file_path"])
    with open(body["video_file_path"], "rb") as f:
        assert f.read() == content


def test_upload_video_rejects_an_unsupported_extension(client, admin_user):
    token = login(client, admin_user.email)

    resp = client.post(
        "/api/cameras/upload-video",
        headers=auth_headers(token),
        files={"video": ("notes.txt", io.BytesIO(b"not a video"), "text/plain")},
    )

    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


def test_upload_video_requires_manage_cameras_permission(client, admin_user, viewer_user):
    viewer_token = login(client, viewer_user.email)

    resp = client.post(
        "/api/cameras/upload-video",
        headers=auth_headers(viewer_token),
        files={"video": ("footage.mp4", io.BytesIO(b"x"), "video/mp4")},
    )

    assert resp.status_code == 403


def test_upload_video_refuses_when_disk_space_would_run_out(client, admin_user, monkeypatch, tmp_upload_path):
    """Real incident this session: the VM's disk hit 100% and took Postgres down with
    it. An upload must abort — and clean up its partial file — rather than risk
    causing that again."""
    token = login(client, admin_user.email)

    class _FakeUsage:
        free = cameras_module.MIN_FREE_DISK_BYTES_AFTER_UPLOAD - 1

    monkeypatch.setattr(cameras_module.shutil, "disk_usage", lambda path: _FakeUsage())

    resp = client.post(
        "/api/cameras/upload-video",
        headers=auth_headers(token),
        files={"video": ("footage.mp4", io.BytesIO(b"some real bytes to write"), "video/mp4")},
    )

    assert resp.status_code == 507
    assert list(tmp_upload_path.rglob("*.mp4")) == [], "the partial file must be cleaned up, not left behind"


def test_uploaded_video_path_can_be_used_to_create_a_video_file_camera(client, admin_user):
    """The join between the two features: confirms the returned path is genuinely
    usable, not just a string that looks right."""
    token = login(client, admin_user.email)
    upload_resp = client.post(
        "/api/cameras/upload-video",
        headers=auth_headers(token),
        files={"video": ("footage.mp4", io.BytesIO(b"fake mp4 bytes"), "video/mp4")},
    )
    video_path = upload_resp.json()["video_file_path"]

    camera_resp = client.post(
        "/api/cameras",
        json={"name": "From Hard Drive", "source_type": "VIDEO_FILE", "video_file_path": video_path},
        headers=auth_headers(token),
    )

    assert camera_resp.status_code == 201, camera_resp.text
    assert camera_resp.json()["video_file_path"] == video_path
