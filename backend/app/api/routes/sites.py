import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.deps import require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.camera import Camera
from app.models.site import Site
from app.models.user import User
from app.schemas.site import SiteCreate, SiteResponse, SiteUpdate

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("", response_model=list[SiteResponse])
def list_sites(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_SITES)),
) -> list[Site]:
    query = db.query(Site)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Site.tenant_id == tenant_id)
    return query.order_by(Site.name).all()


def _get_owned_site(db: Session, site_id: uuid.UUID, user: User) -> Site:
    site = db.get(Site, site_id)
    tenant_id = tenant_filter_value(user)
    if site is None or (tenant_id and site.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return site


@router.post("", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_SITES)),
) -> Site:
    site = Site(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(site)
    db.commit()
    db.refresh(site)
    log_action(db, action="SITE_CREATED", tenant_id=user.tenant_id, user_id=user.id, resource_type="site", resource_id=str(site.id), details={"name": site.name})
    return site


@router.patch("/{site_id}", response_model=SiteResponse)
def update_site(
    site_id: uuid.UUID,
    payload: SiteUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_SITES)),
) -> Site:
    site = _get_owned_site(db, site_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(site, field, value)
    db.commit()
    db.refresh(site)
    return site


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site(
    site_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_SITES)),
) -> None:
    """Deleting a site does not delete its cameras — they're unassigned (site_id set
    to NULL) rather than orphaned-and-deleted, since a camera and its whole event/
    recording history are far too significant to silently destroy as a side effect of
    a site being removed. An admin can reassign them to a different site afterward."""
    site = _get_owned_site(db, site_id, user)
    db.query(Camera).filter(Camera.site_id == site.id).update({"site_id": None})
    db.delete(site)
    db.commit()
    log_action(db, action="SITE_DELETED", tenant_id=user.tenant_id, user_id=user.id, resource_type="site", resource_id=str(site_id))
