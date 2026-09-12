"""Correlates Facial Recognition with the existing tripwire/zone violation pipeline
(spec section 9's "Person + Behaviour" combination): when a TRIPWIRE_VIOLATION or
INTRUSION_DETECTED event carries an identified person (ai-engine attaches this —
see worker.py::_identity_metadata, populated from FaceRecognizer.identity_for), a
real Incident is automatically opened for it, linked to whatever Alert(s) the rule
engine just created from the same event.

This deliberately reuses the existing Incident model/API/page (section 5) rather than
inventing a parallel "violations" table — an Incident already has exactly what a case
file needs: title, description, severity, an investigation-status workflow (OPEN ->
INVESTIGATING -> CONTAINED -> RESOLVED -> CLOSED), a resolution field, and links to
the evidentiary Alert(s)/snapshot(s).

Face recognition itself is never treated as proof of the violation — the identity and
the boundary crossing are two independent, correlated signals (by track_id), and the
auto-generated description says so explicitly.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.camera import Camera
from app.models.event import Event, EventSeverity, EventType
from app.models.incident import Incident, IncidentStatus
from app.models.person import Person

_VIOLATION_EVENT_TYPES = {EventType.TRIPWIRE_VIOLATION, EventType.INTRUSION_DETECTED}

_EVENT_TYPE_LABEL = {
    EventType.TRIPWIRE_VIOLATION: "crossed a tripwire",
    EventType.INTRUSION_DETECTED: "entered a restricted zone",
}


def maybe_create_violation_incident(db: Session, event: Event, alerts: list[Alert], camera: Camera) -> Incident | None:
    """Returns the newly created Incident, or None if this event isn't an identified-
    person violation (either the wrong event type, or no person_id in its metadata —
    e.g. facial recognition isn't enabled on this camera, or the person crossing
    wasn't recognized)."""
    if event.event_type not in _VIOLATION_EVENT_TYPES:
        return None

    person_id_raw = event.event_metadata.get("person_id")
    if not person_id_raw:
        return None

    try:
        person = db.get(Person, uuid.UUID(str(person_id_raw)))
    except ValueError:
        return None
    if person is None:
        return None

    confidence = event.event_metadata.get("person_recognition_confidence")
    action_label = _EVENT_TYPE_LABEL.get(event.event_type, event.event_type.value.replace("_", " ").lower())
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
    )
    incident.related_alerts = alerts
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident
