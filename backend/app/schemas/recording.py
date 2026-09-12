import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.recording import RecordingTrigger


class RecordingCreate(BaseModel):
    """Reported internally by the AI engine when a segment STARTS (not when it
    finishes) — see RecordingFinalize below for why. ended_at/duration/file_size are
    all still unknown at this point; they're 0/None until the segment closes."""

    camera_id: uuid.UUID
    file_path: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float = 0
    trigger_type: RecordingTrigger
    file_size_bytes: int = 0


class RecordingFinalize(BaseModel):
    """Reported when a segment closes (SegmentRecorder.stop()). Recording rows are now
    created at start time (RecordingCreate) specifically so a real recording_id exists
    to attach to a face-recognition/violation event that happens WHILE the segment is
    still being written — this call just fills in what wasn't knowable until the
    segment actually finished."""

    ended_at: datetime
    duration_seconds: float
    file_size_bytes: int


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
