"""AI Video Intelligence Phase 1 tenant settings (section 35) — same seed-on-first-use
pattern as app/api/routes/faces.py::_get_or_create_settings, kept in its own module
since this settings row isn't specific to facial recognition."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.deps import require_permission
from app.core.permissions import Permissions
from app.database import get_db
from app.models.user import User
from app.models.video_intelligence_settings import VideoIntelligenceSettings
from app.schemas.video_intelligence import VideoIntelligenceSettingsResponse, VideoIntelligenceSettingsUpdate

router = APIRouter(prefix="/video-intelligence-settings", tags=["video-intelligence"])


def _get_or_create_settings(db: Session, tenant_id: uuid.UUID) -> VideoIntelligenceSettings:
    row = db.query(VideoIntelligenceSettings).filter(VideoIntelligenceSettings.tenant_id == tenant_id).first()
    if row is None:
        row = VideoIntelligenceSettings(tenant_id=tenant_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("", response_model=VideoIntelligenceSettingsResponse)
def get_video_intelligence_settings(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_RULES)),
) -> VideoIntelligenceSettings:
    return _get_or_create_settings(db, user.tenant_id)


@router.put("", response_model=VideoIntelligenceSettingsResponse)
def update_video_intelligence_settings(
    payload: VideoIntelligenceSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_RULES)),
) -> VideoIntelligenceSettings:
    row = _get_or_create_settings(db, user.tenant_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    log_action(
        db, action="VIDEO_INTELLIGENCE_SETTINGS_UPDATED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="video_intelligence_settings", resource_id=str(row.id), details=data,
        ip_address=request.client.host if request.client else None,
    )
    return row
