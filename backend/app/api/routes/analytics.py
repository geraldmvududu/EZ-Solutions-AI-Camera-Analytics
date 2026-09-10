import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.user import User
from app.schemas.analytics import AnalyticsSummary
from app.services.analytics_service import get_analytics_summary

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
def analytics_summary(
    start: datetime | None = None,
    end: datetime | None = None,
    camera_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_REPORTS)),
) -> AnalyticsSummary:
    return get_analytics_summary(db, tenant_filter_value(user), start, end, camera_id)
