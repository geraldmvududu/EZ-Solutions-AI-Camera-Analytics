"""POST /api/vehicles/recognize-plate — Master Development Prompt Phase 1, "License
Plate Reading (ANPR)". Mirrors test_violation_incidents.py's pattern for the
always-incident dispatch, plus a real, hand-verified severity mapping
(BLACKLISTED -> CRITICAL, WATCHLIST -> HIGH)."""

from datetime import datetime, timezone

from tests.conftest import auth_headers, login
from tests.test_tenant_isolation import make_second_tenant_admin

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _recognize(client, camera_id, plate_text, extra=None):
    payload = {
        "camera_id": camera_id,
        "tracking_id": 1,
        "plate_text": plate_text,
        "vehicle_type": "CAR",
        "confidence": 0.85,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(extra or {})
    return client.post("/api/vehicles/recognize-plate", json=payload, headers=INTERNAL_HEADERS)


def test_unknown_plate_creates_a_plain_sighting_and_no_incident(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate Cam", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = _recognize(client, cam["id"], "UNKNOWN99")
    assert resp.status_code == 200, resp.text
    assert resp.json()["watchlist_status"] is None

    events = client.get(f"/api/events?camera_id={cam['id']}", headers=auth_headers(token)).json()
    plate_events = [e for e in events if e["event_type"] == "LICENSE_PLATE_DETECTED"]
    assert len(plate_events) == 1
    assert not [e for e in events if e["event_type"] == "VEHICLE_WATCHLIST_MATCH"]

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert incidents == []

    plate_log = client.get(f"/api/vehicles/plate-events?camera_id={cam['id']}", headers=auth_headers(token)).json()
    assert len(plate_log) == 1
    assert plate_log[0]["plate_text"] == "UNKNOWN99"


def test_blacklisted_plate_creates_a_critical_incident(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate Cam", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    client.post("/api/vehicles/watchlist", json={"plate_text": "CA123456", "status": "BLACKLISTED"}, headers=auth_headers(token))

    resp = _recognize(client, cam["id"], "ca 123-456")  # same plate, different formatting
    assert resp.status_code == 200, resp.text
    assert resp.json()["watchlist_status"] == "BLACKLISTED"

    events = client.get(f"/api/events?camera_id={cam['id']}", headers=auth_headers(token)).json()
    match_events = [e for e in events if e["event_type"] == "VEHICLE_WATCHLIST_MATCH"]
    assert len(match_events) == 1
    assert match_events[0]["severity"] == "CRITICAL"

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1
    assert incidents[0]["severity"] == "CRITICAL"
    assert incidents[0]["incident_type"] == "VEHICLE_WATCHLIST_MATCH"
    assert incidents[0]["requires_human_review"] is True
    assert "CA123456" in incidents[0]["description"]


def test_watchlist_status_creates_a_high_severity_incident(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate Cam", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    client.post("/api/vehicles/watchlist", json={"plate_text": "WATCH001", "status": "WATCHLIST"}, headers=auth_headers(token))

    resp = _recognize(client, cam["id"], "WATCH001")
    assert resp.json()["watchlist_status"] == "WATCHLIST"

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert len(incidents) == 1
    assert incidents[0]["severity"] == "HIGH"


def test_authorized_plate_does_not_create_an_incident(client, admin_user):
    """AUTHORIZED is a real, deliberate status — a plain sighting log entry, never an
    alert-worthy incident, unlike WATCHLIST/BLACKLISTED."""
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate Cam", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    client.post("/api/vehicles/watchlist", json={"plate_text": "STAFF001", "status": "AUTHORIZED"}, headers=auth_headers(token))

    resp = _recognize(client, cam["id"], "STAFF001")
    assert resp.json()["watchlist_status"] == "AUTHORIZED"

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert incidents == []


def test_inactive_watchlist_entry_is_never_matched(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate Cam", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    entry = client.post(
        "/api/vehicles/watchlist", json={"plate_text": "OLD9999", "status": "BLACKLISTED"}, headers=auth_headers(token)
    ).json()
    client.patch(f"/api/vehicles/watchlist/{entry['id']}", json={"is_active": False}, headers=auth_headers(token))

    resp = _recognize(client, cam["id"], "OLD9999")
    assert resp.json()["watchlist_status"] is None

    incidents = client.get("/api/incidents", headers=auth_headers(token)).json()
    assert incidents == []


def test_recognize_plate_requires_internal_token(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate Cam", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = client.post(
        "/api/vehicles/recognize-plate",
        json={
            "camera_id": cam["id"], "tracking_id": 1, "plate_text": "X", "vehicle_type": "CAR",
            "confidence": 0.5, "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
        headers=auth_headers(token),
    )
    assert resp.status_code in (401, 403)


def test_tenant_b_cannot_see_tenant_a_plate_sightings(client, db_session, admin_user, roles):
    token_a = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Gate Cam", "source_type": "SIMULATED"}, headers=auth_headers(token_a)).json()
    _recognize(client, cam["id"], "TENANTA1")

    _tenant_b, user_b = make_second_tenant_admin(db_session, roles)
    token_b = login(client, user_b.email)

    plate_log = client.get("/api/vehicles/plate-events", headers=auth_headers(token_b)).json()
    assert plate_log == []
