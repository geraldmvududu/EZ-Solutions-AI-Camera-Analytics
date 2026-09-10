import uuid
from datetime import datetime

from pydantic import BaseModel


class SnapshotCreate(BaseModel):
    camera_id: uuid.UUID
    event_id: uuid.UUID | None = None
    file_path: str
    taken_at: datetime
    object_type: str = ""
    confidence: float | None = None


class SnapshotResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    camera_id: uuid.UUID
    event_id: uuid.UUID | None
    file_path: str
    taken_at: datetime
    object_type: str
    confidence: float | None

    model_config = {"from_attributes": True}
