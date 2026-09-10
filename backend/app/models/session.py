import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class UserSession(Base, UUIDPKMixin, TimestampMixin):
    """Tracks issued refresh tokens so sessions can be listed/revoked (mobile + web device management)."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    device_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
