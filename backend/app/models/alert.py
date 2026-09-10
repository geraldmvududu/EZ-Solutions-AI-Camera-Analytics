import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin
from app.models.event import EventSeverity


class AlertStatus(str, enum.Enum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class Alert(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "alerts"

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_rules.id"), nullable=True)

    alert_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[EventSeverity] = mapped_column(Enum(EventSeverity), nullable=False, index=True)
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus), default=AlertStatus.NEW, nullable=False, index=True)

    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("snapshots.id"), nullable=True)
    recording_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recordings.id"), nullable=True)

    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str] = mapped_column(String(2000), nullable=False, default="")

    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
