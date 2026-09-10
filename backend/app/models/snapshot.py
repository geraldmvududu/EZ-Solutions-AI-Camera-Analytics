import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Snapshot(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "snapshots"

    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"), nullable=True, index=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
