import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Notification(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    """In-app / push notification feed for a user (mobile push delivery is a pluggable
    sender invoked from app.services.notification_service — see that module for the
    current status of push delivery)."""

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    alert_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("alerts.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False, default="ALERT")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
