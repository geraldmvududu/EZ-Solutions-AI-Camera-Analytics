from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class Tenant(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="lab", nullable=False)
