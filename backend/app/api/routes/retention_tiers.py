import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.retention_tier import RetentionTier
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.retention_tier import RetentionTierResponse, RetentionTierUpdate, TenantRetentionTierAssign

router = APIRouter(prefix="/retention-tiers", tags=["retention-tiers"])


@router.get("", response_model=list[RetentionTierResponse])
def list_retention_tiers(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[RetentionTier]:
    """Viewing the available tiers/day-counts isn't sensitive — any authenticated
    user can see them (e.g. a tenant admin checking what their current plan
    retains). Only a Platform Administrator (SUPER_ADMIN) can edit the values or
    reassign a tenant to a different tier — see the two routes below."""
    return db.query(RetentionTier).order_by(RetentionTier.event_metadata_days).all()


@router.get("/mine", response_model=RetentionTierResponse)
def get_my_retention_tier(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> RetentionTier:
    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None or tenant.retention_tier_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No retention tier assigned")
    tier = db.get(RetentionTier, tenant.retention_tier_id)
    if tier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No retention tier assigned")
    return tier


@router.put("/{tier_id}", response_model=RetentionTierResponse)
def update_retention_tier(
    tier_id: uuid.UUID,
    payload: RetentionTierUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("SUPER_ADMIN")),
) -> RetentionTier:
    tier = db.get(RetentionTier, tier_id)
    if tier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retention tier not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tier, field, value)
    db.commit()
    db.refresh(tier)
    return tier


@router.put("/assign/{tenant_id}", response_model=RetentionTierResponse)
def assign_tenant_retention_tier(
    tenant_id: uuid.UUID,
    payload: TenantRetentionTierAssign,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("SUPER_ADMIN")),
) -> RetentionTier:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tier = db.get(RetentionTier, payload.retention_tier_id)
    if tier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retention tier not found")
    tenant.retention_tier_id = tier.id
    db.commit()
    return tier
