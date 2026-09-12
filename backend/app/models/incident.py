import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Table, Uuid
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

    # AI Video Intelligence Phase 1 (sections 19/26/33/39). incident_type is a free-form
    # category label (e.g. "GATE_JUMPING") for dashboard grouping/filtering — kept as a
    # plain string rather than a hard enum FK since it mirrors an EventType value and
    # new categories will be added in later phases without a migration each time.
    incident_type: Mapped[str] = mapped_column(String(100), nullable=False, default="", index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 0-100, alert-prioritization only — never proof that a violation actually
    # occurred (see compute_risk_score in app/services/violation_service.py).
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # CONFIRMED/FALSE_POSITIVE/REQUIRES_INVESTIGATION/DISMISSED/ESCALATED — same
    # vocabulary as FaceRecognitionEvent.review_decision. Stored for false-positive-rate
    # reporting only; never used to auto-retrain any model (section 26).
    review_decision: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    evidence_clip_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Set by app/services/violation_service.py at auto-creation time, for both incident
    # paths. Evidence-clip lookup (GET /incidents/internal/pending-evidence-clips) goes
    # through this directly rather than through related_alerts — an "always-incident"
    # event type (gate-jumping/tailgating/restricted-area) is created regardless of
    # whether any AIRule matched it, so it may have zero related Alerts; relying on an
    # Alert join would silently skip evidence-clip generation for those tenants.
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"), nullable=True)

    related_alerts = relationship("Alert", secondary=incident_alerts, lazy="selectin")
