import uuid
from datetime import datetime, timezone

from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import require_internal_service, require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.camera import Camera
from app.models.event import Event, EventCategory, EventReviewStatus, EventSeverity, EventType
from app.models.user import User
from app.schemas.event import EventCreate, EventNotesUpdate, EventResponse, EventReviewUpdate
from app.core.audit import log_action
from app.services import rule_engine
from app.services.event_classification import classify_event
from app.services.notification_service import notify_users_of_alert
from app.services.violation_service import maybe_create_violation_incident
from app.services.ws_manager import manager

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventResponse])
def list_events(
    camera_id: uuid.UUID | None = None,
    event_type: EventType | None = None,
    severity: EventSeverity | None = None,
    event_category: EventCategory | None = None,
    status_filter: EventReviewStatus | None = Query(None, alias="status"),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> list[Event]:
    query = db.query(Event)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Event.tenant_id == tenant_id)
    if camera_id:
        query = query.filter(Event.camera_id == camera_id)
    if event_type:
        query = query.filter(Event.event_type == event_type)
    if severity:
        query = query.filter(Event.severity == severity)
    if event_category:
        query = query.filter(Event.event_category == event_category)
    if status_filter:
        query = query.filter(Event.status == status_filter)
    if start:
        query = query.filter(Event.occurred_at >= start)
    if end:
        query = query.filter(Event.occurred_at <= end)
    return query.order_by(Event.occurred_at.desc()).offset(offset).limit(limit).all()


@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> Event:
    event = db.get(Event, event_id)
    tenant_id = tenant_filter_value(user)
    if event is None or (tenant_id and event.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


def _get_owned_event(db: Session, event_id: uuid.UUID, user: User) -> Event:
    event = db.get(Event, event_id)
    tenant_id = tenant_filter_value(user)
    if event is None or (tenant_id and event.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@router.post("/{event_id}/review", response_model=EventResponse)
def review_event(
    event_id: uuid.UUID,
    payload: EventReviewUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_ALERTS)),
) -> Event:
    """Event-First Cloud Storage Phase 1 (sections 3/13): a plain Event (e.g.
    PERSON_DETECTED) never automatically becomes an Incident, so this is its own
    review workflow — separate from Incident.status and Alert.status, which already
    existed before this phase."""
    event = _get_owned_event(db, event_id, user)
    event.status = payload.status
    event.reviewed_by_user_id = user.id if payload.status == EventReviewStatus.REVIEWED else None
    event.reviewed_at = datetime.now(timezone.utc) if payload.status == EventReviewStatus.REVIEWED else None
    db.commit()
    db.refresh(event)
    return event


@router.post("/{event_id}/notes", response_model=EventResponse)
def add_event_notes(
    event_id: uuid.UUID,
    payload: EventNotesUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_ALERTS)),
) -> Event:
    event = _get_owned_event(db, event_id, user)
    event.notes = payload.notes
    db.commit()
    db.refresh(event)
    return event


async def create_event_and_process(db: Session, camera: Camera, payload: EventCreate) -> Event:
    """The real event-ingestion pipeline: create the Event, run the rule engine, broadcast
    over the tenant's WebSocket channel, notify eligible users, and auto-create an Incident
    when warranted. Factored out of the create_event route so a second internal caller —
    the heartbeat endpoint's OFFLINE->ONLINE transition (backend/app/api/routes/
    cameras.py::camera_heartbeat) — gets the exact same real pipeline (a CAMERA_ONLINE event
    genuinely goes through rule_engine/notifications like any other) rather than a
    hand-rolled duplicate or a bare DB insert with no downstream effect."""
    event = Event(tenant_id=camera.tenant_id, event_category=classify_event(payload.event_type), **payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)

    alerts = rule_engine.evaluate_event(db, event)

    await manager.broadcast(camera.tenant_id, {
        "type": "event",
        "event": EventResponse.model_validate(event).model_dump(mode="json"),
    })
    for alert in alerts:
        from app.schemas.alert import AlertResponse

        await manager.broadcast(camera.tenant_id, {
            "type": "alert",
            "alert": AlertResponse.model_validate(alert).model_dump(mode="json"),
        })
        # notify_users_of_alert does blocking DB + HTTP work (Expo push API) — run off
        # the event loop thread so one alert's push delivery can't stall other requests.
        await to_thread.run_sync(notify_users_of_alert, db, alert, camera)

    incident = maybe_create_violation_incident(db, event, alerts, camera)
    if incident is not None:
        from app.schemas.incident import IncidentResponse

        log_action(
            db, action="INCIDENT_AUTO_CREATED", tenant_id=camera.tenant_id,
            resource_type="incident", resource_id=str(incident.id),
            details={"event_id": str(event.id), "title": incident.title},
        )
        await manager.broadcast(camera.tenant_id, {
            "type": "incident",
            "incident": IncidentResponse.model_validate(incident).model_dump(mode="json"),
        })

    return event


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_internal_service)])
async def create_event(payload: EventCreate, db: Session = Depends(get_db)) -> Event:
    """Called by the AI engine or worker.py's camera-health check whenever a real event
    occurs."""
    camera = db.get(Camera, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    return await create_event_and_process(db, camera, payload)
