"""AI Video Intelligence Phase 1 tenant settings (app/api/routes/video_intelligence.py)
— same seed-on-first-use pattern as face-settings, tested the same way."""

from tests.conftest import auth_headers, login


def test_get_settings_seeds_defaults_on_first_use(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.get("/api/video-intelligence-settings", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["gate_jumping_enabled"] is True
    assert body["tailgating_enabled"] is True
    assert body["restricted_area_enabled"] is True
    assert body["pre_event_seconds"] == 30
    assert body["post_event_seconds"] == 30
    assert body["business_hours_start"] == "07:00"
    assert body["business_hours_end"] == "18:00"


def test_put_settings_updates_only_provided_fields(client, admin_user):
    token = login(client, admin_user.email)
    client.get("/api/video-intelligence-settings", headers=auth_headers(token))  # seed the row

    resp = client.put(
        "/api/video-intelligence-settings",
        json={"tailgating_enabled": False, "business_hours_start": "08:00"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tailgating_enabled"] is False
    assert body["business_hours_start"] == "08:00"
    assert body["gate_jumping_enabled"] is True  # untouched field keeps its default


def test_settings_require_manage_rules_permission(client, viewer_user):
    token = login(client, viewer_user.email)
    resp = client.get("/api/video-intelligence-settings", headers=auth_headers(token))
    # VIEWER role does not have manage_rules per ROLE_PERMISSION_MAP.
    assert resp.status_code == 403


def test_settings_are_tenant_isolated(client, db_session, admin_user, tenant, roles):
    from tests.conftest import make_user

    token = login(client, admin_user.email)
    client.put("/api/video-intelligence-settings", json={"gate_jumping_enabled": False}, headers=auth_headers(token))

    from app.models.tenant import Tenant

    other_tenant = Tenant(name="Other Co", slug="other-co")
    db_session.add(other_tenant)
    db_session.commit()
    db_session.refresh(other_tenant)
    other_admin = make_user(db_session, other_tenant, roles, "other-admin@example.com", "ADMIN")
    other_token = login(client, other_admin.email)

    resp = client.get("/api/video-intelligence-settings", headers=auth_headers(other_token))
    assert resp.status_code == 200
    assert resp.json()["gate_jumping_enabled"] is True  # a fresh, isolated settings row
