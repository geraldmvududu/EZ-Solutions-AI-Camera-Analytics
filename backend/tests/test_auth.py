from tests.conftest import auth_headers, login


def test_login_success(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.get("/api/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == admin_user.email
    assert body["role"] == "ADMIN"
    assert "manage_cameras" in body["permissions"]


def test_login_wrong_password_rejected(client, admin_user):
    resp = client.post("/api/auth/login", json={"email": admin_user.email, "password": "wrong-password"})
    assert resp.status_code == 401


def test_login_unknown_user_rejected(client):
    resp = client.post("/api/auth/login", json={"email": "nobody@ezsolutions.lan", "password": "whatever"})
    assert resp.status_code == 401


def test_disabled_account_rejected(client, db_session, admin_user):
    admin_user.is_active = False
    db_session.commit()
    resp = client.post("/api/auth/login", json={"email": admin_user.email, "password": "Password123!"})
    assert resp.status_code == 403


def test_protected_endpoint_requires_token(client):
    resp = client.get("/api/cameras")
    assert resp.status_code == 401


def test_invalid_token_rejected(client):
    resp = client.get("/api/cameras", headers=auth_headers("not-a-real-token"))
    assert resp.status_code == 401


def test_refresh_token_flow(client, admin_user):
    login_resp = client.post("/api/auth/login", json={"email": admin_user.email, "password": "Password123!"})
    refresh_token = login_resp.json()["refresh_token"]

    refresh_resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200
    new_access = refresh_resp.json()["access_token"]

    me_resp = client.get("/api/auth/me", headers=auth_headers(new_access))
    assert me_resp.status_code == 200

    # The old refresh token should now be revoked (rotation).
    reuse_resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_resp.status_code == 401


def test_password_never_stored_in_plaintext(db_session, admin_user):
    assert admin_user.password_hash != "Password123!"
    assert admin_user.password_hash.startswith("$2b$")
