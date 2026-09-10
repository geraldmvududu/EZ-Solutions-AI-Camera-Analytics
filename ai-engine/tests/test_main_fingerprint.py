from app.main import _config_fingerprint


def _camera(**overrides):
    base = {
        "id": "cam-1",
        "name": "Front Gate",
        "source_type": "SIMULATED",
        "ai_enabled": True,
        "recording_mode": "AI_EVENT",
        "last_heartbeat_at": "2026-01-01T00:00:00Z",
        "status": "OFFLINE",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_heartbeat_and_status_changes_do_not_change_fingerprint():
    """Regression test: a worker's own heartbeat/status updates must NOT look like a
    config change, or main()'s hot-reload would restart every camera on every
    discovery cycle forever (this actually happened during development)."""
    camera_a = _camera(last_heartbeat_at="2026-01-01T00:00:00Z", status="OFFLINE")
    camera_b = _camera(last_heartbeat_at="2026-01-01T00:05:00Z", status="ONLINE")

    assert _config_fingerprint(camera_a, [], []) == _config_fingerprint(camera_b, [], [])


def test_recording_mode_change_changes_fingerprint():
    camera_a = _camera(recording_mode="AI_EVENT")
    camera_b = _camera(recording_mode="CONTINUOUS")

    assert _config_fingerprint(camera_a, [], []) != _config_fingerprint(camera_b, [], [])


def test_adding_a_zone_changes_fingerprint():
    camera = _camera()
    zone = {"id": "z1", "camera_id": "cam-1", "zone_type": "PRIVACY", "polygon": [[0, 0], [1, 0], [1, 1]]}

    assert _config_fingerprint(camera, [], []) != _config_fingerprint(camera, [zone], [])


def test_other_cameras_zones_are_irrelevant():
    camera = _camera()
    other_camera_zone = {"id": "z1", "camera_id": "cam-2", "zone_type": "PRIVACY", "polygon": [[0, 0], [1, 0], [1, 1]]}

    assert _config_fingerprint(camera, [], []) == _config_fingerprint(camera, [other_camera_zone], [])
