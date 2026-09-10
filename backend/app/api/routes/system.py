from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, tenant_filter_value
from app.database import get_db
from app.models.user import User
from app.schemas.system import DashboardStats, SystemHealthResponse
from app.services import health_service, stats_service

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=SystemHealthResponse)
def system_health(db: Session = Depends(get_db)) -> SystemHealthResponse:
    """Intentionally unauthenticated — this is what Docker's healthcheck and the
    nginx upstream probe hit, and it only exposes component status, not tenant data."""
    return health_service.get_system_health(db)


@router.get("/dashboard-stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> DashboardStats:
    return stats_service.get_dashboard_stats(db, tenant_filter_value(user))
