"""Master Development Prompt Phase 1, "License Plate Reading (ANPR)" — mirrors
faces.py's enrollment/recognition split: a tenant-managed VehicleWatchlist (like
FaceProfile/Person) and a real-time recognize endpoint (like /faces/recognize) that
rides the existing event/rule/alert/notification/incident pipeline with zero new
dispatch code beyond registering VEHICLE_WATCHLIST_MATCH as an always-incident type
(see violation_service.py).
"""

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.deps import require_internal_service, require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.camera import Camera
from app.models.event import EventSeverity, EventType
from app.models.license_plate import LicensePlate
from app.models.user import User
from app.models.vehicle_watchlist import VehicleWatchlist, VehicleWatchlistStatus
from app.schemas.event import EventCreate
from app.schemas.vehicle import (
    LicensePlateResponse,
    PlateRecognizeRequest,
    PlateRecognizeResult,
    VehicleWatchlistCreate,
    VehicleWatchlistResponse,
    VehicleWatchlistUpdate,
)

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


def _normalize_plate(raw: str) -> str:
    """Strips whitespace/punctuation and uppercases — matches exactly what
    ai-engine/app/core/plate_reader.py::clean_plate_text produces from a real OCR read,
    so a watchlist entry an admin types as "CA 123-456" actually matches a real
    sighting of "CA123456" instead of silently never matching anything."""
    return re.sub(r"[^A-Z0-9]", "", raw.upper())

_WATCHLIST_SEVERITY = {
    VehicleWatchlistStatus.BLACKLISTED: EventSeverity.CRITICAL,
    VehicleWatchlistStatus.WATCHLIST: EventSeverity.HIGH,
}
_ALERT_WORTHY_STATUSES = set(_WATCHLIST_SEVERITY)


@router.get("/watchlist", response_model=list[VehicleWatchlistResponse])
def list_watchlist(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_VEHICLE_EVENTS)),
) -> list[VehicleWatchlist]:
    query = db.query(VehicleWatchlist)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(VehicleWatchlist.tenant_id == tenant_id)
    return query.order_by(VehicleWatchlist.created_at.desc()).all()


def _get_owned_watchlist_entry(db: Session, entry_id: uuid.UUID, user: User) -> VehicleWatchlist:
    entry = db.get(VehicleWatchlist, entry_id)
    tenant_id = tenant_filter_value(user)
    if entry is None or (tenant_id and entry.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist entry not found")
    return entry


@router.post("/watchlist", response_model=VehicleWatchlistResponse, status_code=status.HTTP_201_CREATED)
def create_watchlist_entry(
    payload: VehicleWatchlistCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_VEHICLE_WATCHLIST)),
) -> VehicleWatchlist:
    entry = VehicleWatchlist(
        tenant_id=user.tenant_id,
        plate_text=_normalize_plate(payload.plate_text),
        status=payload.status,
        description=payload.description,
        notes=payload.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    log_action(
        db, action="VEHICLE_WATCHLIST_CREATED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="vehicle_watchlist", resource_id=str(entry.id),
        details={"plate_text": entry.plate_text, "status": entry.status.value},
    )
    return entry


@router.patch("/watchlist/{entry_id}", response_model=VehicleWatchlistResponse)
def update_watchlist_entry(
    entry_id: uuid.UUID,
    payload: VehicleWatchlistUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_VEHICLE_WATCHLIST)),
) -> VehicleWatchlist:
    entry = _get_owned_watchlist_entry(db, entry_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    log_action(
        db, action="VEHICLE_WATCHLIST_UPDATED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="vehicle_watchlist", resource_id=str(entry.id), details={"plate_text": entry.plate_text},
    )
    return entry


@router.delete("/watchlist/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist_entry(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_VEHICLE_WATCHLIST)),
) -> None:
    entry = _get_owned_watchlist_entry(db, entry_id, user)
    log_action(
        db, action="VEHICLE_WATCHLIST_DELETED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="vehicle_watchlist", resource_id=str(entry.id), details={"plate_text": entry.plate_text},
    )
    db.delete(entry)
    db.commit()


@router.get("/plate-events", response_model=list[LicensePlateResponse])
def list_plate_events(
    camera_id: uuid.UUID | None = None,
    plate_text: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_VEHICLE_EVENTS)),
) -> list[LicensePlate]:
    """Backs the master prompt's own worked example: "show all events involving
    registration CA 123456 during the last 30 days" — filter by plate_text (+ optional
    camera/date range), return every real sighting."""
    query = db.query(LicensePlate)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(LicensePlate.tenant_id == tenant_id)
    if camera_id:
        query = query.filter(LicensePlate.camera_id == camera_id)
    if plate_text:
        query = query.filter(LicensePlate.plate_text == _normalize_plate(plate_text))
    if start:
        query = query.filter(LicensePlate.occurred_at >= start)
    if end:
        query = query.filter(LicensePlate.occurred_at <= end)
    return query.order_by(LicensePlate.occurred_at.desc()).offset(offset).limit(limit).all()


@router.post("/recognize-plate", response_model=PlateRecognizeResult, dependencies=[Depends(require_internal_service)])
async def recognize_plate(payload: PlateRecognizeRequest, db: Session = Depends(get_db)) -> PlateRecognizeResult:
    """Called by ai-engine (app/core/plate_reader.py) for one real, already-regex-
    sanity-checked plate read. Always creates a plain LICENSE_PLATE_DETECTED sighting
    log entry (supports "show all sightings of this plate" regardless of watchlist
    status); additionally creates a VEHICLE_WATCHLIST_MATCH event — which
    violation_service.py's always-incident dispatch picks up with zero new code — only
    when the plate matches an ACTIVE VehicleWatchlist row marked WATCHLIST/
    BLACKLISTED."""
    from app.api.routes.events import create_event_and_process

    camera = db.get(Camera, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    tenant_id = camera.tenant_id
    plate_text = _normalize_plate(payload.plate_text)

    watchlist_entry = (
        db.query(VehicleWatchlist)
        .filter(
            VehicleWatchlist.tenant_id == tenant_id,
            VehicleWatchlist.plate_text == plate_text,
            VehicleWatchlist.is_active.is_(True),
        )
        .first()
    )

    base_metadata = {
        "plate_text": plate_text,
        "vehicle_type": payload.vehicle_type,
        "confidence": payload.confidence,
        "tracking_id": payload.tracking_id,
        "watchlist_status": watchlist_entry.status.value if watchlist_entry else None,
    }

    sighting_event = await create_event_and_process(
        db, camera,
        EventCreate(
            camera_id=camera.id,
            event_type=EventType.LICENSE_PLATE_DETECTED,
            severity=EventSeverity.INFO,
            description=f"License plate '{plate_text}' read on camera '{camera.name}'.",
            occurred_at=payload.occurred_at,
            snapshot_id=payload.snapshot_id,
            recording_id=payload.recording_id,
            event_metadata=base_metadata,
        ),
    )

    license_plate = LicensePlate(
        tenant_id=tenant_id,
        event_id=sighting_event.id,
        camera_id=camera.id,
        watchlist_id=watchlist_entry.id if watchlist_entry else None,
        plate_text=plate_text,
        vehicle_type=payload.vehicle_type,
        confidence=payload.confidence,
        tracking_id=payload.tracking_id,
        occurred_at=payload.occurred_at,
        snapshot_id=payload.snapshot_id,
        recording_id=payload.recording_id,
    )
    db.add(license_plate)
    db.commit()

    result_event_id = sighting_event.id
    if watchlist_entry is not None and watchlist_entry.status in _ALERT_WORTHY_STATUSES:
        match_event = await create_event_and_process(
            db, camera,
            EventCreate(
                camera_id=camera.id,
                event_type=EventType.VEHICLE_WATCHLIST_MATCH,
                severity=_WATCHLIST_SEVERITY[watchlist_entry.status],
                description=f"Vehicle watchlist match: plate '{plate_text}' ({watchlist_entry.status.value}).",
                occurred_at=payload.occurred_at,
                snapshot_id=payload.snapshot_id,
                recording_id=payload.recording_id,
                event_metadata=base_metadata,
            ),
        )
        result_event_id = match_event.id

    return PlateRecognizeResult(
        plate_text=plate_text,
        watchlist_status=watchlist_entry.status.value if watchlist_entry else None,
        event_id=result_event_id,
    )
