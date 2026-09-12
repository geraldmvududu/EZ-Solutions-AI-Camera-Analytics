import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin
from app.models.face_profile import FaceProfile


class PersonCategory(str, enum.Enum):
    EMPLOYEE = "EMPLOYEE"
    CONTRACTOR = "CONTRACTOR"
    VISITOR = "VISITOR"
    AUTHORIZED_PERSON = "AUTHORIZED_PERSON"
    WATCHLIST = "WATCHLIST"


class PersonStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class Person(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    """An enrolled individual (section 2). Never holds a raw embedding directly —
    that lives on FaceProfile, encrypted at rest. A Person can have zero face profiles
    (record created, enrollment pending/rejected) or exactly one active profile in
    the common case."""

    __tablename__ = "persons"

    external_reference: Mapped[str] = mapped_column(String(100), nullable=False, default="", index=True)
    first_name: Mapped[str] = mapped_column(String(150), nullable=False)
    last_name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[PersonCategory] = mapped_column(Enum(PersonCategory), nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    notes: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    status: Mapped[PersonStatus] = mapped_column(Enum(PersonStatus), default=PersonStatus.ACTIVE, nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    face_profiles: Mapped[list[FaceProfile]] = relationship(
        primaryjoin="Person.id == foreign(FaceProfile.person_id)", lazy="selectin", viewonly=True
    )
