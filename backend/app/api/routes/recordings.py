import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.deps import require_internal_service, require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.recording import Recording
from app.models.user import User
from app.schemas.recording import RecordingCreate, RecordingProtect, RecordingResponse

router = APIRouter(prefix="/recordings", tags=["recordings"])


@router.get("", response_model=list[RecordingResponse])
def list_recordings(
    camera_id: uuid.UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    is_protected: bool | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_RECORDINGS)),
) -> list[Recording]:
    query = db.query(Recording)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Recording.tenant_id == tenant_id)
    if camera_id:
        query = query.filter(Recording.camera_id == camera_id)
    if start:
        query = query.filter(Recording.started_at >= start)
    if end:
        query = query.filter(Recording.started_at <= end)
    if is_protected is not None:
        query = query.filter(Recording.is_protected == is_protected)
    return query.order_by(Recording.started_at.desc()).offset(offset).limit(limit).all()


def _get_owned_recording(db: Session, recording_id: uuid.UUID, user: User) -> Recording:
    recording = db.get(Recording, recording_id)
    tenant_id = tenant_filter_value(user)
    if recording is None or (tenant_id and recording.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    return recording


@router.get("/{recording_id}", response_model=RecordingResponse)
def get_recording(
    recording_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_RECORDINGS)),
) -> Recording:
    return _get_owned_recording(db, recording_id, user)


@router.get("/{recording_id}/download")
def download_recording(
    recording_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.DOWNLOAD_RECORDINGS)),
) -> FileResponse:
    recording = _get_owned_recording(db, recording_id, user)
    if not os.path.isfile(recording.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording file missing from storage")

    log_action(
        db, action="RECORDING_DOWNLOADED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="recording", resource_id=str(recording.id),
        ip_address=request.client.host if request.client else "",
    )
    return FileResponse(recording.file_path, media_type="video/mp4", filename=os.path.basename(recording.file_path))


@router.post("/{recording_id}/protect", response_model=RecordingResponse)
def protect_recording(
    recording_id: uuid.UUID,
    payload: RecordingProtect,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_INCIDENTS)),
) -> Recording:
    recording = _get_owned_recording(db, recording_id, user)
    recording.is_protected = True
    recording.protection_notes = payload.protection_notes
    recording.incident_number = payload.incident_number
    recording.protected_by_user_id = user.id
    recording.protected_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(recording)

    log_action(
        db, action="EVIDENCE_LOCKED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="recording", resource_id=str(recording.id),
        details={"incident_number": payload.incident_number},
    )
    return recording


@router.post("/{recording_id}/unprotect", response_model=RecordingResponse)
def unprotect_recording(
    recording_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_INCIDENTS)),
) -> Recording:
    recording = _get_owned_recording(db, recording_id, user)
    recording.is_protected = False
    recording.protected_by_user_id = None
    recording.protected_at = None
    db.commit()
    db.refresh(recording)

    log_action(
        db, action="EVIDENCE_RELEASED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="recording", resource_id=str(recording.id),
    )
    return recording


@router.post("", response_model=RecordingResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_internal_service)])
def create_recording(payload: RecordingCreate, db: Session = Depends(get_db)) -> Recording:
    from app.models.camera import Camera

    camera = db.get(Camera, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    recording = Recording(tenant_id=camera.tenant_id, **payload.model_dump())
    db.add(recording)
    db.commit()
    db.refresh(recording)
    return recording
