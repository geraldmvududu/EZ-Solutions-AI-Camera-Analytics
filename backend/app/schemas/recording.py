import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.recording import RecordingTrigger


class RecordingCreate(BaseModel):
    """Reported internally by the AI engine / recorder service when a segment is finalized."""

    camera_id: uuid.UUID
    file_path: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float = 0
    trigger_type: RecordingTrigger
    file_size_bytes: int = 0


class RecordingProtect(BaseModel):
    protection_notes: str = ""
    incident_number: str = ""


class RecordingResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    camera_id: uuid.UUID
    file_path: str
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: float
    trigger_type: RecordingTrigger
    file_size_bytes: int
    is_protected: bool
    protection_notes: str
    incident_number: str
    protected_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
