"""AI Video Intelligence Phase 1: GATE_JUMPING_DETECTED/TAILGATING_DETECTED/
RESTRICTED_AREA_VIOLATION always create a real Incident (unlike the identified-person-
only path in test_violation_incidents.py) since these event types only fire once the
zone/tripwire logic has already decided a violation occurred — identity is an optional
enrichment ("Unknown Person" when absent), not a gate. See app/services/
violation_service.py."""

import uuid
from datetime import datetime, timedelta, timezone

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


def test_gate_jumping_cooldown_suppresses_a_second_incident_within_the_window(client, db_session, admin_user, tenant):
    """Real bug found live on the deployed VM: the always-incident dispatch had no
    cooldown of its own — a looping test video replaying the same gate-jump content
    every loop pass created a new Incident every time, indefinitely."""
    from app.api.routes.video_intelligence import _get_or_create_settings

    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    settings = _get_or_create_settings(db_session, tenant.id)
    settings.incident_cooldown_seconds = 300
    db_session.commit()

    def _post_gate_jump():
        return client.post(
            "/api/events",
            json={
                "camera_id": cam["id"], "event_type": "GATE_JUMPING_DETECTED", "severity": "HIGH",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "event_metadata": {"direction": "ENTERING", "tracking_id": 1, "confidence": 0.82},
            },
            headers=INTERNAL_HEADERS,
        )

    assert _post_gate_jump().status_code == 201
    assert _post_gate_jump().status_code == 201  # the EVENT still gets created either way

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1, "a second gate-jump within the cooldown window must not create a second incident"


def test_gate_jumping_cooldown_allows_a_new_incident_after_the_window_expires(client, db_session, admin_user, tenant):
    from app.api.routes.video_intelligence import _get_or_create_settings

    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    settings = _get_or_create_settings(db_session, tenant.id)
    settings.incident_cooldown_seconds = 300
    db_session.commit()

    def _post_gate_jump():
        return client.post(
            "/api/events",
            json={
                "camera_id": cam["id"], "event_type": "GATE_JUMPING_DETECTED", "severity": "HIGH",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "event_metadata": {"direction": "ENTERING", "tracking_id": 1, "confidence": 0.82},
            },
            headers=INTERNAL_HEADERS,
        )

    assert _post_gate_jump().status_code == 201
    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1
    # Backdate the existing incident past the cooldown window — a real gap in
    # wall-clock time between two real incidents.
    incident = db_session.get(Incident, uuid.UUID(incidents[0]["id"]))
    incident.created_at = datetime.now(timezone.utc) - timedelta(seconds=301)
    db_session.commit()

    assert _post_gate_jump().status_code == 201
    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 2, "a genuinely new gate-jump after the cooldown has elapsed must still create an incident"


def test_gate_jumping_cooldown_zero_disables_throttling(client, db_session, admin_user, tenant):
    from app.api.routes.video_intelligence import _get_or_create_settings

    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    settings = _get_or_create_settings(db_session, tenant.id)
    settings.incident_cooldown_seconds = 0
    db_session.commit()

    def _post_gate_jump():
        return client.post(
            "/api/events",
            json={
                "camera_id": cam["id"], "event_type": "GATE_JUMPING_DETECTED", "severity": "HIGH",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "event_metadata": {"direction": "ENTERING", "tracking_id": 1, "confidence": 0.82},
            },
            headers=INTERNAL_HEADERS,
        )

    assert _post_gate_jump().status_code == 201
    assert _post_gate_jump().status_code == 201

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 2


def test_incident_cooldown_is_scoped_per_incident_type(client, db_session, admin_user, tenant):
    """A genuinely different incident TYPE on the same camera (e.g. restricted-area
    right after a gate-jump) must not be suppressed by the other's recent incident."""
    from app.api.routes.video_intelligence import _get_or_create_settings

    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    settings = _get_or_create_settings(db_session, tenant.id)
    settings.incident_cooldown_seconds = 300
    db_session.commit()

    def _post(event_type):
        return client.post(
            "/api/events",
            json={
                "camera_id": cam["id"], "event_type": event_type, "severity": "HIGH",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "event_metadata": {"tracking_id": 1, "confidence": 0.82, "threshold_seconds": 10},
            },
            headers=INTERNAL_HEADERS,
        )

    assert _post("GATE_JUMPING_DETECTED").status_code == 201
    assert _post("RESTRICTED_AREA_VIOLATION").status_code == 201

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 2


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


def test_potential_theft_creates_incident_without_a_recognized_person(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Display Case", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "POTENTIAL_THEFT_DETECTED", "severity": "HIGH",
            "occurred_at": "2026-01-01T12:00:00Z",
            "event_metadata": {"object_type": "BACKPACK", "tracking_id": 1, "threshold_seconds": 10},
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201, resp.text

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1
    incident = incidents[0]
    assert "Unknown Person" in incident["title"]
    assert incident["incident_type"] == "POTENTIAL_THEFT_DETECTED"
    assert incident["requires_human_review"] is True
    assert incident["risk_score"] is not None
    assert "backpack" in incident["description"]
    assert "at least 10 seconds" in incident["description"]
    assert "not a trained theft-behavior classifier" in incident["description"]
    assert "Unknown Person" in incident["description"]


def test_potential_theft_creates_incident_with_a_recognized_nearby_person(client, db_session, admin_user, tenant):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Display Case", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    person = _make_person(db_session, tenant)

    resp = client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "POTENTIAL_THEFT_DETECTED", "severity": "HIGH",
            "occurred_at": "2026-01-01T12:00:00Z",
            "event_metadata": {
                "object_type": "SUITCASE", "tracking_id": 2, "threshold_seconds": 15,
                "person_id": str(person.id), "person_recognition_confidence": 0.88,
            },
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1
    incident = incidents[0]
    assert "Jane Doe" in incident["title"]
    assert incident["incident_type"] == "POTENTIAL_THEFT_DETECTED"
    assert "Jane Doe" in incident["description"]
    assert "suitcase" in incident["description"]


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
