import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import require_internal_service, require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.snapshot import Snapshot
from app.models.user import User
from app.schemas.snapshot import SnapshotCreate, SnapshotResponse

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("", response_model=list[SnapshotResponse])
def list_snapshots(
    camera_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> list[Snapshot]:
    query = db.query(Snapshot)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Snapshot.tenant_id == tenant_id)
    if camera_id:
        query = query.filter(Snapshot.camera_id == camera_id)
    if event_id:
        query = query.filter(Snapshot.event_id == event_id)
    return query.order_by(Snapshot.taken_at.desc()).offset(offset).limit(limit).all()


def _get_owned_snapshot(db: Session, snapshot_id: uuid.UUID, user: User) -> Snapshot:
    snapshot = db.get(Snapshot, snapshot_id)
    tenant_id = tenant_filter_value(user)
    if snapshot is None or (tenant_id and snapshot.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")
    return snapshot


@router.get("/{snapshot_id}/image")
def get_snapshot_image(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> FileResponse:
    snapshot = _get_owned_snapshot(db, snapshot_id, user)
    if not os.path.isfile(snapshot.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot file missing from storage")
    return FileResponse(snapshot.file_path, media_type="image/jpeg")


@router.post("", response_model=SnapshotResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_internal_service)])
def create_snapshot(payload: SnapshotCreate, db: Session = Depends(get_db)) -> Snapshot:
    from app.models.camera import Camera

    camera = db.get(Camera, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    snapshot = Snapshot(tenant_id=camera.tenant_id, **payload.model_dump())
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot
