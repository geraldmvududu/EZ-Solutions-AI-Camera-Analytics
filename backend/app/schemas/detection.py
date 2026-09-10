import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.detection import ObjectType


class DetectionCreate(BaseModel):
    camera_id: uuid.UUID
    object_type: ObjectType
    confidence: float
    bbox_x: float
    bbox_y: float
    bbox_width: float
    bbox_height: float
    tracking_id: int
    frame_number: int = 0
    detected_at: datetime
    snapshot_id: uuid.UUID | None = None
    recording_id: uuid.UUID | None = None


class DetectionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    camera_id: uuid.UUID
    object_type: ObjectType
    confidence: float
    bbox_x: float
    bbox_y: float
    bbox_width: float
    bbox_height: float
    tracking_id: int
    frame_number: int
    detected_at: datetime
    snapshot_id: uuid.UUID | None
    recording_id: uuid.UUID | None

    model_config = {"from_attributes": True}
