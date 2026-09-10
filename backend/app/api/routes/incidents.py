import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.deps import require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.alert import Alert
from app.models.incident import Incident, IncidentStatus
from app.models.user import User
from app.schemas.incident import IncidentCreate, IncidentResponse, IncidentUpdate

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentResponse])
def list_incidents(
    status_filter: IncidentStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> list[Incident]:
    query = db.query(Incident)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Incident.tenant_id == tenant_id)
    if status_filter:
        query = query.filter(Incident.status == status_filter)
    return query.order_by(Incident.created_at.desc()).all()


def _get_owned_incident(db: Session, incident_id: uuid.UUID, user: User) -> Incident:
    incident = db.get(Incident, incident_id)
    tenant_id = tenant_filter_value(user)
    if incident is None or (tenant_id and incident.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> Incident:
    return _get_owned_incident(db, incident_id, user)


def _resolve_alerts(db: Session, alert_ids: list[uuid.UUID], tenant_id: uuid.UUID) -> list[Alert]:
    if not alert_ids:
        return []
    alerts = db.query(Alert).filter(Alert.id.in_(alert_ids), Alert.tenant_id == tenant_id).all()
    if len(alerts) != len(set(alert_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more alerts not found")
    return alerts


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_INCIDENTS)),
) -> Incident:
    incident = Incident(
        tenant_id=user.tenant_id,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        camera_id=payload.camera_id,
        assigned_user_id=payload.assigned_user_id,
    )
    incident.related_alerts = _resolve_alerts(db, payload.alert_ids, user.tenant_id)
    db.add(incident)
    db.commit()
    db.refresh(incident)

    log_action(db, action="INCIDENT_CREATED", tenant_id=user.tenant_id, user_id=user.id, resource_type="incident", resource_id=str(incident.id), details={"title": incident.title})
    return incident


@router.patch("/{incident_id}", response_model=IncidentResponse)
def update_incident(
    incident_id: uuid.UUID,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_INCIDENTS)),
) -> Incident:
    incident = _get_owned_incident(db, incident_id, user)
    data = payload.model_dump(exclude_unset=True)

    alert_ids = data.pop("alert_ids", None)
    if alert_ids is not None:
        incident.related_alerts = _resolve_alerts(db, alert_ids, user.tenant_id)

    for field, value in data.items():
        setattr(incident, field, value)

    if data.get("status") in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) and incident.closed_at is None:
        incident.closed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(incident)

    log_action(db, action="INCIDENT_UPDATED", tenant_id=user.tenant_id, user_id=user.id, resource_type="incident", resource_id=str(incident.id), details=data)
    return incident
