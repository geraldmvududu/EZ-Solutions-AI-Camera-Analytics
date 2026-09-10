import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin
from app.models.event import EventSeverity


class AIRule(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    """A security rule. `conditions` is evaluated against real incoming Events by
    app.services.rule_engine.evaluate_event() — see that module for the supported
    condition keys (event_type, camera_id, zone_id, object_type, time_start/time_end,
    days_of_week, min_confidence)."""

    __tablename__ = "ai_rules"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    conditions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    action_severity: Mapped[EventSeverity] = mapped_column(Enum(EventSeverity), nullable=False, default=EventSeverity.MEDIUM)
    action_alert_type: Mapped[str] = mapped_column(String(100), nullable=False, default="RULE_MATCH")

    camera_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
