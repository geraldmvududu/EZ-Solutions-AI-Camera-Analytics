from sqlalchemy import Boolean, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class FaceRecognitionSettings(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    """One row per tenant (section 22's "Settings -> Facial Recognition" page).
    Per-camera overrides live on Camera itself (face_recognition_threshold etc.) —
    these are the tenant-wide defaults new cameras and the matcher fall back to."""

    __tablename__ = "face_recognition_settings"

    facial_recognition_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    unknown_face_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_match_threshold: Mapped[float] = mapped_column(Float, default=0.85, nullable=False)
    multi_frame_confirmation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    liveness_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recognition_cooldown_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    max_events_per_person_camera_per_hour: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    event_retention_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    snapshot_retention_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    face_profile_retention_days: Mapped[int] = mapped_column(Integer, default=365, nullable=False)
