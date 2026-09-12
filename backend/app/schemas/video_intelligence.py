import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.analytics import NamedCount


class VideoIntelligenceSettingsUpdate(BaseModel):
    gate_jumping_enabled: bool | None = None
    tailgating_enabled: bool | None = None
    restricted_area_enabled: bool | None = None
    min_confidence: float | None = None
    pre_event_seconds: int | None = None
    post_event_seconds: int | None = None
    business_hours_start: str | None = None
    business_hours_end: str | None = None


class VideoIntelligenceSettingsResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    gate_jumping_enabled: bool
    tailgating_enabled: bool
    restricted_area_enabled: bool
    min_confidence: float
    pre_event_seconds: int
    post_event_seconds: int
    business_hours_start: str
    business_hours_end: str

    model_config = {"from_attributes": True}


class IncidentSummaryResponse(BaseModel):
    range_start: datetime
    range_end: datetime
    by_severity: list[NamedCount]
    by_type: list[NamedCount]


class PendingEvidenceClip(BaseModel):
    incident_id: uuid.UUID
    event_occurred_at: datetime
    recording_started_at: datetime
    recording_file_path: str
    recording_duration_seconds: float
    pre_event_seconds: int
    post_event_seconds: int


class EvidenceClipUpdate(BaseModel):
    evidence_clip_path: str
