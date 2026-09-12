import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin, utcnow


class FaceProfileStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class FaceProfile(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    """The actual biometric record (section 2/14). `embedding_encrypted` is a
    Fernet-encrypted, base64-serialized numpy vector — never returned by any list/
    detail API response (see schemas/person.py). `image_reference` is a file path
    under the faces volume; the raw photo is retained only because section 2 asks
    admins to be able to review the enrolled photo, and is deletable independently of
    the embedding via the retention/secure-deletion path (Phase 2)."""

    __tablename__ = "face_profiles"

    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("persons.id"), nullable=False, index=True)
    embedding_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    image_reference: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    enrollment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    status: Mapped[FaceProfileStatus] = mapped_column(Enum(FaceProfileStatus), default=FaceProfileStatus.ACTIVE, nullable=False, index=True)
