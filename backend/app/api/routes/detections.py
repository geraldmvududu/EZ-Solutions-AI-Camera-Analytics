import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import require_internal_service, require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.camera import Camera
from app.models.detection import Detection, ObjectType
from app.models.user import User
from app.schemas.detection import DetectionCreate, DetectionResponse

router = APIRouter(prefix="/detections", tags=["detections"])


@router.get("", response_model=list[DetectionResponse])
def list_detections(
    camera_id: uuid.UUID | None = None,
    object_type: ObjectType | None = None,
    tracking_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(200, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> list[Detection]:
    query = db.query(Detection)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Detection.tenant_id == tenant_id)
    if camera_id:
        query = query.filter(Detection.camera_id == camera_id)
    if object_type:
        query = query.filter(Detection.object_type == object_type)
    if tracking_id is not None:
        query = query.filter(Detection.tracking_id == tracking_id)
    if start:
        query = query.filter(Detection.detected_at >= start)
    if end:
        query = query.filter(Detection.detected_at <= end)
    return query.order_by(Detection.detected_at.desc()).offset(offset).limit(limit).all()


@router.get("/{detection_id}", response_model=DetectionResponse)
def get_detection(
    detection_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> Detection:
    detection = db.get(Detection, detection_id)
    tenant_id = tenant_filter_value(user)
    if detection is None or (tenant_id and detection.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
    return detection


@router.post("", response_model=DetectionResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_internal_service)])
def create_detection(payload: DetectionCreate, db: Session = Depends(get_db)) -> Detection:
    camera = db.get(Camera, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    detection = Detection(tenant_id=camera.tenant_id, **payload.model_dump())
    db.add(detection)
    db.commit()
    db.refresh(detection)
    return detection
