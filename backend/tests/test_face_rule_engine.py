"""Direct unit tests for the person_category/person_status conditions added to
rule_engine._rule_matches for the Facial Recognition module (section 8). Complements
test_face_matching.py's end-to-end HTTP-level coverage of the same mechanism."""

from datetime import datetime, timezone

from app.models.camera import Camera, CameraSourceType
from app.models.event import Event, EventSeverity, EventType
from app.models.rule import AIRule
from app.services import rule_engine


def _make_camera(db_session, tenant):
    camera = Camera(tenant_id=tenant.id, camera_code="CAM-001", name="Front Gate", source_type=CameraSourceType.SIMULATED)
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)
    return camera


def _make_face_event(db_session, tenant, camera, person_category=None, person_status=None):
    event = Event(
        tenant_id=tenant.id, camera_id=camera.id, event_type=EventType.FACE_RECOGNIZED,
        occurred_at=datetime.now(timezone.utc),
        event_metadata={"person_category": person_category, "person_status": person_status, "confidence": 0.9},
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


def test_watchlist_match_rule(db_session, tenant):
    camera = _make_camera(db_session, tenant)
    rule = AIRule(
        tenant_id=tenant.id, name="Watchlist match",
        conditions={"event_type": "FACE_RECOGNIZED", "person_category": "WATCHLIST"},
        action_severity=EventSeverity.HIGH, action_alert_type="FACE_WATCHLIST_MATCH",
    )
    db_session.add(rule)
    db_session.commit()

    watchlist_event = _make_face_event(db_session, tenant, camera, person_category="WATCHLIST")
    assert len(rule_engine.evaluate_event(db_session, watchlist_event)) == 1

    employee_event = _make_face_event(db_session, tenant, camera, person_category="EMPLOYEE")
    assert rule_engine.evaluate_event(db_session, employee_event) == []


def test_suspended_person_rule(db_session, tenant):
    camera = _make_camera(db_session, tenant)
    rule = AIRule(
        tenant_id=tenant.id, name="Suspended person",
        conditions={"event_type": "FACE_RECOGNIZED", "person_status": "SUSPENDED"},
        action_severity=EventSeverity.CRITICAL, action_alert_type="FACE_SUSPENDED_PERSON",
    )
    db_session.add(rule)
    db_session.commit()

    suspended_event = _make_face_event(db_session, tenant, camera, person_status="SUSPENDED")
    alerts = rule_engine.evaluate_event(db_session, suspended_event)
    assert len(alerts) == 1
    assert alerts[0].severity == EventSeverity.CRITICAL

    active_event = _make_face_event(db_session, tenant, camera, person_status="ACTIVE")
    assert rule_engine.evaluate_event(db_session, active_event) == []


def test_person_category_accepts_a_list(db_session, tenant):
    camera = _make_camera(db_session, tenant)
    rule = AIRule(
        tenant_id=tenant.id, name="Non-employee restricted area",
        conditions={"event_type": "FACE_RECOGNIZED", "person_category": ["VISITOR", "CONTRACTOR"]},
    )
    db_session.add(rule)
    db_session.commit()

    visitor_event = _make_face_event(db_session, tenant, camera, person_category="VISITOR")
    assert len(rule_engine.evaluate_event(db_session, visitor_event)) == 1

    employee_event = _make_face_event(db_session, tenant, camera, person_category="EMPLOYEE")
    assert rule_engine.evaluate_event(db_session, employee_event) == []


def test_unknown_face_event_does_not_match_person_status_condition(db_session, tenant):
    """UNKNOWN_FACE_DETECTED events have no person -> person_category/status are None
    in event_metadata, so a rule requiring a specific status must not match them."""
    camera = _make_camera(db_session, tenant)
    rule = AIRule(tenant_id=tenant.id, name="Suspended", conditions={"person_status": "SUSPENDED"})
    db_session.add(rule)
    db_session.commit()

    unknown_event = Event(
        tenant_id=tenant.id, camera_id=camera.id, event_type=EventType.UNKNOWN_FACE_DETECTED,
        occurred_at=datetime.now(timezone.utc), event_metadata={"person_category": None, "person_status": None},
    )
    db_session.add(unknown_event)
    db_session.commit()
    db_session.refresh(unknown_event)

    assert rule_engine.evaluate_event(db_session, unknown_event) == []
