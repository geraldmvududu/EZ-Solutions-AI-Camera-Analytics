import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.deps import require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.alert import Alert, AlertStatus
from app.models.event import EventSeverity
from app.models.user import User
from app.schemas.alert import AlertResponse, AlertUpdate

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
def list_alerts(
    camera_id: uuid.UUID | None = None,
    status_filter: AlertStatus | None = Query(None, alias="status"),
    severity: EventSeverity | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> list[Alert]:
    query = db.query(Alert)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Alert.tenant_id == tenant_id)
    if camera_id:
        query = query.filter(Alert.camera_id == camera_id)
    if status_filter:
        query = query.filter(Alert.status == status_filter)
    if severity:
        query = query.filter(Alert.severity == severity)
    return query.order_by(Alert.created_at.desc()).offset(offset).limit(limit).all()


def _get_owned_alert(db: Session, alert_id: uuid.UUID, user: User) -> Alert:
    alert = db.get(Alert, alert_id)
    tenant_id = tenant_filter_value(user)
    if alert is None or (tenant_id and alert.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> Alert:
    return _get_owned_alert(db, alert_id, user)


@router.patch("/{alert_id}", response_model=AlertResponse)
def update_alert(
    alert_id: uuid.UUID,
    payload: AlertUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_ALERTS)),
) -> Alert:
    alert = _get_owned_alert(db, alert_id, user)
    data = payload.model_dump(exclude_unset=True)

    if "status" in data:
        alert.status = data["status"]
        now = datetime.now(timezone.utc)
        if alert.status == AlertStatus.ACKNOWLEDGED and alert.acknowledged_at is None:
            alert.acknowledged_at = now
        if alert.status in (AlertStatus.RESOLVED, AlertStatus.FALSE_POSITIVE):
            alert.resolved_at = now
    if "assigned_user_id" in data:
        alert.assigned_user_id = data["assigned_user_id"]
    if "notes" in data:
        alert.notes = data["notes"]

    db.commit()
    db.refresh(alert)

    log_action(
        db, action="ALERT_UPDATED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="alert", resource_id=str(alert.id), details=data,
    )
    return alert
