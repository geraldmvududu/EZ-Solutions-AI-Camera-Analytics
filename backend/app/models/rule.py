import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, JSON, String
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

    # Real bug found live on the deployed VM: a rule matching a frequently-recurring
    # event type (here, PERSON_DETECTED — itself already cooled down to once per 30s
    # at the ai-engine level) still got a brand-new Alert every single time that event
    # fired, since evaluate_event() had no throttling of its own at all — a rule
    # sitting on a busy looping test camera produced a fresh CRITICAL alert every
    # ~30 seconds for over an hour. Every OTHER event-creation path in this codebase
    # already learned this lesson (OBJECT_EVENT_COOLDOWN_SECONDS,
    # TRIPWIRE_VIOLATION_COOLDOWN_SECONDS, ...); the rule engine was the one place left
    # with none. Default (300s = 5 minutes) is deliberately longer than any single
    # event-level cooldown, since an Alert is meant to represent something worth a
    # human's attention, not a running tally of every qualifying event — configurable
    # per rule for an admin who genuinely wants tighter or looser re-alerting.
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
