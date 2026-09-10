import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Uuid, ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", Uuid, ForeignKey("permissions.id"), primary_key=True),
)


class Permission(Base, UUIDPKMixin):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class Role(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    permissions: Mapped[list[Permission]] = relationship(secondary=role_permissions, lazy="selectin")


class User(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    role: Mapped[Role] = relationship(lazy="selectin")
