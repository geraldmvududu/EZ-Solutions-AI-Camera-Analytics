"""Real rule evaluation against real Event rows (section 23). No detection or event here
is synthetic — this runs whenever app.api.routes.events creates an Event, whether that
event originated from the AI engine's real inference pipeline or from a manually
recorded camera-offline/online transition.
"""

from datetime import datetime, time

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.event import Event
from app.models.rule import AIRule


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _time_in_window(now: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= now <= end
    # Window wraps past midnight, e.g. 22:00-05:00.
    return now >= start or now <= end


def _rule_matches(rule: AIRule, event: Event) -> bool:
    cond = rule.conditions or {}

    if rule.camera_id is not None and rule.camera_id != event.camera_id:
        return False

    event_types = cond.get("event_type")
    if event_types:
        allowed = event_types if isinstance(event_types, list) else [event_types]
        if event.event_type.value not in allowed:
            return False

    if cond.get("zone_id") and str(event.zone_id) != str(cond["zone_id"]):
        return False

    if cond.get("tripwire_id") and str(event.tripwire_id) != str(cond["tripwire_id"]):
        return False

    object_type = cond.get("object_type")
    if object_type and event.event_metadata.get("object_type") != object_type:
        return False

    min_confidence = cond.get("min_confidence")
    if min_confidence is not None:
        confidence = event.event_metadata.get("confidence")
        if confidence is None or confidence < min_confidence:
            return False

    time_start, time_end = cond.get("time_start"), cond.get("time_end")
    if time_start and time_end:
        local_time = event.occurred_at.time()
        if not _time_in_window(local_time, _parse_hhmm(time_start), _parse_hhmm(time_end)):
            return False

    days_of_week = cond.get("days_of_week")
    if days_of_week is not None and event.occurred_at.weekday() not in days_of_week:
        return False

    return True


def evaluate_event(db: Session, event: Event) -> list[Alert]:
    """Evaluates every enabled rule for this tenant against `event`. Returns the list of
    newly created Alert rows (empty if nothing matched)."""

    rules = (
        db.query(AIRule)
        .filter(AIRule.tenant_id == event.tenant_id, AIRule.is_enabled.is_(True))
        .all()
    )

    created: list[Alert] = []
    for rule in rules:
        if not _rule_matches(rule, event):
            continue
        alert = Alert(
            tenant_id=event.tenant_id,
            event_id=event.id,
            camera_id=event.camera_id,
            rule_id=rule.id,
            alert_type=rule.action_alert_type,
            severity=rule.action_severity,
            snapshot_id=event.snapshot_id,
            recording_id=event.recording_id,
        )
        db.add(alert)
        created.append(alert)

    if created:
        db.commit()
        for alert in created:
            db.refresh(alert)

    return created
