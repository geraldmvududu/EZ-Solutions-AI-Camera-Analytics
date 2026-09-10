import uuid

from pydantic import BaseModel

from app.schemas.common import SimpleEmailStr


class LoginRequest(BaseModel):
    email: SimpleEmailStr
    password: str
    remember_me: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class CurrentUserResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str
    role: str
    permissions: list[str]

    model_config = {"from_attributes": True}
