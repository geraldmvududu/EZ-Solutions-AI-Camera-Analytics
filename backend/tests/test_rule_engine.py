import uuid
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


def test_rule_matches_event_type_and_creates_alert(db_session, tenant):
    camera = _make_camera(db_session, tenant)
    rule = AIRule(
        tenant_id=tenant.id,
        name="Person after hours",
        conditions={"event_type": "PERSON_DETECTED"},
        action_severity=EventSeverity.HIGH,
        action_alert_type="PERSON_AFTER_HOURS",
    )
    db_session.add(rule)
    db_session.commit()

    event = Event(
        tenant_id=tenant.id,
        camera_id=camera.id,
        event_type=EventType.PERSON_DETECTED,
        occurred_at=datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc),
        event_metadata={"object_type": "PERSON", "confidence": 0.95},
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    alerts = rule_engine.evaluate_event(db_session, event)
    assert len(alerts) == 1
    assert alerts[0].severity == EventSeverity.HIGH
    assert alerts[0].alert_type == "PERSON_AFTER_HOURS"


def test_rule_does_not_match_wrong_event_type(db_session, tenant):
    camera = _make_camera(db_session, tenant)
    rule = AIRule(tenant_id=tenant.id, name="Vehicle rule", conditions={"event_type": "VEHICLE_DETECTED"})
    db_session.add(rule)
    db_session.commit()

    event = Event(
        tenant_id=tenant.id, camera_id=camera.id, event_type=EventType.PERSON_DETECTED,
        occurred_at=datetime.now(timezone.utc), event_metadata={},
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert rule_engine.evaluate_event(db_session, event) == []


def test_rule_time_window_wraps_midnight(db_session, tenant):
    camera = _make_camera(db_session, tenant)
    rule = AIRule(
        tenant_id=tenant.id, name="Overnight rule",
        conditions={"event_type": "PERSON_DETECTED", "time_start": "22:00", "time_end": "05:00"},
    )
    db_session.add(rule)
    db_session.commit()

    # 23:00 is inside the overnight window -> should match.
    event_night = Event(
        tenant_id=tenant.id, camera_id=camera.id, event_type=EventType.PERSON_DETECTED,
        occurred_at=datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc), event_metadata={},
    )
    db_session.add(event_night)
    db_session.commit()
    db_session.refresh(event_night)
    assert len(rule_engine.evaluate_event(db_session, event_night)) == 1

    # 12:00 noon is outside the window -> should not match.
    event_day = Event(
        tenant_id=tenant.id, camera_id=camera.id, event_type=EventType.PERSON_DETECTED,
        occurred_at=datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc), event_metadata={},
    )
    db_session.add(event_day)
    db_session.commit()
    db_session.refresh(event_day)
    assert rule_engine.evaluate_event(db_session, event_day) == []


def test_disabled_rule_never_matches(db_session, tenant):
    camera = _make_camera(db_session, tenant)
    rule = AIRule(tenant_id=tenant.id, name="Disabled", is_enabled=False, conditions={"event_type": "PERSON_DETECTED"})
    db_session.add(rule)
    db_session.commit()

    event = Event(
        tenant_id=tenant.id, camera_id=camera.id, event_type=EventType.PERSON_DETECTED,
        occurred_at=datetime.now(timezone.utc), event_metadata={},
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert rule_engine.evaluate_event(db_session, event) == []
