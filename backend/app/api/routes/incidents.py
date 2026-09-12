import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from jose import JWTError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.deps import require_internal_service, require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.core.security import decode_access_token
from app.database import get_db
from app.models.alert import Alert
from app.models.event import Event
from app.models.incident import Incident, IncidentStatus
from app.models.recording import Recording
from app.models.user import User
from app.schemas.analytics import NamedCount
from app.schemas.incident import IncidentCreate, IncidentResponse, IncidentUpdate
from app.schemas.video_intelligence import EvidenceClipUpdate, IncidentSummaryResponse, PendingEvidenceClip

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


@router.get("/summary", response_model=IncidentSummaryResponse)
def get_incident_summary(
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> IncidentSummaryResponse:
    """Backs the AI Video Intelligence dashboard's "Today's Incidents" counts
    (section 22) — a real GROUP BY over Incident rows, same convention as
    app/services/analytics_service.py."""
    range_end = end or datetime.now(timezone.utc)
    range_start = start or (range_end - timedelta(days=1))

    query = db.query(Incident).filter(Incident.created_at >= range_start, Incident.created_at <= range_end)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Incident.tenant_id == tenant_id)

    by_severity_rows = query.with_entities(Incident.severity, func.count(Incident.id)).group_by(Incident.severity).all()
    by_type_rows = (
        query.filter(Incident.incident_type != "")
        .with_entities(Incident.incident_type, func.count(Incident.id))
        .group_by(Incident.incident_type)
        .all()
    )

    return IncidentSummaryResponse(
        range_start=range_start,
        range_end=range_end,
        by_severity=[NamedCount(label=sev.value if hasattr(sev, "value") else sev, count=count) for sev, count in by_severity_rows],
        by_type=[NamedCount(label=t, count=count) for t, count in by_type_rows],
    )


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


@router.get("/{incident_id}/evidence-clip")
def play_incident_evidence_clip(incident_id: uuid.UUID, token: str, db: Session = Depends(get_db)) -> FileResponse:
    """Inline playback for a <video> tag — mirrors recordings.py::play_recording's
    query-param-token pattern exactly, since a <video src="..."> can't send an
    Authorization header. Scoped by incident ID rather than a raw file path, so a user
    can only ever fetch a clip belonging to an incident they're allowed to see."""
    try:
        payload = decode_access_token(token)
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    if "view_cameras" not in {p.code for p in user.role.permissions}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: view_cameras")

    tenant_id = tenant_filter_value(user)
    incident = db.get(Incident, incident_id)
    if incident is None or (tenant_id and incident.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    if not incident.evidence_clip_path or not os.path.isfile(incident.evidence_clip_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence clip not available")

    return FileResponse(incident.evidence_clip_path, media_type="video/mp4")


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


@router.get(
    "/internal/pending-evidence-clips",
    response_model=list[PendingEvidenceClip],
    include_in_schema=False,
    dependencies=[Depends(require_internal_service)],
)
def list_pending_evidence_clips(recording_id: uuid.UUID, db: Session = Depends(get_db)) -> list[PendingEvidenceClip]:
    """Called by ai-engine's SegmentRecorder.stop() (AI Video Intelligence Phase 1,
    section 21) right after a recording finishes transcoding, to find any Incidents
    whose evidence clip still needs to be trimmed from this now-finalized file. Goes
    through Incident.source_event_id -> Event.recording_id directly rather than
    through related_alerts: an "always-incident" event type (gate-jumping/tailgating/
    restricted-area) is created regardless of whether any AIRule matched it, so it may
    have zero related Alerts — an Alert-only join would silently skip evidence-clip
    generation whenever a tenant has no matching rule configured."""
    from app.api.routes.video_intelligence import _get_or_create_settings

    recording = db.get(Recording, recording_id)
    if recording is None:
        return []

    matches = (
        db.query(Incident, Event)
        .join(Event, Event.id == Incident.source_event_id)
        .filter(Event.recording_id == recording_id, Incident.evidence_clip_path.is_(None))
        .all()
    )

    settings_by_tenant: dict[uuid.UUID, tuple[int, int]] = {}
    results: list[PendingEvidenceClip] = []
    for incident, event in matches:
        if incident.tenant_id not in settings_by_tenant:
            fr_settings = _get_or_create_settings(db, incident.tenant_id)
            settings_by_tenant[incident.tenant_id] = (fr_settings.pre_event_seconds, fr_settings.post_event_seconds)
        pre_seconds, post_seconds = settings_by_tenant[incident.tenant_id]
        results.append(
            PendingEvidenceClip(
                incident_id=incident.id,
                event_occurred_at=event.occurred_at,
                recording_started_at=recording.started_at,
                recording_file_path=recording.file_path,
                recording_duration_seconds=recording.duration_seconds,
                pre_event_seconds=pre_seconds,
                post_event_seconds=post_seconds,
            )
        )
    return results


@router.patch(
    "/{incident_id}/internal/evidence-clip",
    include_in_schema=False,
    dependencies=[Depends(require_internal_service)],
)
def set_incident_evidence_clip(incident_id: uuid.UUID, payload: EvidenceClipUpdate, db: Session = Depends(get_db)) -> dict:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    incident.evidence_clip_path = payload.evidence_clip_path
    db.commit()
    return {"id": str(incident.id), "evidence_clip_path": incident.evidence_clip_path}
