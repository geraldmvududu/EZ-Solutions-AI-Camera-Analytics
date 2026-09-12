import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class TripwireDirection(str, enum.Enum):
    ENTERING = "ENTERING"
    EXITING = "EXITING"
    BOTH = "BOTH"


class Tripwire(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "tripwires"

    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Two points [[x1,y1],[x2,y2]], normalized 0-1.
    line: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    direction: Mapped[TripwireDirection] = mapped_column(Enum(TripwireDirection), default=TripwireDirection.BOTH, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # AI Video Intelligence Phase 1 (sections 4/8): opt-in per tripwire, not global —
    # gate-jump analysis only makes sense on a line actually drawn across a gate/fence,
    # not a general people-counting line, and tailgating only on a controlled entrance.
    gate_jump_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tailgating_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tailgating_window_seconds: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
