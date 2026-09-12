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
    # AI Video Intelligence Phase 1 (section 26): CONFIRMED/FALSE_POSITIVE/
    # REQUIRES_INVESTIGATION/DISMISSED/ESCALATED — stored for false-positive-rate
    # reporting only, never used to auto-retrain anything.
    review_decision: str | None = None


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
    incident_type: str
    confidence: float | None
    risk_score: int | None
    requires_human_review: bool
    review_decision: str
    evidence_clip_path: str | None
    source_event_id: uuid.UUID | None
    related_alerts: list[AlertResponse] = []

    model_config = {"from_attributes": True}
