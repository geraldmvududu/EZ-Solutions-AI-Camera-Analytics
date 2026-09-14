import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.vehicle_watchlist import VehicleWatchlistStatus


class VehicleWatchlistCreate(BaseModel):
    plate_text: str
    status: VehicleWatchlistStatus
    description: str = ""
    notes: str = ""


class VehicleWatchlistUpdate(BaseModel):
    status: VehicleWatchlistStatus | None = None
    description: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class VehicleWatchlistResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    plate_text: str
    status: VehicleWatchlistStatus
    description: str
    notes: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PlateRecognizeRequest(BaseModel):
    """Posted by ai-engine (internal-service-authenticated) for one real plate read —
    see ai-engine/app/core/plate_reader.py. The plate text has already passed a coarse
    regex sanity check there (rejecting obvious OCR garbage) before this is ever sent."""

    camera_id: uuid.UUID
    tracking_id: int
    plate_text: str
    vehicle_type: str
    confidence: float
    snapshot_id: uuid.UUID | None = None
    recording_id: uuid.UUID | None = None
    occurred_at: datetime


class PlateRecognizeResult(BaseModel):
    plate_text: str
    watchlist_status: str | None
    event_id: uuid.UUID


class LicensePlateResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    event_id: uuid.UUID
    camera_id: uuid.UUID
    watchlist_id: uuid.UUID | None
    plate_text: str
    vehicle_type: str
    confidence: float
    tracking_id: int
    occurred_at: datetime
    snapshot_id: uuid.UUID | None
    recording_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
