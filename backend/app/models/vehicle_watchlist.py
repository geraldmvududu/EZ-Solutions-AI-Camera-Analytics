import enum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class VehicleWatchlistStatus(str, enum.Enum):
    AUTHORIZED = "AUTHORIZED"
    UNAUTHORIZED = "UNAUTHORIZED"
    WATCHLIST = "WATCHLIST"
    BLACKLISTED = "BLACKLISTED"


class VehicleWatchlist(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    """Master Development Prompt Phase 1, "License Plate Reading (ANPR)" — mirrors
    Person's category/status role for vehicles: a plate number plus a status an admin
    assigns. A plate NOT in this table is simply unknown (a plain LICENSE_PLATE_DETECTED
    sighting, no watchlist match) — this table only ever holds plates someone
    deliberately registered an opinion about."""

    __tablename__ = "vehicle_watchlists"

    plate_text: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[VehicleWatchlistStatus] = mapped_column(Enum(VehicleWatchlistStatus), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    notes: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
