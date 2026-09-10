import uuid

from pydantic import BaseModel

from app.models.tripwire import TripwireDirection


class TripwireCreate(BaseModel):
    camera_id: uuid.UUID
    name: str
    line: list[list[float]]
    direction: TripwireDirection = TripwireDirection.BOTH
    is_enabled: bool = True


class TripwireUpdate(BaseModel):
    name: str | None = None
    line: list[list[float]] | None = None
    direction: TripwireDirection | None = None
    is_enabled: bool | None = None


class TripwireResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    camera_id: uuid.UUID
    name: str
    line: list
    direction: TripwireDirection
    is_enabled: bool

    model_config = {"from_attributes": True}
