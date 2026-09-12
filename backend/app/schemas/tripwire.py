import uuid

from pydantic import BaseModel

from app.models.tripwire import TripwireDirection


class TripwireCreate(BaseModel):
    camera_id: uuid.UUID
    name: str
    line: list[list[float]]
    direction: TripwireDirection = TripwireDirection.BOTH
    is_enabled: bool = True
    # AI Video Intelligence Phase 1 (sections 4/8) — opt-in per tripwire, not global.
    gate_jump_detection_enabled: bool = False
    tailgating_detection_enabled: bool = False
    tailgating_window_seconds: int = 5


class TripwireUpdate(BaseModel):
    name: str | None = None
    line: list[list[float]] | None = None
    direction: TripwireDirection | None = None
    is_enabled: bool | None = None
    gate_jump_detection_enabled: bool | None = None
    tailgating_detection_enabled: bool | None = None
    tailgating_window_seconds: int | None = None


class TripwireResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    camera_id: uuid.UUID
    name: str
    line: list
    direction: TripwireDirection
    is_enabled: bool
    gate_jump_detection_enabled: bool
    tailgating_detection_enabled: bool
    tailgating_window_seconds: int

    model_config = {"from_attributes": True}
