from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User
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


def test_tenant_b_cannot_see_tenant_a_camera(client, db_session, admin_user, roles):
    token_a = login(client, admin_user.email)
    camera = client.post(
        "/api/cameras", json={"name": "Tenant A Cam", "source_type": "SIMULATED"}, headers=auth_headers(token_a)
    ).json()

    _tenant_b, user_b = make_second_tenant_admin(db_session, roles)
    token_b = login(client, user_b.email)

    # Object-level authorization: changing the ID in the URL must not leak cross-tenant data.
    resp = client.get(f"/api/cameras/{camera['id']}", headers=auth_headers(token_b))
    assert resp.status_code == 404

    list_resp = client.get("/api/cameras", headers=auth_headers(token_b))
    assert list_resp.status_code == 200
    assert list_resp.json() == []


def test_tenant_b_cannot_modify_tenant_a_camera(client, db_session, admin_user, roles):
    token_a = login(client, admin_user.email)
    camera = client.post(
        "/api/cameras", json={"name": "Tenant A Cam", "source_type": "SIMULATED"}, headers=auth_headers(token_a)
    ).json()

    _tenant_b, user_b = make_second_tenant_admin(db_session, roles)
    token_b = login(client, user_b.email)

    resp = client.patch(
        f"/api/cameras/{camera['id']}", json={"name": "Pwned"}, headers=auth_headers(token_b)
    )
    assert resp.status_code == 404
