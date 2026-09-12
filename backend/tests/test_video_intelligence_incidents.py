"""AI Video Intelligence Phase 1: GATE_JUMPING_DETECTED/TAILGATING_DETECTED/
RESTRICTED_AREA_VIOLATION always create a real Incident (unlike the identified-person-
only path in test_violation_incidents.py) since these event types only fire once the
zone/tripwire logic has already decided a violation occurred — identity is an optional
enrichment ("Unknown Person" when absent), not a gate. See app/services/
violation_service.py."""

from datetime import datetime, timezone

from app.models.event import EventSeverity
from app.models.incident import Incident
from app.models.person import Person, PersonCategory
from app.services.violation_service import compute_risk_score
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _make_person(db_session, tenant) -> Person:
    person = Person(tenant_id=tenant.id, first_name="Jane", last_name="Doe", category=PersonCategory.EMPLOYEE)
    db_session.add(person)
    db_session.commit()
    db_session.refresh(person)
    return person


def test_gate_jumping_creates_incident_without_a_recognized_person(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "GATE_JUMPING_DETECTED", "severity": "HIGH",
            "occurred_at": "2026-01-01T12:00:00Z",
            "event_metadata": {"direction": "ENTERING", "tracking_id": 1, "confidence": 0.82},
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201, resp.text

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1
    incident = incidents[0]
    assert "Unknown Person" in incident["title"]
    assert incident["incident_type"] == "GATE_JUMPING_DETECTED"
    assert incident["requires_human_review"] is True
    assert incident["confidence"] == 0.82
    assert incident["risk_score"] is not None
    assert "climbing or jumping" in incident["description"]
    assert "Unknown Person" in incident["description"]


def test_tailgating_creates_incident_with_a_recognized_person(client, db_session, admin_user, tenant):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Main Entrance", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    person = _make_person(db_session, tenant)

    resp = client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "TAILGATING_DETECTED", "severity": "MEDIUM",
            "occurred_at": "2026-01-01T12:00:00Z",
            "event_metadata": {"tracking_id": 2, "leading_tracking_id": 1, "window_seconds": 5, "person_id": str(person.id), "person_recognition_confidence": 0.9},
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1
    incident = incidents[0]
    assert "Jane Doe" in incident["title"]
    assert incident["incident_type"] == "TAILGATING_DETECTED"
    assert "Jane Doe" in incident["description"]
    assert "no access-control-system integration" in incident["description"]


def test_restricted_area_violation_creates_incident(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Server Room", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "RESTRICTED_AREA_VIOLATION", "severity": "HIGH",
            "occurred_at": "2026-01-01T12:00:00Z",
            "event_metadata": {"tracking_id": 3, "threshold_seconds": 10},
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == "RESTRICTED_AREA_VIOLATION"
    assert "at least 10 seconds" in incidents[0]["description"]


def test_compute_risk_score_severity_base():
    business_start, business_end = "07:00", "18:00"
    noon = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert compute_risk_score(EventSeverity.CRITICAL, noon, business_start, business_end, False) == 40
    assert compute_risk_score(EventSeverity.HIGH, noon, business_start, business_end, False) == 30
    assert compute_risk_score(EventSeverity.MEDIUM, noon, business_start, business_end, False) == 15
    assert compute_risk_score(EventSeverity.LOW, noon, business_start, business_end, False) == 5


def test_compute_risk_score_after_hours_bonus():
    business_start, business_end = "07:00", "18:00"
    midnight = datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc)
    noon = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert compute_risk_score(EventSeverity.HIGH, midnight, business_start, business_end, False) == 30 + 20
    assert compute_risk_score(EventSeverity.HIGH, noon, business_start, business_end, False) == 30


def test_compute_risk_score_identified_person_bonus():
    business_start, business_end = "07:00", "18:00"
    noon = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert compute_risk_score(EventSeverity.HIGH, noon, business_start, business_end, True) == 30 + 15


def test_compute_risk_score_worst_case_combination_stays_within_0_to_100():
    business_start, business_end = "07:00", "18:00"
    midnight = datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc)
    score = compute_risk_score(EventSeverity.CRITICAL, midnight, business_start, business_end, True)
    assert score == 75  # 40 (CRITICAL) + 20 (after-hours) + 15 (identified person)
    assert 0 <= score <= 100
