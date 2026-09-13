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
    FACE_DETECTION = "FACE_DETECTION"
    FACE_EXCLUSION = "FACE_EXCLUSION"
    # AI Video Intelligence Phase 1 (section 5): functionally identical to LOITERING
    # (same dwell-time mechanism, ai-engine/app/core/zones.py::LoiteringTracker is
    # already zone-type-agnostic) but reported/dashboarded as its own category —
    # RESTRICTED_AREA_VIOLATION events, not LOITERING_DETECTED ones.
    RESTRICTED_AREA = "RESTRICTED_AREA"
    # AI Video Intelligence Phase 2 (section 6, "potential theft / unauthorized object
    # removal"): a monitored asset area (shelf, display case, loading dock). Reuses the
    # same loitering_threshold_seconds column as "minimum seconds an object must be
    # continuously present before its removal counts as a violation" — see
    # ai-engine/app/core/object_tracking.py::AssetZoneTracker.
    ASSET_ZONE = "ASSET_ZONE"


class Zone(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "zones"

    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    zone_type: Mapped[ZoneType] = mapped_column(Enum(ZoneType), nullable=False)

    # List of [x, y] points, normalized 0-1, forming a closed polygon.
    polygon: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    loitering_threshold_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
