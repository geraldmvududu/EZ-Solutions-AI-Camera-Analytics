"""Event-First Cloud Storage Phase 1 (sections 3/13/14): the new per-Event review
workflow (POST /events/{id}/review, POST /events/{id}/notes) and event_category
computed at creation time from event_classification.classify_event."""

import uuid
from datetime import datetime, timezone

from app.models.event import EventCategory
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _create_event(client, camera_id, event_type="PERSON_DETECTED"):
    resp = client.post(
        "/api/events",
        json={"camera_id": camera_id, "event_type": event_type, "occurred_at": datetime.now(timezone.utc).isoformat()},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_new_event_defaults_to_unreviewed(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Lobby", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    event = _create_event(client, cam["id"])
    assert event["status"] == "UNREVIEWED"
    assert event["reviewed_by_user_id"] is None
    assert event["reviewed_at"] is None
    assert event["notes"] == ""


def test_review_event_marks_reviewed_with_user_and_timestamp(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Lobby", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    event = _create_event(client, cam["id"])

    resp = client.post(f"/api/events/{event['id']}/review", json={"status": "REVIEWED"}, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "REVIEWED"
    assert body["reviewed_by_user_id"] == str(admin_user.id)
    assert body["reviewed_at"] is not None


def test_marking_unreviewed_again_clears_reviewer_and_timestamp(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Lobby", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    event = _create_event(client, cam["id"])
    client.post(f"/api/events/{event['id']}/review", json={"status": "REVIEWED"}, headers=auth_headers(token))

    resp = client.post(f"/api/events/{event['id']}/review", json={"status": "UNREVIEWED"}, headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["reviewed_by_user_id"] is None
    assert resp.json()["reviewed_at"] is None


def test_add_event_notes(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Lobby", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    event = _create_event(client, cam["id"])

    resp = client.post(f"/api/events/{event['id']}/notes", json={"notes": "Confirmed false alarm — a cat."}, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["notes"] == "Confirmed false alarm — a cat."


def test_viewer_cannot_review_events(client, admin_user, viewer_user):
    admin_token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Lobby", "source_type": "SIMULATED"}, headers=auth_headers(admin_token)).json()
    event = _create_event(client, cam["id"])

    viewer_token = login(client, viewer_user.email)
    resp = client.post(f"/api/events/{event['id']}/review", json={"status": "REVIEWED"}, headers=auth_headers(viewer_token))
    assert resp.status_code == 403


def test_review_event_404_for_unknown_id(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.post(f"/api/events/{uuid.uuid4()}/review", json={"status": "REVIEWED"}, headers=auth_headers(token))
    assert resp.status_code == 404


def test_review_event_404_across_tenants(client, db_session, admin_user, roles):
    from app.core.security import hash_password
    from app.models.tenant import Tenant
    from app.models.user import User

    token_a = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Lobby", "source_type": "SIMULATED"}, headers=auth_headers(token_a)).json()
    event = _create_event(client, cam["id"])

    tenant_b = Tenant(name="Other Org", slug="other-org")
    db_session.add(tenant_b)
    db_session.commit()
    db_session.refresh(tenant_b)
    user_b = User(tenant_id=tenant_b.id, email="admin@other-org.lan", password_hash=hash_password("Password123!"), full_name="Other Admin", role_id=roles["ADMIN"].id)
    db_session.add(user_b)
    db_session.commit()
    db_session.refresh(user_b)
    token_b = login(client, user_b.email)

    resp = client.post(f"/api/events/{event['id']}/review", json={"status": "REVIEWED"}, headers=auth_headers(token_b))
    assert resp.status_code == 404


def test_event_category_computed_for_security_type(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    event = _create_event(client, cam["id"], event_type="TRIPWIRE_VIOLATION")
    assert event["event_category"] == EventCategory.SECURITY.value


def test_event_category_computed_for_people_type(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    event = _create_event(client, cam["id"], event_type="LOITERING_DETECTED")
    assert event["event_category"] == EventCategory.PEOPLE.value


def test_event_category_computed_for_vehicle_type(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    event = _create_event(client, cam["id"], event_type="VEHICLE_DETECTED")
    assert event["event_category"] == EventCategory.VEHICLES.value


def test_event_category_defaults_to_operations_for_unmapped_type(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    event = _create_event(client, cam["id"], event_type="CAMERA_OFFLINE")
    assert event["event_category"] == EventCategory.OPERATIONS.value


def test_list_events_filters_by_category(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    _create_event(client, cam["id"], event_type="TRIPWIRE_VIOLATION")
    _create_event(client, cam["id"], event_type="VEHICLE_DETECTED")

    resp = client.get("/api/events", params={"event_category": "SECURITY"}, headers=auth_headers(token))
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["event_type"] == "TRIPWIRE_VIOLATION"


def test_list_events_filters_by_review_status(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    reviewed = _create_event(client, cam["id"], event_type="PERSON_DETECTED")
    _create_event(client, cam["id"], event_type="VEHICLE_DETECTED")
    client.post(f"/api/events/{reviewed['id']}/review", json={"status": "REVIEWED"}, headers=auth_headers(token))

    resp = client.get("/api/events", params={"status": "REVIEWED"}, headers=auth_headers(token))
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["id"] == reviewed["id"]
