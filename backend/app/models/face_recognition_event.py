import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class RecognitionStatus(str, enum.Enum):
    RECOGNIZED = "RECOGNIZED"
    UNKNOWN = "UNKNOWN"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class FaceRecognitionEvent(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    """One face-matching attempt (section 3/6/7). Links 1:1 to a generic `Event` row
    (event_id) so it rides the existing rule-engine/alert/WebSocket/notification
    pipeline (app/api/routes/events.py::create_event) with zero duplicate plumbing —
    this table only holds the face-specific detail that pipeline doesn't model:
    which person (if any) matched, at what confidence, and the human-review workflow.
    person_id is nullable — null means no enrolled person matched (an "unknown
    person" event, per section 7, which is explicitly NOT itself proof of anything)."""

    __tablename__ = "face_recognition_events"

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    person_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("persons.id"), nullable=True, index=True)
    face_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("face_profiles.id"), nullable=True)

    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recognition_status: Mapped[RecognitionStatus] = mapped_column(Enum(RecognitionStatus), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("snapshots.id"), nullable=True)
    recording_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recordings.id"), nullable=True)

    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    review_decision: Mapped[str] = mapped_column(String(30), nullable=False, default="")  # CONFIRMED/REJECTED/FALSE_POSITIVE/ESCALATED
    review_notes: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
