import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class RecordingTrigger(str, enum.Enum):
    CONTINUOUS = "CONTINUOUS"
    MOTION = "MOTION"
    AI_EVENT = "AI_EVENT"
    MANUAL = "MANUAL"


class Recording(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "recordings"

    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Integer, default=0, nullable=False)
    trigger_type: Mapped[RecordingTrigger] = mapped_column(Enum(RecordingTrigger), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Evidence protection (section 32) — protected recordings are excluded from retention cleanup.
    is_protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    protection_notes: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    incident_number: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    protected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    protected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
