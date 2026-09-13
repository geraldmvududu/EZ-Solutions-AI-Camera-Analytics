"""Event-First Cloud Storage Phase 1 (section 14): a static, transparent
EventType -> EventCategory mapping — plain Python dict lookups, not an LLM call or a
trained classifier, matching this project's "do not hallucinate" convention used
throughout (see violation_service.py's description templates). Every EventType this
platform actually produces must have an entry here; a genuinely new type added later
without one falls back to OPERATIONS rather than raising, so a missed mapping update
degrades gracefully instead of breaking event creation.
"""

from app.models.event import EventCategory, EventType

_EVENT_TYPE_CATEGORY: dict[EventType, EventCategory] = {
    # SECURITY
    EventType.TRIPWIRE_VIOLATION: EventCategory.SECURITY,
    EventType.INTRUSION_DETECTED: EventCategory.SECURITY,
    EventType.GATE_JUMPING_DETECTED: EventCategory.SECURITY,
    EventType.TAILGATING_DETECTED: EventCategory.SECURITY,
    EventType.RESTRICTED_AREA_VIOLATION: EventCategory.SECURITY,
    EventType.POTENTIAL_THEFT_DETECTED: EventCategory.SECURITY,
    EventType.UNKNOWN_FACE_DETECTED: EventCategory.SECURITY,
    # PEOPLE
    EventType.PERSON_DETECTED: EventCategory.PEOPLE,
    EventType.LOITERING_DETECTED: EventCategory.PEOPLE,
    EventType.FACE_RECOGNIZED: EventCategory.PEOPLE,
    # VEHICLES
    EventType.VEHICLE_DETECTED: EventCategory.VEHICLES,
    # OPERATIONS
    EventType.MOTION_DETECTED: EventCategory.OPERATIONS,
    EventType.CAMERA_OFFLINE: EventCategory.OPERATIONS,
    EventType.CAMERA_ONLINE: EventCategory.OPERATIONS,
    EventType.RECORDING_FAILURE: EventCategory.OPERATIONS,
    EventType.AI_DETECTION: EventCategory.OPERATIONS,
}


def classify_event(event_type: EventType) -> EventCategory:
    return _EVENT_TYPE_CATEGORY.get(event_type, EventCategory.OPERATIONS)
