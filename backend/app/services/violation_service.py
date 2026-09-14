"""Correlates the tripwire/zone violation pipeline with real Incidents (spec section
9's "Person + Behaviour" combination, extended by AI Video Intelligence Phase 1).

Two distinct code paths live here:

1. **Identified-person violations** (original, Facial Recognition Phase 1): a
   TRIPWIRE_VIOLATION or INTRUSION_DETECTED event only becomes an Incident when it
   carries an identified person (ai-engine attaches this — see
   worker.py::_identity_metadata, populated from FaceRecognizer.identity_for). A plain,
   unidentified crossing of an ordinary tripwire/intrusion zone is normal traffic, not
   incident-worthy on its own.

2. **AI Video Intelligence violations** (Phase 1: GATE_JUMPING_DETECTED,
   TAILGATING_DETECTED, RESTRICTED_AREA_VIOLATION): these event types only ever fire
   when the zone/tripwire logic in ai-engine has *already* decided a violation
   occurred (see worker.py), so they always become an Incident — with a recognized
   identity as an optional enrichment ("Unknown Person" when none) rather than a gate.
   Each of these Incidents also gets a real, transparent `risk_score` (see
   compute_risk_score below) and `requires_human_review=True`, matching spec section
   39's default posture for anything the platform can't independently confirm.

Both paths deliberately reuse the existing Incident model/API/page (section 5) rather
than inventing a parallel "violations" table — an Incident already has exactly what a
case file needs: title, description, severity, an investigation-status workflow (OPEN
-> INVESTIGATING -> CONTAINED -> RESOLVED -> CLOSED), a resolution field, and links to
the evidentiary Alert(s)/snapshot(s)/recording.

Nothing here claims certainty it doesn't have: descriptions are plain, deterministic
string formatting from real event/zone/camera/confidence facts — never an LLM call —
and every generated description explicitly tells the reviewer to check the linked
evidence rather than treat the correlation as confirmed proof (spec section 18's
"do not hallucinate" requirement).

**Multi-event incident correlation** (Master Development Prompt Phase 1): before either
path above creates a brand-new Incident, it first checks whether the triggering event's
`correlation_key` (same camera + same `tracking_id`, or same camera + same `person_id`
when no `tracking_id` is present — see `_compute_correlation_key`) matches an
already-open Incident whose `updated_at` is within `VideoIntelligenceSettings.
correlation_window_seconds` (default 120s). If so, the new event is MERGED into that
incident (linked via the `incident_events` table, its Alerts added to `related_alerts`,
severity escalated if higher, and a real timeline line appended to the description)
instead of creating a redundant second incident — this is the literal mechanism behind
the master prompt's own worked examples ("person detected -> entered zone -> loitered ->
object removed" becoming ONE incident, not four). This is deliberately a DIFFERENT,
narrower check than `_recently_had_incident` below: correlation requires the SAME
tracked presence (a much stronger signal) and merges across DIFFERENT incident types,
while the cooldown suppresses same-camera/same-type repeats regardless of tracking
identity (needed because a looping test video's repeated crossings get a fresh
tracking_id every loop pass — see limitation 24 — so correlation alone would not have
fixed the original repeated-incident bug that cooldown was built for). Both mechanisms
run, in that order: correlation first (a stronger, more specific match), then cooldown
as a fallback for content that repeats without a stable tracking identity.
"""

import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.camera import Camera
from app.models.event import Event, EventSeverity, EventType
from app.models.incident import Incident, IncidentStatus, incident_events
from app.models.person import Person

# Only an incident that's still genuinely "live" is eligible to absorb a later,
# correlated event — one already RESOLVED/CLOSED is a finished case file, not something
# a new detection should silently reopen and rewrite.
_CORRELATABLE_STATUSES = {IncidentStatus.OPEN, IncidentStatus.INVESTIGATING, IncidentStatus.CONTAINED}

_SEVERITY_RANK = {
    EventSeverity.INFO: 0,
    EventSeverity.LOW: 1,
    EventSeverity.MEDIUM: 2,
    EventSeverity.HIGH: 3,
    EventSeverity.CRITICAL: 4,
}

_IDENTIFIED_PERSON_EVENT_TYPES = {EventType.TRIPWIRE_VIOLATION, EventType.INTRUSION_DETECTED}

_IDENTIFIED_PERSON_EVENT_LABEL = {
    EventType.TRIPWIRE_VIOLATION: "crossed a tripwire",
    EventType.INTRUSION_DETECTED: "entered a restricted zone",
}

_ALWAYS_INCIDENT_EVENT_TYPES = {
    EventType.GATE_JUMPING_DETECTED,
    EventType.TAILGATING_DETECTED,
    EventType.RESTRICTED_AREA_VIOLATION,
    EventType.POTENTIAL_THEFT_DETECTED,
}

# compute_risk_score's weights (spec section 19) — deliberately simple and documented
# here so the number is explainable, not a black box. 0-100, clamped; used only for
# alert prioritization/sorting, never as proof a violation actually occurred.
_SEVERITY_BASE_SCORE = {
    EventSeverity.CRITICAL: 40,
    EventSeverity.HIGH: 30,
    EventSeverity.MEDIUM: 15,
    EventSeverity.LOW: 5,
    EventSeverity.INFO: 0,
}
_AFTER_HOURS_BONUS = 20
_IDENTIFIED_PERSON_BONUS = 15


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _is_after_hours(occurred_at: datetime, business_hours_start: str, business_hours_end: str) -> bool:
    start, end = _parse_hhmm(business_hours_start), _parse_hhmm(business_hours_end)
    now = occurred_at.time()
    inside_hours = start <= now <= end if start <= end else (now >= start or now <= end)
    return not inside_hours


def compute_risk_score(
    severity: EventSeverity,
    occurred_at: datetime,
    business_hours_start: str,
    business_hours_end: str,
    has_identified_person: bool,
) -> int:
    """0-100, alert-prioritization only (spec section 19) — never proof that a
    violation actually occurred. See the module docstring and _SEVERITY_BASE_SCORE/
    _AFTER_HOURS_BONUS/_IDENTIFIED_PERSON_BONUS above for the exact, documented
    formula."""
    score = _SEVERITY_BASE_SCORE.get(severity, 15)
    if _is_after_hours(occurred_at, business_hours_start, business_hours_end):
        score += _AFTER_HOURS_BONUS
    if has_identified_person:
        score += _IDENTIFIED_PERSON_BONUS
    return max(0, min(100, score))


def _resolve_person(db: Session, event: Event) -> Person | None:
    person_id_raw = event.event_metadata.get("person_id")
    if not person_id_raw:
        return None
    try:
        person = db.get(Person, uuid.UUID(str(person_id_raw)))
    except ValueError:
        return None
    return person


def _identity_clause(person: Person | None, confidence) -> str:
    if person is None:
        return "The person's identity could not be determined (no facial recognition match) — logged as Unknown Person."
    confidence_note = f" (confidence {confidence * 100:.0f}%)" if isinstance(confidence, (int, float)) else ""
    return f"They were identified via facial recognition as {person.first_name} {person.last_name} ({person.category.value}){confidence_note}."


_ALWAYS_INCIDENT_TITLE = {
    EventType.GATE_JUMPING_DETECTED: "Possible Gate Jumping",
    EventType.TAILGATING_DETECTED: "Possible Tailgating",
    EventType.RESTRICTED_AREA_VIOLATION: "Restricted Area Violation",
    EventType.POTENTIAL_THEFT_DETECTED: "Potential Theft / Unauthorized Object Removal",
}


def _build_always_incident_description(event: Event, camera: Camera, person: Person | None) -> str:
    identity = _identity_clause(person, event.event_metadata.get("person_recognition_confidence"))
    when = event.occurred_at.isoformat()

    if event.event_type == EventType.GATE_JUMPING_DETECTED:
        confidence = event.event_metadata.get("confidence")
        confidence_note = f" (heuristic confidence {confidence * 100:.0f}%)" if isinstance(confidence, (int, float)) else ""
        return (
            f"A person was observed crossing a gate/fence boundary on camera '{camera.name}' at {when} with a "
            f"trajectory consistent with climbing or jumping rather than a normal walk-through{confidence_note}. "
            f"{identity} This is a real-time trajectory heuristic, not a trained climbing/jumping classifier — "
            f"review the linked evidence before treating this as confirmed."
        )
    if event.event_type == EventType.TAILGATING_DETECTED:
        window = event.event_metadata.get("window_seconds")
        window_note = f" within {window}s of" if window is not None else " immediately after"
        return (
            f"A person crossed a controlled access point on camera '{camera.name}' at {when}{window_note} another "
            f"person's crossing, without a separate authorized entry in between. {identity} This platform has no "
            f"access-control-system integration, so this is video-only evidence — review the linked footage "
            f"before treating this as confirmed."
        )
    if event.event_type == EventType.POTENTIAL_THEFT_DETECTED:
        object_type = event.event_metadata.get("object_type", "object")
        threshold = event.event_metadata.get("threshold_seconds")
        threshold_note = f" for at least {threshold} seconds" if threshold is not None else ""
        return (
            f"A {object_type.lower()} that had been present in a monitored area on camera '{camera.name}'"
            f"{threshold_note} was removed from the area at {when}. {identity} This is an object-class-detection "
            f"+ zone dwell/exit heuristic, not a trained theft-behavior classifier — review the linked evidence "
            f"before treating this as confirmed."
        )
    # RESTRICTED_AREA_VIOLATION
    threshold = event.event_metadata.get("threshold_seconds")
    threshold_note = f" for at least {threshold} seconds" if threshold is not None else ""
    return (
        f"A person remained in a restricted area on camera '{camera.name}'{threshold_note}, detected at {when}. "
        f"{identity} Review the linked evidence before treating this as a confirmed violation."
    )


def _compute_correlation_key(event: Event) -> str | None:
    """Prefers tracking_id (present in event_metadata for every violation event type
    worker.py creates — TRIPWIRE_VIOLATION, INTRUSION_DETECTED, GATE_JUMPING_DETECTED,
    TAILGATING_DETECTED, RESTRICTED_AREA_VIOLATION, POTENTIAL_THEFT_DETECTED) over
    person_id (only present once face recognition has actually matched someone) since
    it's the more universally available "this is very likely the same real presence"
    signal — not a stronger identity claim than a person_id would be, just a more
    common one. Returns None when neither is present, meaning this event can never be
    correlated (it always creates its own incident, exactly as before this feature
    existed)."""
    tracking_id = event.event_metadata.get("tracking_id")
    if tracking_id is not None:
        return f"{event.camera_id}:track:{tracking_id}"
    person_id = event.event_metadata.get("person_id")
    if person_id:
        return f"{event.camera_id}:person:{person_id}"
    return None


def _find_correlatable_incident(db: Session, correlation_key: str, window_seconds: int) -> Incident | None:
    if window_seconds <= 0:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    return (
        db.query(Incident)
        .filter(
            Incident.correlation_key == correlation_key,
            Incident.status.in_(_CORRELATABLE_STATUSES),
            Incident.updated_at >= cutoff,
        )
        .order_by(Incident.updated_at.desc())
        .first()
    )


def _ensure_timeline_seeded(db: Session, incident: Incident) -> str:
    """The first time an incident is ever correlated into, its description is still
    just the original single-event prose paragraph with no timeline section yet — seed
    one from the incident's own source event so the timeline is complete from the
    start, not just from the point correlation began."""
    if "\n\nTimeline:\n" in incident.description:
        return incident.description
    source_event = db.get(Event, incident.source_event_id) if incident.source_event_id else None
    if source_event is None:
        return incident.description
    first_line = f"{source_event.occurred_at.strftime('%H:%M:%S')} — {source_event.event_type.value.replace('_', ' ').title()}"
    return f"{incident.description}\n\nTimeline:\n{first_line}"


def _seed_incident_events(db: Session, incident: Incident, source_event: Event) -> None:
    """Links a brand-new incident's own triggering event into incident_events at
    creation time — without this, `linked_events` (the timeline the frontend renders)
    would only ever contain LATER correlated events, never the one the incident was
    actually created from."""
    db.execute(
        incident_events.insert().values(incident_id=incident.id, event_id=source_event.id, occurred_at=source_event.occurred_at)
    )
    db.commit()


def _attach_event_to_incident(db: Session, incident: Incident, event: Event, alerts: list[Alert]) -> Incident:
    db.execute(incident_events.insert().values(incident_id=incident.id, event_id=event.id, occurred_at=event.occurred_at))

    existing_alert_ids = {a.id for a in incident.related_alerts}
    new_alerts = [a for a in alerts if a.id not in existing_alert_ids]
    if new_alerts:
        incident.related_alerts = list(incident.related_alerts) + new_alerts

    if _SEVERITY_RANK.get(event.severity, 0) > _SEVERITY_RANK.get(incident.severity, 0):
        incident.severity = event.severity

    timeline_line = f"{event.occurred_at.strftime('%H:%M:%S')} — {event.event_type.value.replace('_', ' ').title()}"
    incident.description = f"{_ensure_timeline_seeded(db, incident)}\n{timeline_line}"

    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def _recently_had_incident(db: Session, camera_id, incident_type: str, cooldown_seconds: int) -> bool:
    """Real bug found live on the deployed VM: the always-incident dispatch below
    created a brand-new Incident every single time its triggering event type fired,
    with no throttling of its own — a looping test video replaying the same gate-jump
    content every loop pass produced a new Incident every ~30-90s indefinitely.
    Scoped per (camera, incident_type) — a genuinely different incident TYPE on the
    same camera (e.g. a real theft alongside an unrelated gate-jump) still gets its
    own Incident; cooldown_seconds<=0 is a real, supported opt-out."""
    if cooldown_seconds <= 0:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
    return (
        db.query(Incident)
        .filter(Incident.camera_id == camera_id, Incident.incident_type == incident_type, Incident.created_at >= cutoff)
        .first()
        is not None
    )


def _maybe_create_always_incident(db: Session, event: Event, alerts: list[Alert], camera: Camera) -> tuple[Incident, bool] | None:
    from app.api.routes.video_intelligence import _get_or_create_settings

    vi_settings = _get_or_create_settings(db, event.tenant_id)

    correlation_key = _compute_correlation_key(event)
    if correlation_key is not None:
        existing = _find_correlatable_incident(db, correlation_key, vi_settings.correlation_window_seconds)
        if existing is not None:
            return _attach_event_to_incident(db, existing, event, alerts), False

    if _recently_had_incident(db, camera.id, event.event_type.value, vi_settings.incident_cooldown_seconds):
        return None
    person = _resolve_person(db, event)
    has_person = person is not None

    risk_score = compute_risk_score(
        event.severity, event.occurred_at, vi_settings.business_hours_start, vi_settings.business_hours_end, has_person,
    )

    person_label = f"{person.first_name} {person.last_name}" if person else "Unknown Person"
    title = f"{_ALWAYS_INCIDENT_TITLE.get(event.event_type, event.event_type.value.replace('_', ' ').title())} — {person_label} at {camera.name}"

    incident = Incident(
        tenant_id=event.tenant_id,
        title=title,
        description=_build_always_incident_description(event, camera, person),
        severity=event.severity,
        camera_id=camera.id,
        status=IncidentStatus.OPEN,
        incident_type=event.event_type.value,
        confidence=event.event_metadata.get("confidence") if isinstance(event.event_metadata.get("confidence"), (int, float)) else None,
        risk_score=risk_score,
        requires_human_review=True,
        source_event_id=event.id,
        correlation_key=correlation_key,
    )
    incident.related_alerts = alerts
    db.add(incident)
    db.commit()
    db.refresh(incident)
    _seed_incident_events(db, incident, event)
    db.refresh(incident)
    return incident, True


def _maybe_create_identified_person_incident(db: Session, event: Event, alerts: list[Alert], camera: Camera) -> tuple[Incident, bool] | None:
    from app.api.routes.video_intelligence import _get_or_create_settings

    person = _resolve_person(db, event)
    if person is None:
        return None

    vi_settings = _get_or_create_settings(db, event.tenant_id)

    correlation_key = _compute_correlation_key(event)
    if correlation_key is not None:
        existing = _find_correlatable_incident(db, correlation_key, vi_settings.correlation_window_seconds)
        if existing is not None:
            return _attach_event_to_incident(db, existing, event, alerts), False

    if _recently_had_incident(db, camera.id, event.event_type.value, vi_settings.incident_cooldown_seconds):
        return None

    confidence = event.event_metadata.get("person_recognition_confidence")
    action_label = _IDENTIFIED_PERSON_EVENT_LABEL.get(event.event_type, event.event_type.value.replace("_", " ").lower())
    confidence_note = f" (recognition confidence {confidence * 100:.0f}%)" if isinstance(confidence, (int, float)) else ""

    incident = Incident(
        tenant_id=event.tenant_id,
        title=f"{person.first_name} {person.last_name} — {event.event_type.value.replace('_', ' ').title()} at {camera.name}",
        description=(
            f"{person.first_name} {person.last_name} ({person.category.value}) was identified via facial "
            f"recognition and {action_label} on camera '{camera.name}' at {event.occurred_at.isoformat()}"
            f"{confidence_note}. Facial recognition and the boundary-crossing detection are independent, "
            f"automated signals correlated by camera/tracking — review the linked alert and its snapshot/"
            f"recording before treating this as a confirmed violation."
        ),
        severity=EventSeverity.CRITICAL,
        camera_id=camera.id,
        status=IncidentStatus.OPEN,
        incident_type=event.event_type.value,
        source_event_id=event.id,
        correlation_key=correlation_key,
    )
    incident.related_alerts = alerts
    db.add(incident)
    db.commit()
    db.refresh(incident)
    _seed_incident_events(db, incident, event)
    db.refresh(incident)
    return incident, True


def maybe_create_violation_incident(db: Session, event: Event, alerts: list[Alert], camera: Camera) -> tuple[Incident, bool] | None:
    """Returns (the created-or-correlated Incident, was_newly_created), or None if this
    event doesn't warrant one — see the module docstring for the two distinct dispatch
    paths and the correlation logic that runs inside each of them."""
    if event.event_type in _ALWAYS_INCIDENT_EVENT_TYPES:
        return _maybe_create_always_incident(db, event, alerts, camera)
    if event.event_type in _IDENTIFIED_PERSON_EVENT_TYPES:
        return _maybe_create_identified_person_incident(db, event, alerts, camera)
    return None
