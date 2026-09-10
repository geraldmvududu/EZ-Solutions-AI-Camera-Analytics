import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware(value: datetime) -> datetime:
    """SQLite (used in local dev/tests) drops tzinfo on round-trip even for
    DateTime(timezone=True) columns; Postgres (production) does not. Normalize here so
    comparisons against datetime.now(timezone.utc) work identically on both backends."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class TenantScopedMixin:
    """Adds a tenant_id column. Every query against a tenant-scoped model MUST filter by
    the current user's tenant_id — see app.core.deps.require_tenant_scope and
    app.services.tenant_scope. This is what enforces multi-tenant isolation (section 44)."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
