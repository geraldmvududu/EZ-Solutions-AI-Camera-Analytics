import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.face_profile import FaceProfileStatus
from app.models.person import PersonCategory, PersonStatus


class PersonCreate(BaseModel):
    first_name: str
    last_name: str
    external_reference: str = ""
    category: PersonCategory
    department: str = ""
    notes: str = ""
    expires_at: datetime | None = None


class PersonUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    external_reference: str | None = None
    category: PersonCategory | None = None
    department: str | None = None
    notes: str | None = None
    status: PersonStatus | None = None
    expires_at: datetime | None = None


class FaceProfileResponse(BaseModel):
    """Deliberately omits embedding_encrypted — section 16: "Do not expose facial
    embeddings through normal frontend API responses." """

    id: uuid.UUID
    person_id: uuid.UUID
    model_version: str
    quality_score: float
    enrollment_date: datetime
    status: FaceProfileStatus

    model_config = {"from_attributes": True}


class PersonResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    external_reference: str
    first_name: str
    last_name: str
    category: PersonCategory
    department: str
    notes: str
    status: PersonStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    face_profiles: list[FaceProfileResponse] = []

    model_config = {"from_attributes": True}


class EnrollmentResult(BaseModel):
    success: bool
    message: str
    person: PersonResponse | None = None
    quality_score: float | None = None
