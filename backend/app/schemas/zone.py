import uuid

from pydantic import BaseModel

from app.models.zone import ZoneType


class ZoneCreate(BaseModel):
    camera_id: uuid.UUID
    name: str
    zone_type: ZoneType
    polygon: list[list[float]]
    loitering_threshold_seconds: int = 30
    is_enabled: bool = True


class ZoneUpdate(BaseModel):
    name: str | None = None
    polygon: list[list[float]] | None = None
    loitering_threshold_seconds: int | None = None
    is_enabled: bool | None = None


class ZoneResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    camera_id: uuid.UUID
    name: str
    zone_type: ZoneType
    polygon: list
    loitering_threshold_seconds: int
    is_enabled: bool

    model_config = {"from_attributes": True}
