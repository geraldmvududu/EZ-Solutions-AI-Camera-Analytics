import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.event import EventSeverity
from app.models.incident import IncidentStatus
from app.schemas.alert import AlertResponse


class IncidentCreate(BaseModel):
    title: str
    description: str = ""
    severity: EventSeverity
    camera_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None
    alert_ids: list[uuid.UUID] = []


class IncidentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    severity: EventSeverity | None = None
    status: IncidentStatus | None = None
    assigned_user_id: uuid.UUID | None = None
    resolution: str | None = None
    alert_ids: list[uuid.UUID] | None = None


class IncidentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    description: str
    severity: EventSeverity
    camera_id: uuid.UUID | None
    status: IncidentStatus
    assigned_user_id: uuid.UUID | None
    resolution: str
    closed_at: datetime | None
    created_at: datetime
    related_alerts: list[AlertResponse] = []

    model_config = {"from_attributes": True}
