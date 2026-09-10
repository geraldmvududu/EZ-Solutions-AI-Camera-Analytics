import uuid
from datetime import datetime

from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import require_internal_service, require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.camera import Camera
from app.models.event import Event, EventSeverity, EventType
from app.models.user import User
from app.schemas.event import EventCreate, EventResponse
from app.services import rule_engine
from app.services.notification_service import notify_users_of_alert
from app.services.ws_manager import manager

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventResponse])
def list_events(
    camera_id: uuid.UUID | None = None,
    event_type: EventType | None = None,
    severity: EventSeverity | None = None,
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


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_internal_service)])
async def create_event(payload: EventCreate, db: Session = Depends(get_db)) -> Event:
    """Called by the AI engine (or the camera-status watchdog) whenever a real event
    occurs. Runs the rule engine synchronously and broadcasts the result over the
    tenant's WebSocket channel so the dashboard updates without a page refresh."""
    camera = db.get(Camera, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    event = Event(tenant_id=camera.tenant_id, **payload.model_dump())
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

    return event
