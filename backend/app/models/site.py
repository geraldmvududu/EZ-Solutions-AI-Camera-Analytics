from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Site(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    """Event-First Cloud Storage Phase 1 (section 1): the layer the spec calls
    "Site" between a tenant ("Customer") and its cameras — a tenant with cameras in
    more than one physical location. Every existing camera predates this model, so
    the migration backfills one "Default Site" per tenant and points all of that
    tenant's existing cameras at it (Camera.site_id is nullable specifically so this
    backfill — and any future camera created without picking a site — never breaks
    existing functionality)."""

    __tablename__ = "sites"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
