import uuid
from datetime import datetime, timedelta, timezone

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


def test_rule_cooldown_suppresses_a_second_match_within_the_window(db_session, tenant):
    """Real bug found live on the deployed VM: a rule matching a frequently-recurring
    event type had no cooldown at all and created a fresh CRITICAL alert every ~30
    seconds for over an hour on a busy looping test camera."""
    camera = _make_camera(db_session, tenant)
    rule = AIRule(
        tenant_id=tenant.id, name="gate rule", conditions={"event_type": "PERSON_DETECTED"},
        action_severity=EventSeverity.CRITICAL, cooldown_seconds=300,
    )
    db_session.add(rule)
    db_session.commit()

    def _make_event():
        event = Event(
            tenant_id=tenant.id, camera_id=camera.id, event_type=EventType.PERSON_DETECTED,
            occurred_at=datetime.now(timezone.utc), event_metadata={},
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        return event

    first_alerts = rule_engine.evaluate_event(db_session, _make_event())
    assert len(first_alerts) == 1

    second_alerts = rule_engine.evaluate_event(db_session, _make_event())
    assert second_alerts == [], "a second match within the cooldown window must not create a second alert"


def test_rule_cooldown_allows_a_match_after_the_window_expires(db_session, tenant):
    camera = _make_camera(db_session, tenant)
    rule = AIRule(
        tenant_id=tenant.id, name="gate rule", conditions={"event_type": "PERSON_DETECTED"}, cooldown_seconds=300,
    )
    db_session.add(rule)
    db_session.commit()

    def _make_event(occurred_at):
        event = Event(
            tenant_id=tenant.id, camera_id=camera.id, event_type=EventType.PERSON_DETECTED,
            occurred_at=occurred_at, event_metadata={},
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        return event

    now = datetime.now(timezone.utc)
    first_alerts = rule_engine.evaluate_event(db_session, _make_event(now))
    assert len(first_alerts) == 1
    # Backdate the alert itself (not just the event) — evaluate_event's cooldown looks
    # at when the ALERT was actually created, matching what a real gap in wall-clock
    # time between two real alerts looks like.
    first_alerts[0].created_at = now - timedelta(seconds=301)
    db_session.commit()

    second_alerts = rule_engine.evaluate_event(db_session, _make_event(now))
    assert len(second_alerts) == 1, "a genuinely new match after the cooldown has elapsed must still be reported"


def test_rule_cooldown_zero_disables_throttling(db_session, tenant):
    camera = _make_camera(db_session, tenant)
    rule = AIRule(
        tenant_id=tenant.id, name="always alert", conditions={"event_type": "PERSON_DETECTED"}, cooldown_seconds=0,
    )
    db_session.add(rule)
    db_session.commit()

    def _make_event():
        event = Event(
            tenant_id=tenant.id, camera_id=camera.id, event_type=EventType.PERSON_DETECTED,
            occurred_at=datetime.now(timezone.utc), event_metadata={},
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        return event

    assert len(rule_engine.evaluate_event(db_session, _make_event())) == 1
    assert len(rule_engine.evaluate_event(db_session, _make_event())) == 1


def test_rule_cooldown_is_scoped_per_camera(db_session, tenant):
    """A camera-agnostic rule (camera_id=None) matching a genuinely different camera
    must not be suppressed by another camera's recent alert."""
    camera_a = _make_camera(db_session, tenant)
    camera_b = Camera(tenant_id=tenant.id, camera_code="CAM-002", name="Back Gate", source_type=CameraSourceType.SIMULATED)
    db_session.add(camera_b)
    db_session.commit()
    db_session.refresh(camera_b)

    rule = AIRule(
        tenant_id=tenant.id, name="any camera", conditions={"event_type": "PERSON_DETECTED"}, cooldown_seconds=300,
    )
    db_session.add(rule)
    db_session.commit()

    def _make_event(camera):
        event = Event(
            tenant_id=tenant.id, camera_id=camera.id, event_type=EventType.PERSON_DETECTED,
            occurred_at=datetime.now(timezone.utc), event_metadata={},
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        return event

    assert len(rule_engine.evaluate_event(db_session, _make_event(camera_a))) == 1
    assert len(rule_engine.evaluate_event(db_session, _make_event(camera_b))) == 1, "a different camera must get its own alert"


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
