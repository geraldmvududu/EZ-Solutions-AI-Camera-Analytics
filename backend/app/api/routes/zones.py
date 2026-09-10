import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.deps import require_internal_service, require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.camera import Camera
from app.models.user import User
from app.models.zone import Zone
from app.schemas.zone import ZoneCreate, ZoneResponse, ZoneUpdate

router = APIRouter(prefix="/zones", tags=["zones"])


@router.get("/internal/all", response_model=list[ZoneResponse], include_in_schema=False, dependencies=[Depends(require_internal_service)])
def list_all_zones_internal(db: Session = Depends(get_db)) -> list[Zone]:
    """Used by the ai-engine to load zone geometry for every active camera it's
    processing, across all tenants (trusted server-to-server call)."""
    return db.query(Zone).filter(Zone.is_enabled.is_(True)).all()


@router.get("", response_model=list[ZoneResponse])
def list_zones(
    camera_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> list[Zone]:
    query = db.query(Zone)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Zone.tenant_id == tenant_id)
    if camera_id:
        query = query.filter(Zone.camera_id == camera_id)
    return query.all()


def _get_owned_zone(db: Session, zone_id: uuid.UUID, user: User) -> Zone:
    zone = db.get(Zone, zone_id)
    tenant_id = tenant_filter_value(user)
    if zone is None or (tenant_id and zone.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    return zone


@router.post("", response_model=ZoneResponse, status_code=status.HTTP_201_CREATED)
def create_zone(
    payload: ZoneCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_RULES)),
) -> Zone:
    camera = db.get(Camera, payload.camera_id)
    tenant_id = tenant_filter_value(user)
    if camera is None or (tenant_id and camera.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    zone = Zone(tenant_id=camera.tenant_id, **payload.model_dump())
    db.add(zone)
    db.commit()
    db.refresh(zone)
    log_action(db, action="ZONE_CREATED", tenant_id=camera.tenant_id, user_id=user.id, resource_type="zone", resource_id=str(zone.id))
    return zone


@router.patch("/{zone_id}", response_model=ZoneResponse)
def update_zone(
    zone_id: uuid.UUID,
    payload: ZoneUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_RULES)),
) -> Zone:
    zone = _get_owned_zone(db, zone_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(zone, field, value)
    db.commit()
    db.refresh(zone)
    return zone


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_zone(
    zone_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_RULES)),
) -> None:
    zone = _get_owned_zone(db, zone_id, user)
    db.delete(zone)
    db.commit()
    log_action(db, action="ZONE_DELETED", tenant_id=user.tenant_id, user_id=user.id, resource_type="zone", resource_id=str(zone_id))
