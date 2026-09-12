"""Facial Recognition + tripwire/zone violation correlation (spec section 9): a
TRIPWIRE_VIOLATION/INTRUSION_DETECTED event carrying a recognized person_id in its
metadata (attached by ai-engine's worker.py::_identity_metadata, from
FaceRecognizer.identity_for) auto-creates a real, linked Incident — the "file you can
open" for that violation. See app/services/violation_service.py."""

from app.models.incident import Incident
from app.models.person import Person, PersonCategory
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _make_person(db_session, tenant) -> Person:
    person = Person(tenant_id=tenant.id, first_name="Jane", last_name="Doe", category=PersonCategory.EMPLOYEE)
    db_session.add(person)
    db_session.commit()
    db_session.refresh(person)
    return person


def test_tripwire_violation_by_recognized_person_creates_incident(client, db_session, admin_user, tenant):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    person = _make_person(db_session, tenant)

    resp = client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "TRIPWIRE_VIOLATION", "severity": "HIGH",
            "occurred_at": "2026-01-01T12:00:00Z",
            "event_metadata": {"direction": "ENTERING", "tracking_id": 1, "person_id": str(person.id), "person_recognition_confidence": 0.94},
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201, resp.text

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1
    incident = incidents[0]
    assert "Jane Doe" in incident["title"]
    assert cam["id"] == incident["camera_id"]
    assert incident["status"] == "OPEN"
    assert incident["severity"] == "CRITICAL"
    assert "Jane Doe" in incident["description"]
    assert "94%" in incident["description"]


def test_intrusion_by_recognized_person_creates_incident(client, db_session, admin_user, tenant):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Server Room", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    person = _make_person(db_session, tenant)

    resp = client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "INTRUSION_DETECTED", "severity": "CRITICAL",
            "occurred_at": "2026-01-01T12:00:00Z",
            "event_metadata": {"tracking_id": 2, "person_id": str(person.id)},
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1
    assert "restricted zone" in incidents[0]["description"]


def test_no_incident_when_person_not_recognized(client, admin_user):
    """A violation by someone NOT identified (facial recognition off, or genuinely
    unrecognized) still creates a real Event/Alert as normal — it just doesn't get an
    auto-opened Incident, since there's no identity to correlate."""
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "TRIPWIRE_VIOLATION", "severity": "HIGH",
            "occurred_at": "2026-01-01T12:00:00Z", "event_metadata": {"direction": "ENTERING", "tracking_id": 3},
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201
    assert client.get("/api/incidents", headers=auth_headers(token)).json() == []


def test_no_incident_for_non_violation_event_type_even_with_person_id(client, db_session, admin_user, tenant):
    """A plain PERSON_DETECTED/FACE_RECOGNIZED event is not itself a "violation" —
    only an actual boundary-crossing event type triggers an auto-incident."""
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Lobby", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    person = _make_person(db_session, tenant)

    resp = client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "FACE_RECOGNIZED", "severity": "INFO",
            "occurred_at": "2026-01-01T12:00:00Z", "event_metadata": {"person_id": str(person.id)},
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201
    assert client.get("/api/incidents", headers=auth_headers(token)).json() == []


def test_incident_links_the_alert_created_from_the_same_event(client, db_session, admin_user, tenant):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    person = _make_person(db_session, tenant)
    client.post(
        "/api/rules",
        json={"name": "Tripwire rule", "conditions": {"event_type": "TRIPWIRE_VIOLATION"}, "action_severity": "HIGH", "action_alert_type": "TRIPWIRE_MATCH"},
        headers=auth_headers(token),
    )

    client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "TRIPWIRE_VIOLATION", "severity": "HIGH",
            "occurred_at": "2026-01-01T12:00:00Z",
            "event_metadata": {"tracking_id": 1, "person_id": str(person.id)},
        },
        headers=INTERNAL_HEADERS,
    )

    incident_row = db_session.query(Incident).one()
    assert len(incident_row.related_alerts) == 1
    assert incident_row.related_alerts[0].alert_type == "TRIPWIRE_MATCH"
