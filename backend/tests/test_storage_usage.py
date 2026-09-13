"""Event-First Cloud Storage Phase 1 (section 18): GET /api/storage/usage against real
rows with known file_size_bytes — the aggregate is hand-verified, not just "did it
return 200", matching this project's own convention (see
test_analytics.py::test_total_counts_are_not_collapsed_by_aggregate_subquery for the
precedent this mirrors)."""

import uuid
from datetime import datetime, timezone

from app.models.event import Event, EventCategory, EventType, EventSeverity
from app.models.incident import Incident, IncidentStatus
from app.models.recording import Recording, RecordingTrigger
from app.models.snapshot import Snapshot
from tests.conftest import auth_headers, login


def _make_camera(client, token, name="Cam") -> uuid.UUID:
    body = client.post("/api/cameras", json={"name": name, "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    return uuid.UUID(body["id"])


def test_storage_usage_is_zero_for_a_tenant_with_no_data(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.get("/api/storage/usage", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["event_metadata_bytes"] == 0
    assert body["snapshot_bytes"] == 0
    assert body["evidence_clip_bytes"] == 0
    assert body["cloud_recording_bytes"] == 0
    assert body["continuous_recording_bytes"] == 0
    assert body["total_bytes"] == 0
    assert body["is_estimate"] is True


def test_storage_usage_sums_real_snapshot_sizes(client, db_session, admin_user):
    token = login(client, admin_user.email)
    camera_id = _make_camera(client, token)

    db_session.add_all([
        Snapshot(tenant_id=admin_user.tenant_id, camera_id=camera_id, file_path="/data/a.jpg", file_size_bytes=1000, taken_at=datetime.now(timezone.utc)),
        Snapshot(tenant_id=admin_user.tenant_id, camera_id=camera_id, file_path="/data/b.jpg", file_size_bytes=2500, taken_at=datetime.now(timezone.utc)),
    ])
    db_session.commit()

    resp = client.get("/api/storage/usage", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["snapshot_bytes"] == 3500


def test_storage_usage_splits_cloud_vs_continuous_recordings(client, db_session, admin_user):
    token = login(client, admin_user.email)
    camera_id = _make_camera(client, token)

    db_session.add_all([
        Recording(
            tenant_id=admin_user.tenant_id, camera_id=camera_id, file_path="/data/cloud.mp4", storage_key="tenant/cloud.mp4",
            started_at=datetime.now(timezone.utc), trigger_type=RecordingTrigger.AI_EVENT, file_size_bytes=5000,
        ),
        Recording(
            tenant_id=admin_user.tenant_id, camera_id=camera_id, file_path="/data/local.mp4", storage_key=None,
            started_at=datetime.now(timezone.utc), trigger_type=RecordingTrigger.CONTINUOUS, file_size_bytes=9000,
        ),
    ])
    db_session.commit()

    resp = client.get("/api/storage/usage", headers=auth_headers(token))
    body = resp.json()
    assert body["cloud_recording_bytes"] == 5000
    assert body["continuous_recording_bytes"] == 9000


def test_storage_usage_sums_evidence_clip_sizes(client, db_session, admin_user):
    token = login(client, admin_user.email)

    db_session.add(
        Incident(
            tenant_id=admin_user.tenant_id, title="Gate Jump", severity=EventSeverity.HIGH,
            status=IncidentStatus.OPEN, evidence_clip_size_bytes=4200,
        )
    )
    db_session.commit()

    resp = client.get("/api/storage/usage", headers=auth_headers(token))
    assert resp.json()["evidence_clip_bytes"] == 4200


def test_storage_usage_event_metadata_is_row_count_times_estimate(client, db_session, admin_user):
    token = login(client, admin_user.email)
    camera_id = _make_camera(client, token)

    for _ in range(3):
        db_session.add(
            Event(
                tenant_id=admin_user.tenant_id, camera_id=camera_id, event_type=EventType.MOTION_DETECTED,
                severity=EventSeverity.INFO, occurred_at=datetime.now(timezone.utc), event_category=EventCategory.OPERATIONS,
            )
        )
    db_session.commit()

    resp = client.get("/api/storage/usage", headers=auth_headers(token))
    body = resp.json()
    assert body["event_metadata_bytes"] == 3 * 512
    assert body["is_estimate"] is True


def test_storage_usage_total_bytes_matches_sum_of_components(client, db_session, admin_user):
    token = login(client, admin_user.email)
    camera_id = _make_camera(client, token)

    db_session.add_all([
        Snapshot(tenant_id=admin_user.tenant_id, camera_id=camera_id, file_path="/data/a.jpg", file_size_bytes=100, taken_at=datetime.now(timezone.utc)),
        Recording(
            tenant_id=admin_user.tenant_id, camera_id=camera_id, file_path="/data/c.mp4", storage_key="k",
            started_at=datetime.now(timezone.utc), trigger_type=RecordingTrigger.AI_EVENT, file_size_bytes=200,
        ),
    ])
    db_session.commit()

    resp = client.get("/api/storage/usage", headers=auth_headers(token))
    body = resp.json()
    assert body["total_bytes"] == (
        body["event_metadata_bytes"] + body["snapshot_bytes"] + body["evidence_clip_bytes"]
        + body["cloud_recording_bytes"] + body["continuous_recording_bytes"]
    )
    assert body["total_bytes"] == 300


def test_storage_usage_is_tenant_scoped(client, db_session, admin_user, roles):
    from app.core.security import hash_password
    from app.models.tenant import Tenant
    from app.models.user import User

    token_a = login(client, admin_user.email)
    camera_id_a = _make_camera(client, token_a, "Tenant A Cam")
    db_session.add(Snapshot(tenant_id=admin_user.tenant_id, camera_id=camera_id_a, file_path="/data/a.jpg", file_size_bytes=9999, taken_at=datetime.now(timezone.utc)))
    db_session.commit()

    tenant_b = Tenant(name="Other Org", slug="other-org")
    db_session.add(tenant_b)
    db_session.commit()
    db_session.refresh(tenant_b)
    user_b = User(tenant_id=tenant_b.id, email="admin@other-org.lan", password_hash=hash_password("Password123!"), full_name="Other Admin", role_id=roles["ADMIN"].id)
    db_session.add(user_b)
    db_session.commit()
    db_session.refresh(user_b)
    token_b = login(client, user_b.email)

    resp_b = client.get("/api/storage/usage", headers=auth_headers(token_b))
    assert resp_b.json()["snapshot_bytes"] == 0

    resp_a = client.get("/api/storage/usage", headers=auth_headers(token_a))
    assert resp_a.json()["snapshot_bytes"] == 9999


def test_viewer_can_view_storage_usage(client, viewer_user):
    token = login(client, viewer_user.email)
    resp = client.get("/api/storage/usage", headers=auth_headers(token))
    assert resp.status_code == 200
