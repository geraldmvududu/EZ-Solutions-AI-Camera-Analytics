"""AIRule CRUD (app/api/routes/rules.py). test_delete_rule_that_already_matched_a_real_event
covers a real bug found live on the deployed VM: deleting a rule that had already
matched a real event and created a real Alert raised an unhandled
alerts_rule_id_fkey ForeignKeyViolation — SQLite (used by every other test in this
suite) never enforces that FK, so this needs a real dependent Alert row built
directly, the same convention test_camera_delete_cascade.py already established."""

import uuid
from datetime import datetime, timezone

from app.models.alert import Alert
from app.models.event import Event, EventSeverity, EventType
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def test_create_and_update_rule(client, admin_user):
    token = login(client, admin_user.email)
    rule = client.post(
        "/api/rules",
        json={"name": "Motion Rule", "conditions": {"event_type": "MOTION_DETECTED"}, "action_severity": "HIGH", "action_alert_type": "MOTION_DETECTED"},
        headers=auth_headers(token),
    ).json()
    assert rule["name"] == "Motion Rule"
    assert rule["is_enabled"] is True

    resp = client.patch(f"/api/rules/{rule['id']}", json={"name": "Renamed Rule", "is_enabled": False}, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Renamed Rule"
    assert resp.json()["is_enabled"] is False


def test_delete_rule_with_no_alerts(client, admin_user):
    token = login(client, admin_user.email)
    rule = client.post(
        "/api/rules",
        json={"name": "Unused Rule", "conditions": {"event_type": "MOTION_DETECTED"}, "action_severity": "LOW", "action_alert_type": "MOTION_DETECTED"},
        headers=auth_headers(token),
    ).json()

    resp = client.delete(f"/api/rules/{rule['id']}", headers=auth_headers(token))
    assert resp.status_code == 204


def test_delete_rule_that_already_matched_a_real_event(client, db_session, tenant, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    rule = client.post(
        "/api/rules",
        json={"name": "Motion Rule", "conditions": {"event_type": "MOTION_DETECTED"}, "action_severity": "HIGH", "action_alert_type": "MOTION_DETECTED", "camera_id": cam["id"]},
        headers=auth_headers(token),
    ).json()

    camera_id = uuid.UUID(cam["id"])
    event = Event(
        tenant_id=tenant.id, camera_id=camera_id, event_type=EventType.MOTION_DETECTED,
        severity=EventSeverity.HIGH, occurred_at=datetime.now(timezone.utc), event_metadata={},
    )
    db_session.add(event)
    db_session.commit()
    alert = Alert(tenant_id=tenant.id, event_id=event.id, camera_id=camera_id, rule_id=uuid.UUID(rule["id"]), alert_type="MOTION_DETECTED", severity=EventSeverity.HIGH)
    db_session.add(alert)
    db_session.commit()
    alert_id = alert.id

    resp = client.delete(f"/api/rules/{rule['id']}", headers=auth_headers(token))
    assert resp.status_code == 204, resp.text

    db_session.expire_all()
    # The alert survives, unscoped from the deleted rule — its own history/evidence
    # outlives the rule config that happened to generate it.
    surviving_alert = db_session.get(Alert, alert_id)
    assert surviving_alert is not None
    assert surviving_alert.rule_id is None


def test_delete_rule_tenant_isolation(client, db_session, admin_user, roles):
    from app.core.security import hash_password
    from app.models.tenant import Tenant
    from app.models.user import User

    token_a = login(client, admin_user.email)
    rule = client.post(
        "/api/rules",
        json={"name": "Tenant A Rule", "conditions": {"event_type": "MOTION_DETECTED"}, "action_severity": "LOW", "action_alert_type": "MOTION_DETECTED"},
        headers=auth_headers(token_a),
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

    resp = client.delete(f"/api/rules/{rule['id']}", headers=auth_headers(token_b))
    assert resp.status_code == 404
