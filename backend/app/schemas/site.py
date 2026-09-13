import uuid
from datetime import datetime

from pydantic import BaseModel


class SiteCreate(BaseModel):
    name: str
    address: str = ""
    timezone: str = "UTC"


class SiteUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    timezone: str | None = None
    is_active: bool | None = None


class SiteResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    address: str
    timezone: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
