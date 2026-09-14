import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class LicensePlate(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    """Master Development Prompt Phase 1, "License Plate Reading (ANPR)" — one real
    plate-read attempt, mirroring FaceRecognitionEvent's role exactly: links 1:1 to a
    generic `Event` row (event_id) so it rides the existing rule-engine/alert/
    WebSocket/notification pipeline with zero duplicate plumbing. This table only
    holds the ANPR-specific detail that pipeline doesn't model — the raw plate text
    read, which vehicle class it came from, and whether a VehicleWatchlist entry
    matched at read time (watchlist_id is nullable: most sightings match nothing)."""

    __tablename__ = "license_plates"

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    watchlist_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicle_watchlists.id"), nullable=True, index=True)

    plate_text: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    vehicle_type: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tracking_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("snapshots.id"), nullable=True, index=True)
    recording_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recordings.id"), nullable=True, index=True)
