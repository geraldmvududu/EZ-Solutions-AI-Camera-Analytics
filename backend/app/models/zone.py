import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class ZoneType(str, enum.Enum):
    INTRUSION = "INTRUSION"
    PRIVACY = "PRIVACY"
    LOITERING = "LOITERING"


class Zone(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "zones"

    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    zone_type: Mapped[ZoneType] = mapped_column(Enum(ZoneType), nullable=False)

    # List of [x, y] points, normalized 0-1, forming a closed polygon.
    polygon: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    loitering_threshold_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
