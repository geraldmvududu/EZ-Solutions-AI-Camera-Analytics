import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.event import EventSeverity, EventType


class EventCreate(BaseModel):
    """Used internally by the AI engine (via the internal-service-authenticated endpoint)
    to report a real detected/derived event."""

    camera_id: uuid.UUID
    event_type: EventType
    severity: EventSeverity = EventSeverity.INFO
    description: str = ""
    detection_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    tripwire_id: uuid.UUID | None = None
    snapshot_id: uuid.UUID | None = None
    recording_id: uuid.UUID | None = None
    occurred_at: datetime
    event_metadata: dict = {}
    is_demo: bool = False


class EventResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    camera_id: uuid.UUID
    event_type: EventType
    severity: EventSeverity
    description: str
    detection_id: uuid.UUID | None
    zone_id: uuid.UUID | None
    tripwire_id: uuid.UUID | None
    snapshot_id: uuid.UUID | None
    recording_id: uuid.UUID | None
    occurred_at: datetime
    event_metadata: dict
    is_demo: bool
    created_at: datetime

    model_config = {"from_attributes": True}
