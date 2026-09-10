import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Table, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin
from app.models.event import EventSeverity

incident_alerts = Table(
    "incident_alerts",
    Base.metadata,
    Column("incident_id", Uuid, ForeignKey("incidents.id"), primary_key=True),
    Column("alert_id", Uuid, ForeignKey("alerts.id"), primary_key=True),
)


class IncidentStatus(str, enum.Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    CONTAINED = "CONTAINED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Incident(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "incidents"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), nullable=False, default="")
    severity: Mapped[EventSeverity] = mapped_column(Enum(EventSeverity), nullable=False)
    camera_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    status: Mapped[IncidentStatus] = mapped_column(Enum(IncidentStatus), default=IncidentStatus.OPEN, nullable=False, index=True)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolution: Mapped[str] = mapped_column(String(4000), nullable=False, default="")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    related_alerts = relationship("Alert", secondary=incident_alerts, lazy="selectin")
