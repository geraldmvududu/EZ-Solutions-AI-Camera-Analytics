import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.deps import require_internal_service, require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.camera import Camera
from app.models.tripwire import Tripwire
from app.models.user import User
from app.schemas.tripwire import TripwireCreate, TripwireResponse, TripwireUpdate

router = APIRouter(prefix="/tripwires", tags=["tripwires"])


@router.get("/internal/all", response_model=list[TripwireResponse], include_in_schema=False, dependencies=[Depends(require_internal_service)])
def list_all_tripwires_internal(db: Session = Depends(get_db)) -> list[Tripwire]:
    """Used by the ai-engine to load tripwire geometry for every active camera it's
    processing, across all tenants (trusted server-to-server call)."""
    return db.query(Tripwire).filter(Tripwire.is_enabled.is_(True)).all()


@router.get("", response_model=list[TripwireResponse])
def list_tripwires(
    camera_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> list[Tripwire]:
    query = db.query(Tripwire)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Tripwire.tenant_id == tenant_id)
    if camera_id:
        query = query.filter(Tripwire.camera_id == camera_id)
    return query.all()


def _get_owned_tripwire(db: Session, tripwire_id: uuid.UUID, user: User) -> Tripwire:
    tripwire = db.get(Tripwire, tripwire_id)
    tenant_id = tenant_filter_value(user)
    if tripwire is None or (tenant_id and tripwire.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tripwire not found")
    return tripwire


@router.post("", response_model=TripwireResponse, status_code=status.HTTP_201_CREATED)
def create_tripwire(
    payload: TripwireCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_RULES)),
) -> Tripwire:
    camera = db.get(Camera, payload.camera_id)
    tenant_id = tenant_filter_value(user)
    if camera is None or (tenant_id and camera.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    tripwire = Tripwire(tenant_id=camera.tenant_id, **payload.model_dump())
    db.add(tripwire)
    db.commit()
    db.refresh(tripwire)
    log_action(db, action="TRIPWIRE_CREATED", tenant_id=camera.tenant_id, user_id=user.id, resource_type="tripwire", resource_id=str(tripwire.id))
    return tripwire


@router.patch("/{tripwire_id}", response_model=TripwireResponse)
def update_tripwire(
    tripwire_id: uuid.UUID,
    payload: TripwireUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_RULES)),
) -> Tripwire:
    tripwire = _get_owned_tripwire(db, tripwire_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tripwire, field, value)
    db.commit()
    db.refresh(tripwire)
    return tripwire


@router.delete("/{tripwire_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tripwire(
    tripwire_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_RULES)),
) -> None:
    tripwire = _get_owned_tripwire(db, tripwire_id, user)
    db.delete(tripwire)
    db.commit()
    log_action(db, action="TRIPWIRE_DELETED", tenant_id=user.tenant_id, user_id=user.id, resource_type="tripwire", resource_id=str(tripwire_id))
