"""GET /api/reports/events/{id}.pdf — a per-event PDF export, requested after a user
reported no way to get a shareable record of a single event's full detail (the
existing security-report.pdf is a tenant-wide aggregate, not a per-event document).

The image-embedding tests below cover a follow-up request: the report initially shipped
with event type/severity/description/metadata but no picture, even though the Events
page's own detail modal always showed the snapshot image right alongside those same
fields — the PDF export needs to match, not omit the one thing a reviewer usually wants
most out of a "what happened here" report."""

import uuid
from datetime import datetime, timezone

import cv2
import numpy as np

from app.models.event import Event
from app.models.snapshot import Snapshot
from app.services import object_storage
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _jpeg_bytes(seed: int) -> bytes:
    img = np.full((120, 160, 3), seed % 255, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def test_event_pdf_is_generated_with_real_content(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    event = client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "TRIPWIRE_VIOLATION", "severity": "HIGH",
            "occurred_at": datetime.now(timezone.utc).isoformat(), "event_metadata": {"direction": "ENTERING", "tracking_id": 1},
        },
        headers=INTERNAL_HEADERS,
    ).json()

    resp = client.get(f"/api/reports/events/{event['id']}.pdf", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_event_pdf_404_for_unknown_id(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.get(f"/api/reports/events/{uuid.uuid4()}.pdf", headers=auth_headers(token))
    assert resp.status_code == 404


def test_event_pdf_404_across_tenants(client, db_session, admin_user, roles):
    from app.core.security import hash_password
    from app.models.tenant import Tenant
    from app.models.user import User

    token_a = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token_a)).json()
    event = client.post(
        "/api/events",
        json={"camera_id": cam["id"], "event_type": "MOTION_DETECTED", "occurred_at": datetime.now(timezone.utc).isoformat()},
        headers=INTERNAL_HEADERS,
    ).json()

    tenant_b = Tenant(name="Other Org", slug="other-org")
    db_session.add(tenant_b)
    db_session.commit()
    db_session.refresh(tenant_b)
    user_b = User(tenant_id=tenant_b.id, email="admin@other-org.lan", password_hash=hash_password("Password123!"), full_name="Other Admin", role_id=roles["ADMIN"].id)
    db_session.add(user_b)
    db_session.commit()
    db_session.refresh(user_b)
    token_b = login(client, user_b.email)

    resp = client.get(f"/api/reports/events/{event['id']}.pdf", headers=auth_headers(token_b))
    assert resp.status_code == 404


def test_viewer_can_download_event_pdf(client, admin_user, viewer_user):
    admin_token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(admin_token)).json()
    event = client.post(
        "/api/events",
        json={"camera_id": cam["id"], "event_type": "PERSON_DETECTED", "occurred_at": datetime.now(timezone.utc).isoformat()},
        headers=INTERNAL_HEADERS,
    ).json()

    viewer_token = login(client, viewer_user.email)
    resp = client.get(f"/api/reports/events/{event['id']}.pdf", headers=auth_headers(viewer_token))
    assert resp.status_code == 200


def _event_with_snapshot(client, db_session, tenant, token, *, storage_key: str | None, file_path: str) -> str:
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    event_resp = client.post(
        "/api/events",
        json={"camera_id": cam["id"], "event_type": "TRIPWIRE_VIOLATION", "severity": "HIGH", "occurred_at": datetime.now(timezone.utc).isoformat()},
        headers=INTERNAL_HEADERS,
    ).json()

    snapshot = Snapshot(tenant_id=tenant.id, camera_id=uuid.UUID(cam["id"]), file_path=file_path, storage_key=storage_key, taken_at=datetime.now(timezone.utc))
    db_session.add(snapshot)
    db_session.commit()

    event = db_session.get(Event, uuid.UUID(event_resp["id"]))
    event.snapshot_id = snapshot.id
    db_session.commit()
    return event_resp["id"]


def test_event_pdf_embeds_a_real_local_snapshot_image(client, db_session, admin_user, tenant, tmp_path):
    token = login(client, admin_user.email)
    photo_path = tmp_path / "snap.jpg"
    photo_path.write_bytes(_jpeg_bytes(10))

    event_id = _event_with_snapshot(client, db_session, tenant, token, storage_key=None, file_path=str(photo_path))

    resp = client.get(f"/api/reports/events/{event_id}.pdf", headers=auth_headers(token))
    assert resp.status_code == 200
    assert b"/DCTDecode" in resp.content, "the local snapshot's real JPEG bytes must be embedded in the PDF, not just referenced"


def test_event_pdf_embeds_a_cloud_stored_snapshot_image(client, db_session, admin_user, tenant, monkeypatch):
    """A snapshot with storage_key set (Event-First Cloud Storage Phase 1) has no
    reachable local file at all — the PDF export must fetch the real bytes via
    object_storage.download_object rather than trying (and failing) to open file_path
    or, worse, redirecting like the browser-facing snapshot endpoint does."""
    token = login(client, admin_user.email)
    monkeypatch.setattr(object_storage, "download_object", lambda key: _jpeg_bytes(20))

    event_id = _event_with_snapshot(
        client, db_session, tenant, token, storage_key="tenant-1/site-1/camera-1/snapshots/evidence.jpg", file_path="/no/such/file.jpg"
    )

    resp = client.get(f"/api/reports/events/{event_id}.pdf", headers=auth_headers(token))
    assert resp.status_code == 200
    assert b"/DCTDecode" in resp.content


def test_event_pdf_still_generates_when_snapshot_file_is_missing(client, db_session, admin_user, tenant):
    """The image is best-effort: a snapshot row whose file was never actually written
    (or has since been deleted) must not break the rest of the report."""
    token = login(client, admin_user.email)
    event_id = _event_with_snapshot(client, db_session, tenant, token, storage_key=None, file_path="/no/such/file.jpg")

    resp = client.get(f"/api/reports/events/{event_id}.pdf", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"
    assert b"/DCTDecode" not in resp.content


def test_event_pdf_has_no_image_section_marker_when_event_has_no_snapshot(client, admin_user):
    """Regression guard for the original (image-less) behavior: an event that never had
    a snapshot at all still renders a complete, valid PDF."""
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    event = client.post(
        "/api/events",
        json={"camera_id": cam["id"], "event_type": "MOTION_DETECTED", "occurred_at": datetime.now(timezone.utc).isoformat()},
        headers=INTERNAL_HEADERS,
    ).json()

    resp = client.get(f"/api/reports/events/{event['id']}.pdf", headers=auth_headers(token))
    assert resp.status_code == 200
    assert b"/DCTDecode" not in resp.content
