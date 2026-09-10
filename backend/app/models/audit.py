import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin, utcnow


class AuditLog(Base, UUIDPKMixin):
    __tablename__ = "audit_logs"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="SUCCESS")
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
