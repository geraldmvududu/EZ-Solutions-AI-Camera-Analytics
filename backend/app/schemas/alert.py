import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.alert import AlertStatus
from app.models.event import EventSeverity


class AlertUpdate(BaseModel):
    status: AlertStatus | None = None
    assigned_user_id: uuid.UUID | None = None
    notes: str | None = None


class AlertResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    event_id: uuid.UUID
    camera_id: uuid.UUID
    rule_id: uuid.UUID | None
    alert_type: str
    severity: EventSeverity
    status: AlertStatus
    snapshot_id: uuid.UUID | None
    recording_id: uuid.UUID | None
    assigned_user_id: uuid.UUID | None
    notes: str
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
