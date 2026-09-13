"""Event-First Cloud Storage Phase 1 (section 10): RetentionTier CRUD + the
SUPER_ADMIN-only gate on editing/assigning tiers. Tiers are normally seeded by the
Alembic migration (not by Base.metadata.create_all, which only builds schema), so
these tests seed rows directly via db_session — mirroring how other test files here
build real dependent rows rather than relying on migration-time data."""

import uuid

from app.models.retention_tier import RetentionTier
from app.models.tenant import Tenant
from tests.conftest import auth_headers, login, make_user


def _seed_tier(db_session, name="starter", event_days=90, snapshot_days=30, video_days=90) -> RetentionTier:
    tier = RetentionTier(name=name, event_metadata_days=event_days, snapshot_days=snapshot_days, video_evidence_days=video_days)
    db_session.add(tier)
    db_session.commit()
    db_session.refresh(tier)
    return tier


def _make_super_admin(db_session, admin_user, roles):
    tenant = db_session.get(Tenant, admin_user.tenant_id)
    return make_user(db_session, tenant, roles, "super@ezsolutions.lan", "SUPER_ADMIN")


def test_list_retention_tiers_is_visible_to_any_authenticated_user(client, db_session, admin_user, viewer_user):
    _seed_tier(db_session, name="starter", event_days=90)
    _seed_tier(db_session, name="enterprise", event_days=730)

    token = login(client, viewer_user.email)
    resp = client.get("/api/retention-tiers", headers=auth_headers(token))
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert names == ["starter", "enterprise"]  # ordered by event_metadata_days ascending


def test_get_my_retention_tier_404s_when_tenant_has_none_assigned(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.get("/api/retention-tiers/mine", headers=auth_headers(token))
    assert resp.status_code == 404


def test_get_my_retention_tier_returns_assigned_tier(client, db_session, admin_user):
    tier = _seed_tier(db_session, name="business", event_days=180)
    tenant = db_session.get(Tenant, admin_user.tenant_id)
    tenant.retention_tier_id = tier.id
    db_session.commit()

    token = login(client, admin_user.email)
    resp = client.get("/api/retention-tiers/mine", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["name"] == "business"


def test_update_retention_tier_requires_super_admin(client, db_session, admin_user, roles):
    tier = _seed_tier(db_session)
    token = login(client, admin_user.email)  # ADMIN, not SUPER_ADMIN

    resp = client.put(f"/api/retention-tiers/{tier.id}", json={"snapshot_days": 60}, headers=auth_headers(token))
    assert resp.status_code == 403


def test_super_admin_can_update_retention_tier(client, db_session, admin_user, roles):
    tier = _seed_tier(db_session, snapshot_days=30)
    super_admin = _make_super_admin(db_session, admin_user, roles)
    token = login(client, super_admin.email)

    resp = client.put(f"/api/retention-tiers/{tier.id}", json={"snapshot_days": 60}, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["snapshot_days"] == 60


def test_update_retention_tier_404_for_unknown_id(client, db_session, admin_user, roles):
    super_admin = _make_super_admin(db_session, admin_user, roles)
    token = login(client, super_admin.email)

    resp = client.put(f"/api/retention-tiers/{uuid.uuid4()}", json={"snapshot_days": 60}, headers=auth_headers(token))
    assert resp.status_code == 404


def test_assign_tenant_retention_tier_requires_super_admin(client, db_session, admin_user, roles):
    tier = _seed_tier(db_session)
    token = login(client, admin_user.email)

    resp = client.put(f"/api/retention-tiers/assign/{admin_user.tenant_id}", json={"retention_tier_id": str(tier.id)}, headers=auth_headers(token))
    assert resp.status_code == 403


def test_super_admin_can_assign_tenant_retention_tier(client, db_session, admin_user, roles):
    tier = _seed_tier(db_session, name="professional")
    super_admin = _make_super_admin(db_session, admin_user, roles)
    token = login(client, super_admin.email)

    resp = client.put(f"/api/retention-tiers/assign/{admin_user.tenant_id}", json={"retention_tier_id": str(tier.id)}, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "professional"

    tenant = db_session.get(Tenant, admin_user.tenant_id)
    assert tenant.retention_tier_id == tier.id
