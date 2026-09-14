"""Master Development Prompt Phase 1, "Multi-event Incident Correlation" — a real gap
found by direct code read: violation_service.py::maybe_create_violation_incident always
dispatched on exactly one triggering Event, with zero logic to merge a later, related
event into an already-open incident. This is the literal mechanism behind the master
prompt's own worked examples: "person detected -> entered zone -> loitered -> object
removed" should become ONE incident, not four.

Correlation is scoped to the SAME camera + SAME tracking_id (or person_id) within
VideoIntelligenceSettings.correlation_window_seconds — deliberately narrower than
_recently_had_incident's same-camera/same-type cooldown, which stays in place
unchanged and is covered by test_video_intelligence_incidents.py."""

import uuid
from datetime import datetime, timedelta, timezone

from app.api.routes.video_intelligence import _get_or_create_settings
from app.models.incident import Incident
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _post_event(client, camera_id, event_type, tracking_id, severity="HIGH", extra=None):
    metadata = {"tracking_id": tracking_id, "confidence": 0.8, "threshold_seconds": 10}
    metadata.update(extra or {})
    return client.post(
        "/api/events",
        json={
            "camera_id": camera_id, "event_type": event_type, "severity": severity,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "event_metadata": metadata,
        },
        headers=INTERNAL_HEADERS,
    )


def test_two_different_violation_types_for_the_same_track_merge_into_one_incident(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    r1 = _post_event(client, cam["id"], "RESTRICTED_AREA_VIOLATION", tracking_id=7)
    r2 = _post_event(client, cam["id"], "GATE_JUMPING_DETECTED", tracking_id=7)
    assert r1.status_code == 201 and r2.status_code == 201

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1, "the same tracked presence triggering two different violation types must be one incident"

    incident = incidents[0]
    assert len(incident["linked_events"]) == 2
    assert "Timeline:" in incident["description"]


def test_correlation_escalates_severity_to_the_higher_of_the_two_events(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    _post_event(client, cam["id"], "RESTRICTED_AREA_VIOLATION", tracking_id=9, severity="MEDIUM")
    _post_event(client, cam["id"], "POTENTIAL_THEFT_DETECTED", tracking_id=9, severity="CRITICAL")

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1
    assert incidents[0]["severity"] == "CRITICAL"


def test_a_different_track_on_the_same_camera_does_not_correlate(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    _post_event(client, cam["id"], "RESTRICTED_AREA_VIOLATION", tracking_id=1)
    _post_event(client, cam["id"], "GATE_JUMPING_DETECTED", tracking_id=2)

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 2, "a genuinely different tracked presence must get its own incident, not be merged"


def test_correlation_past_the_window_creates_a_new_incident_instead(client, db_session, admin_user, tenant):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    vi_settings = _get_or_create_settings(db_session, tenant.id)
    vi_settings.correlation_window_seconds = 120
    db_session.commit()

    r1 = _post_event(client, cam["id"], "RESTRICTED_AREA_VIOLATION", tracking_id=3)
    assert r1.status_code == 201
    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1

    # Push the existing incident's updated_at outside the correlation window — a real
    # gap in wall-clock time between two genuinely separate occurrences of the same
    # track_id (e.g. it was reassigned to a new object after the original left frame).
    incident = db_session.get(Incident, uuid.UUID(incidents[0]["id"]))
    incident.updated_at = datetime.now(timezone.utc) - timedelta(seconds=200)
    db_session.commit()

    r2 = _post_event(client, cam["id"], "GATE_JUMPING_DETECTED", tracking_id=3)
    assert r2.status_code == 201
    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 2, "a correlation match past the window must not merge — it's effectively a new occurrence"


def test_correlation_window_zero_disables_correlation_entirely(client, db_session, admin_user, tenant):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    vi_settings = _get_or_create_settings(db_session, tenant.id)
    vi_settings.correlation_window_seconds = 0
    db_session.commit()

    _post_event(client, cam["id"], "RESTRICTED_AREA_VIOLATION", tracking_id=5)
    _post_event(client, cam["id"], "GATE_JUMPING_DETECTED", tracking_id=5)

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 2, "correlation_window_seconds=0 must disable correlation, matching cooldown_seconds=0's opt-out convention"


def test_correlation_only_attaches_to_a_still_open_incident(client, db_session, admin_user, tenant):
    """A RESOLVED/CLOSED incident is a finished case file — a later event sharing its
    tracking_id must open a fresh incident, not silently reopen and rewrite a closed one."""
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    r1 = _post_event(client, cam["id"], "RESTRICTED_AREA_VIOLATION", tracking_id=11)
    assert r1.status_code == 201
    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    incident_id = incidents[0]["id"]

    resp = client.patch(f"/api/incidents/{incident_id}", json={"status": "RESOLVED"}, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text

    r2 = _post_event(client, cam["id"], "GATE_JUMPING_DETECTED", tracking_id=11)
    assert r2.status_code == 201

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 2
    statuses = {i["id"]: i["status"] for i in incidents}
    assert statuses[incident_id] == "RESOLVED"


def test_correlation_by_person_id_when_no_tracking_id_present(client, db_session, admin_user, tenant):
    """The identified-person path (TRIPWIRE_VIOLATION/INTRUSION_DETECTED with a
    person_id) still carries tracking_id too in real ai-engine payloads, but this
    confirms the person_id fallback works standalone for whichever event never carries
    a tracking_id at all."""
    from app.models.person import Person, PersonCategory

    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Entrance", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    person = Person(tenant_id=tenant.id, first_name="Jane", last_name="Doe", category=PersonCategory.EMPLOYEE)
    db_session.add(person)
    db_session.commit()
    db_session.refresh(person)

    def _post_identified(event_type):
        return client.post(
            "/api/events",
            json={
                "camera_id": cam["id"], "event_type": event_type, "severity": "CRITICAL",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "event_metadata": {"person_id": str(person.id), "person_recognition_confidence": 0.9},
            },
            headers=INTERNAL_HEADERS,
        )

    assert _post_identified("TRIPWIRE_VIOLATION").status_code == 201
    assert _post_identified("INTRUSION_DETECTED").status_code == 201

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1, "the same identified person triggering two different violation types must be one incident"
