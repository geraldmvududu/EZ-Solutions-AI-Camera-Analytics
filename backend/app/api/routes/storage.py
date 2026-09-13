from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.user import User
from app.schemas.storage import StorageUsageResponse
from app.services.storage_service import get_storage_usage

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/usage", response_model=StorageUsageResponse)
def get_usage(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_REPORTS)),
) -> StorageUsageResponse:
    return get_storage_usage(db, tenant_filter_value(user))
