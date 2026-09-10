from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.audit import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
def list_audit_logs(
    action: str | None = None,
    user_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.MANAGE_SYSTEM_SETTINGS)),
) -> list[dict]:
    query = db.query(AuditLog)
    tenant_id = tenant_filter_value(current_user)
    if tenant_id:
        query = query.filter(AuditLog.tenant_id == tenant_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if start:
        query = query.filter(AuditLog.created_at >= start)
    if end:
        query = query.filter(AuditLog.created_at <= end)

    rows = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return [
        {
            "id": str(r.id),
            "tenant_id": str(r.tenant_id) if r.tenant_id else None,
            "user_id": str(r.user_id) if r.user_id else None,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "ip_address": r.ip_address,
            "result": r.result,
            "details": r.details,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
