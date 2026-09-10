import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin, utcnow


class HealthStatus(str, enum.Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class SystemHealthCheck(Base, UUIDPKMixin):
    """Historical record of a point-in-time health check for one component. Live status
    is computed on demand by app.services.health_service and only persisted here when
    it changes, so this table doubles as a status-change audit trail."""

    __tablename__ = "system_health"

    component: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[HealthStatus] = mapped_column(Enum(HealthStatus), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
