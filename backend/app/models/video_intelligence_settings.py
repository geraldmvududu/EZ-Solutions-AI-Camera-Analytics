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
    # AI Video Intelligence Phase 2 (section 6) — tenant-wide kill switch, same family
    # as the three above. Has no effect on a camera without
    # Camera.multi_class_detection_enabled, since HOG never emits BACKPACK/BAG/SUITCASE
    # detections for the ASSET_ZONE check to see.
    theft_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.6, nullable=False)
    pre_event_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    post_event_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    # HH:MM, used only for compute_risk_score's after-hours bonus (violation_service.py)
    # — independent of any per-rule time window an admin configures in the rule builder.
    business_hours_start: Mapped[str] = mapped_column(String(5), default="07:00", nullable=False)
    business_hours_end: Mapped[str] = mapped_column(String(5), default="18:00", nullable=False)
    # Real bug found live on the deployed VM: violation_service.py's always-incident
    # dispatch (GATE_JUMPING_DETECTED/TAILGATING_DETECTED/RESTRICTED_AREA_VIOLATION/
    # POTENTIAL_THEFT_DETECTED) created a brand-new Incident every single time one of
    # those event types fired, with no throttling of its own — the same gap
    # AIRule.cooldown_seconds fixed for Alerts, one layer up. A looping test video
    # replaying the same gate-jump content every loop pass produced a new Incident
    # every time the underlying event's own (already-cooled-down) tripwire check fired.
    # Scoped per (camera, incident_type) in violation_service.py — a genuinely
    # different incident TYPE on the same camera still gets its own Incident.
    incident_cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    # Master Development Prompt Phase 1, "Multi-event Incident Correlation" — a real
    # correlation window, distinct from and complementary to incident_cooldown_seconds
    # above: the cooldown suppresses a same-camera/same-type repeat outright (the
    # looping-test-video fix), while this window MERGES a later event of a DIFFERENT
    # type for the SAME tracked person/object into the already-open incident instead of
    # creating a second one (the master prompt's own worked example: person detected ->
    # entered zone -> loitered -> object removed becoming one incident, not four).
    # Deliberately shorter than incident_cooldown_seconds' 300s default — correlation
    # requires the SAME tracking_id/person_id, a much stronger signal than the coarse
    # cooldown's camera+type-only scope, so a shorter window is appropriate.
    correlation_window_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
