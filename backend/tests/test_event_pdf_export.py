"""GET /api/reports/events/{id}.pdf — a per-event PDF export, requested after a user
reported no way to get a shareable record of a single event's full detail (the
existing security-report.pdf is a tenant-wide aggregate, not a per-event document)."""

import uuid
from datetime import datetime, timezone

from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


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
