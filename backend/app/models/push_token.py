import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class PushToken(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    """An Expo push token registered by the mobile app for one user's device (section
    39/40). Sent to via Expo's push service (app/services/push_service.py) — not raw
    FCM/APNs, so this works without the deployer provisioning their own Firebase/Apple
    Developer credentials."""

    __tablename__ = "push_tokens"
    __table_args__ = (UniqueConstraint("user_id", "token", name="uq_push_token_user_token"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="expo")
