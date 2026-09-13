from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class RetentionTier(Base, UUIDPKMixin, TimestampMixin):
    """Event-First Cloud Storage Phase 1 (section 10): a named retention preset
    (Starter/Business/Professional/Enterprise, seeded by the migration with the
    spec's own worked example values) governing how long the NEW cloud-stored
    artifacts (snapshots, non-continuous evidence recordings, incident evidence
    clips) survive before worker/app.py::cleanup_expired_cloud_evidence purges them.

    Deliberately NOT tenant-scoped — this is a small, named, platform-wide set of
    presets a Platform Administrator (SUPER_ADMIN) configures via
    GET/PUT /api/retention-tiers; Tenant.retention_tier_id then picks one. Not
    hard-coded anywhere per the spec's explicit requirement.

    This governs cloud-storage retention only. Camera.retention_days (today's
    local-recording/local-file retention, unaffected by this table) keeps governing
    local continuous-recording cleanup exactly as it did before this phase."""

    __tablename__ = "retention_tiers"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    event_metadata_days: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_days: Mapped[int] = mapped_column(Integer, nullable=False)
    video_evidence_days: Mapped[int] = mapped_column(Integer, nullable=False)
