"""Event-First Cloud Storage Phase 1 (section 1): Site CRUD + tenant isolation, and a
camera's site_id round-tripping through the Cameras API — following
test_tenant_isolation.py's real-two-tenants convention (a 404, not empty data, is what
actually happens against the live route code)."""

from app.models.tenant import Tenant
from app.models.user import User
from app.core.security import hash_password
from tests.conftest import auth_headers, login


def make_second_tenant_admin(db_session, roles):
    tenant_b = Tenant(name="Other Org", slug="other-org")
    db_session.add(tenant_b)
    db_session.commit()
    db_session.refresh(tenant_b)

    user = User(
        tenant_id=tenant_b.id,
        email="admin@other-org.lan",
        password_hash=hash_password("Password123!"),
        full_name="Other Admin",
        role_id=roles["ADMIN"].id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return tenant_b, user


def test_create_site(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.post("/api/sites", json={"name": "Downtown Warehouse", "address": "1 Main St", "timezone": "America/New_York"}, headers=auth_headers(token))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Downtown Warehouse"
    assert body["address"] == "1 Main St"
    assert body["timezone"] == "America/New_York"
    assert body["is_active"] is True
    assert body["tenant_id"] == str(admin_user.tenant_id)


def test_create_site_defaults_timezone_to_utc(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.post("/api/sites", json={"name": "Minimal Site"}, headers=auth_headers(token))
    assert resp.status_code == 201, resp.text
    assert resp.json()["timezone"] == "UTC"


def test_list_sites_only_returns_own_tenant(client, db_session, admin_user, roles):
    token_a = login(client, admin_user.email)
    client.post("/api/sites", json={"name": "Tenant A Site"}, headers=auth_headers(token_a))

    _tenant_b, user_b = make_second_tenant_admin(db_session, roles)
    token_b = login(client, user_b.email)
    resp_b = client.get("/api/sites", headers=auth_headers(token_b))
    assert resp_b.status_code == 200
    assert resp_b.json() == []

    resp_a = client.get("/api/sites", headers=auth_headers(token_a))
    assert len(resp_a.json()) == 1
    assert resp_a.json()[0]["name"] == "Tenant A Site"


def test_update_site(client, admin_user):
    token = login(client, admin_user.email)
    site = client.post("/api/sites", json={"name": "Old Name"}, headers=auth_headers(token)).json()

    resp = client.patch(f"/api/sites/{site['id']}", json={"name": "New Name", "is_active": False}, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "New Name"
    assert resp.json()["is_active"] is False


def test_tenant_b_cannot_update_tenant_a_site(client, db_session, admin_user, roles):
    token_a = login(client, admin_user.email)
    site = client.post("/api/sites", json={"name": "Tenant A Site"}, headers=auth_headers(token_a)).json()

    _tenant_b, user_b = make_second_tenant_admin(db_session, roles)
    token_b = login(client, user_b.email)

    resp = client.patch(f"/api/sites/{site['id']}", json={"name": "Pwned"}, headers=auth_headers(token_b))
    assert resp.status_code == 404


def test_tenant_b_cannot_see_tenant_a_site(client, db_session, admin_user, roles):
    token_a = login(client, admin_user.email)
    site = client.post("/api/sites", json={"name": "Tenant A Site"}, headers=auth_headers(token_a)).json()

    _tenant_b, user_b = make_second_tenant_admin(db_session, roles)
    token_b = login(client, user_b.email)

    resp = client.get("/api/sites", headers=auth_headers(token_b))
    assert resp.json() == []
    # confirms it's a 404, not a silent cross-tenant leak, if a client guesses the ID
    resp2 = client.patch(f"/api/sites/{site['id']}", json={}, headers=auth_headers(token_b))
    assert resp2.status_code == 404


def test_delete_site_unassigns_cameras_instead_of_deleting_them(client, admin_user):
    token = login(client, admin_user.email)
    site = client.post("/api/sites", json={"name": "To Delete"}, headers=auth_headers(token)).json()
    cam = client.post("/api/cameras", json={"name": "Cam 1", "source_type": "SIMULATED", "site_id": site["id"]}, headers=auth_headers(token)).json()
    assert cam["site_id"] == site["id"]

    resp = client.delete(f"/api/sites/{site['id']}", headers=auth_headers(token))
    assert resp.status_code == 204

    cam_after = client.get(f"/api/cameras/{cam['id']}", headers=auth_headers(token)).json()
    assert cam_after["site_id"] is None
    assert client.get("/api/sites", headers=auth_headers(token)).json() == []


def test_viewer_can_list_sites_but_not_create(client, admin_user, viewer_user):
    admin_token = login(client, admin_user.email)
    client.post("/api/sites", json={"name": "Visible To Viewer"}, headers=auth_headers(admin_token))

    viewer_token = login(client, viewer_user.email)
    list_resp = client.get("/api/sites", headers=auth_headers(viewer_token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    create_resp = client.post("/api/sites", json={"name": "Nope"}, headers=auth_headers(viewer_token))
    assert create_resp.status_code == 403


def test_camera_create_persists_site_id(client, admin_user):
    token = login(client, admin_user.email)
    site = client.post("/api/sites", json={"name": "Branch Office"}, headers=auth_headers(token)).json()

    cam = client.post(
        "/api/cameras",
        json={"name": "Lobby Cam", "source_type": "SIMULATED", "site_id": site["id"], "cloud_recording_enabled": True},
        headers=auth_headers(token),
    ).json()
    assert cam["site_id"] == site["id"]
    assert cam["cloud_recording_enabled"] is True


def test_camera_without_site_id_defaults_to_none(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "No Site Cam", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    assert cam["site_id"] is None
    assert cam["cloud_recording_enabled"] is False
