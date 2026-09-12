from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class VideoIntelligenceSettings(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    """AI Video Intelligence Phase 1 tenant settings (section 35). One row per tenant,
    same seed-on-first-use pattern as FaceRecognitionSettings
    (app/api/routes/video_intelligence.py::_get_or_create_settings)."""

    __tablename__ = "video_intelligence_settings"

    gate_jumping_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tailgating_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    restricted_area_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.6, nullable=False)
    pre_event_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    post_event_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    # HH:MM, used only for compute_risk_score's after-hours bonus (violation_service.py)
    # — independent of any per-rule time window an admin configures in the rule builder.
    business_hours_start: Mapped[str] = mapped_column(String(5), default="07:00", nullable=False)
    business_hours_end: Mapped[str] = mapped_column(String(5), default="18:00", nullable=False)
