import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class EventType(str, enum.Enum):
    PERSON_DETECTED = "PERSON_DETECTED"
    VEHICLE_DETECTED = "VEHICLE_DETECTED"
    MOTION_DETECTED = "MOTION_DETECTED"
    TRIPWIRE_VIOLATION = "TRIPWIRE_VIOLATION"
    INTRUSION_DETECTED = "INTRUSION_DETECTED"
    LOITERING_DETECTED = "LOITERING_DETECTED"
    CAMERA_OFFLINE = "CAMERA_OFFLINE"
    CAMERA_ONLINE = "CAMERA_ONLINE"
    RECORDING_FAILURE = "RECORDING_FAILURE"
    AI_DETECTION = "AI_DETECTION"
    FACE_RECOGNIZED = "FACE_RECOGNIZED"
    UNKNOWN_FACE_DETECTED = "UNKNOWN_FACE_DETECTED"
    # AI Video Intelligence Phase 1 (sections 4/5/8)
    GATE_JUMPING_DETECTED = "GATE_JUMPING_DETECTED"
    TAILGATING_DETECTED = "TAILGATING_DETECTED"
    RESTRICTED_AREA_VIOLATION = "RESTRICTED_AREA_VIOLATION"
    # AI Video Intelligence Phase 2 (section 6): fires only when a camera has a real
    # multi-class detector enabled (Camera.multi_class_detection_enabled) — see
    # worker.py's ASSET_ZONE branch and CLAUDE.md for the honest scope of this
    # detection (backpack/handbag/suitcase only — COCO has no generic box/package
    # class).
    POTENTIAL_THEFT_DETECTED = "POTENTIAL_THEFT_DETECTED"


class EventSeverity(str, enum.Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventReviewStatus(str, enum.Enum):
    UNREVIEWED = "UNREVIEWED"
    REVIEWED = "REVIEWED"


class EventCategory(str, enum.Enum):
    """Event-First Cloud Storage Phase 1 (section 14) — a coarse grouping over
    EventType for dashboard filtering. Computed once at event-creation time from
    _EVENT_TYPE_CATEGORY (app/services/event_classification.py) and stored as an
    indexed column so filtering by category is a real indexed query, not a per-row
    Python computation on every list request."""

    SECURITY = "SECURITY"
    PEOPLE = "PEOPLE"
    VEHICLES = "VEHICLES"
    SAFETY = "SAFETY"
    OPERATIONS = "OPERATIONS"


class Event(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "events"

    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False, index=True)
    severity: Mapped[EventSeverity] = mapped_column(Enum(EventSeverity), default=EventSeverity.INFO, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")

    # use_alter=True on detection/snapshot/recording: these three plus events form a
    # reference cycle (see app/models/detection.py's comment) — Postgres enforces FK
    # targets at CREATE TABLE time, so these are deferred to a post-creation ALTER
    # TABLE. zone/tripwire aren't part of the cycle and don't need this.
    detection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detections.id", use_alter=True, name="fk_events_detection_id"), nullable=True
    )
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    tripwire_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tripwires.id"), nullable=True)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("snapshots.id", use_alter=True, name="fk_events_snapshot_id"), nullable=True
    )
    recording_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recordings.id", use_alter=True, name="fk_events_recording_id"), nullable=True
    )

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    event_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Event-First Cloud Storage Phase 1 (sections 3/13/14) — a plain Event (e.g.
    # PERSON_DETECTED) never automatically becomes an Incident (see
    # violation_service.py's _ALWAYS_INCIDENT_EVENT_TYPES), so before this it had no
    # review workflow of its own at all — only Incidents/Alerts did.
    status: Mapped[EventReviewStatus] = mapped_column(
        Enum(EventReviewStatus), default=EventReviewStatus.UNREVIEWED, nullable=False, index=True
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    event_category: Mapped[EventCategory] = mapped_column(
        Enum(EventCategory), default=EventCategory.OPERATIONS, nullable=False, index=True
    )
