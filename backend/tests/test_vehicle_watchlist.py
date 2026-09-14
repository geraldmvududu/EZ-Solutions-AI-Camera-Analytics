"""Master Development Prompt Phase 1, "License Plate Reading (ANPR)" — VehicleWatchlist
CRUD, mirroring test_faces.py's/Person's own CRUD test conventions, plus tenant
isolation (mirroring test_face_tenant_isolation.py)."""

from tests.conftest import auth_headers, login
from tests.test_tenant_isolation import make_second_tenant_admin


def test_create_and_list_watchlist_entry(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.post(
        "/api/vehicles/watchlist",
        json={"plate_text": "ca 123-456", "status": "BLACKLISTED", "description": "Reported stolen"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    entry = resp.json()
    assert entry["plate_text"] == "CA123456", "plate text is normalized (stripped/uppercased) at creation time"
    assert entry["status"] == "BLACKLISTED"
    assert entry["is_active"] is True

    listed = client.get("/api/vehicles/watchlist", headers=auth_headers(token)).json()
    assert any(e["id"] == entry["id"] for e in listed)


def test_update_watchlist_entry_status(client, admin_user):
    token = login(client, admin_user.email)
    entry = client.post(
        "/api/vehicles/watchlist", json={"plate_text": "XYZ999", "status": "WATCHLIST"}, headers=auth_headers(token)
    ).json()

    resp = client.patch(
        f"/api/vehicles/watchlist/{entry['id']}", json={"status": "AUTHORIZED"}, headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "AUTHORIZED"


def test_delete_watchlist_entry(client, admin_user):
    token = login(client, admin_user.email)
    entry = client.post(
        "/api/vehicles/watchlist", json={"plate_text": "DEL123", "status": "UNAUTHORIZED"}, headers=auth_headers(token)
    ).json()

    resp = client.delete(f"/api/vehicles/watchlist/{entry['id']}", headers=auth_headers(token))
    assert resp.status_code == 204

    listed = client.get("/api/vehicles/watchlist", headers=auth_headers(token)).json()
    assert not any(e["id"] == entry["id"] for e in listed)


def test_viewer_cannot_manage_watchlist(client, viewer_user):
    token = login(client, viewer_user.email)
    resp = client.post(
        "/api/vehicles/watchlist", json={"plate_text": "ABC111", "status": "WATCHLIST"}, headers=auth_headers(token)
    )
    assert resp.status_code == 403


def test_tenant_b_cannot_see_or_modify_tenant_a_watchlist_entry(client, db_session, admin_user, roles):
    token_a = login(client, admin_user.email)
    entry = client.post(
        "/api/vehicles/watchlist", json={"plate_text": "TENANTA1", "status": "BLACKLISTED"}, headers=auth_headers(token_a)
    ).json()

    _tenant_b, user_b = make_second_tenant_admin(db_session, roles)
    token_b = login(client, user_b.email)

    resp = client.patch(
        f"/api/vehicles/watchlist/{entry['id']}", json={"status": "AUTHORIZED"}, headers=auth_headers(token_b)
    )
    assert resp.status_code == 404

    listed = client.get("/api/vehicles/watchlist", headers=auth_headers(token_b)).json()
    assert listed == []
