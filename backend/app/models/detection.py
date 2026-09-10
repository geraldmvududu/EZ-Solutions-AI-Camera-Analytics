import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class ObjectType(str, enum.Enum):
    PERSON = "PERSON"
    CAR = "CAR"
    TRUCK = "TRUCK"
    BUS = "BUS"
    MOTORCYCLE = "MOTORCYCLE"
    BICYCLE = "BICYCLE"
    ANIMAL = "ANIMAL"
    BACKPACK = "BACKPACK"
    BAG = "BAG"
    SUITCASE = "SUITCASE"


class Detection(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "detections"

    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    object_type: Mapped[ObjectType] = mapped_column(Enum(ObjectType), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Bounding box, normalized 0-1 relative to frame width/height.
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_width: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_height: Mapped[float] = mapped_column(Float, nullable=False)

    tracking_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    frame_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # use_alter=True: detections/snapshots/events/recordings form a reference cycle
    # (e.g. Snapshot -> Event -> Detection -> Snapshot), which SQLite never enforces at
    # CREATE TABLE time but Postgres does. use_alter defers these specific constraints
    # to a separate ALTER TABLE, emitted after every table exists, breaking the cycle.
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("snapshots.id", use_alter=True, name="fk_detections_snapshot_id"), nullable=True
    )
    recording_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recordings.id", use_alter=True, name="fk_detections_recording_id"), nullable=True
    )
