import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import SimpleEmailStr


class UserCreate(BaseModel):
    email: SimpleEmailStr
    password: str = Field(min_length=8)
    full_name: str = ""
    role: str = "VIEWER"


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class UserResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("role", mode="before")
    @classmethod
    def _role_name(cls, value):
        return value.name if hasattr(value, "name") else value
