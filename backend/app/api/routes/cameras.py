import os
import socket
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from jose import JWTError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import log_action
from app.core.deps import require_internal_service, require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.core.security import decrypt_secret, decode_access_token, encrypt_secret
from app.database import get_db
from app.models.alert import Alert
from app.models.camera import Camera, CameraSourceType, CameraStream
from app.models.detection import Detection
from app.models.event import Event
from app.models.face_recognition_event import FaceRecognitionEvent
from app.models.recording import Recording
from app.models.rule import AIRule
from app.models.snapshot import Snapshot
from app.models.tripwire import Tripwire
from app.models.user import User
from app.models.zone import Zone
from app.schemas.camera import CameraCreate, CameraResponse, CameraUpdate

router = APIRouter(prefix="/cameras", tags=["cameras"])
settings = get_settings()


def _get_owned_camera(db: Session, camera_id: uuid.UUID, user: User) -> Camera:
    camera = db.get(Camera, camera_id)
    tenant_id = tenant_filter_value(user)
    if camera is None or (tenant_id and camera.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera


def _next_camera_code(db: Session, tenant_id: uuid.UUID) -> str:
    count = db.query(Camera).filter(Camera.tenant_id == tenant_id).count()
    return f"CAM-{count + 1:03d}"


@router.get("/internal/active", response_model=list[CameraResponse], include_in_schema=False, dependencies=[Depends(require_internal_service)])
def list_active_cameras_internal(db: Session = Depends(get_db)) -> list[Camera]:
    """Used by the ai-engine to discover which cameras it should be capturing/processing
    across ALL tenants — this is a trusted server-to-server call, not a user request, so
    it deliberately bypasses tenant scoping."""
    return db.query(Camera).filter(Camera.is_active.is_(True)).all()


@router.get("", response_model=list[CameraResponse])
def list_cameras(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> list[Camera]:
    query = db.query(Camera)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Camera.tenant_id == tenant_id)
    return query.order_by(Camera.camera_code).all()


@router.get("/{camera_id}", response_model=CameraResponse)
def get_camera(
    camera_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> Camera:
    return _get_owned_camera(db, camera_id, user)


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
def create_camera(
    payload: CameraCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_CAMERAS)),
) -> Camera:
    camera = Camera(
        tenant_id=user.tenant_id,
        camera_code=_next_camera_code(db, user.tenant_id),
        name=payload.name,
        location=payload.location,
        description=payload.description,
        source_type=payload.source_type,
        stream_url=payload.stream_url,
        username=payload.username,
        password_encrypted=encrypt_secret(payload.password),
        video_file_path=payload.video_file_path,
        loop_video=payload.loop_video,
        resolution_width=payload.resolution_width,
        resolution_height=payload.resolution_height,
        capture_fps=payload.capture_fps,
        ai_fps=payload.ai_fps,
        ai_enabled=payload.ai_enabled,
        motion_detection_enabled=payload.motion_detection_enabled,
        motion_sensitivity=payload.motion_sensitivity,
        recording_enabled=payload.recording_enabled,
        recording_mode=payload.recording_mode,
        retention_days=payload.retention_days,
        confidence_threshold=payload.confidence_threshold,
        face_recognition_enabled=payload.face_recognition_enabled,
        face_recognition_threshold=payload.face_recognition_threshold,
        face_operating_hours_start=payload.face_operating_hours_start,
        face_operating_hours_end=payload.face_operating_hours_end,
    )
    db.add(camera)
    db.commit()
    db.refresh(camera)

    log_action(
        db, action="CAMERA_CREATED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="camera", resource_id=str(camera.id),
        ip_address=request.client.host if request.client else "",
        details={"name": camera.name, "source_type": camera.source_type.value},
    )
    return camera


@router.patch("/{camera_id}", response_model=CameraResponse)
def update_camera(
    camera_id: uuid.UUID,
    payload: CameraUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_CAMERAS)),
) -> Camera:
    camera = _get_owned_camera(db, camera_id, user)
    data = payload.model_dump(exclude_unset=True)

    if "password" in data:
        password = data.pop("password")
        if password is not None:
            camera.password_encrypted = encrypt_secret(password)

    for field, value in data.items():
        setattr(camera, field, value)

    db.commit()
    db.refresh(camera)

    log_action(
        db, action="CAMERA_UPDATED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="camera", resource_id=str(camera.id),
        ip_address=request.client.host if request.client else "",
        details={k: v for k, v in data.items()},
    )
    return camera


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(
    camera_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_CAMERAS)),
) -> None:
    """Deleting a camera with real activity against it (events, detections, zones,
    recordings...) used to raise an unhandled IntegrityError on Postgres — SQLite
    (used in local tests) never enforces the foreign keys pointing at cameras.id, so
    `db.delete(camera)` alone "worked" in every test run but failed for real once a
    camera actually had dependent rows. Every dependent table is cleaned up explicitly
    here, in an order that respects the circular Event/Detection/Snapshot FK
    relationship (see app/models/detection.py's comment) by nulling those cross-
    references out before deleting any of the three. AIRule is the one exception —
    a rule outlives the camera it was scoped to, just unscoped (camera_id -> NULL),
    since deleting someone's configured rule as a side effect of deleting a camera
    would be a surprising, unrelated data loss."""
    camera = _get_owned_camera(db, camera_id, user)

    snapshot_paths = [
        row[0] for row in db.query(Snapshot.file_path).filter(Snapshot.camera_id == camera_id).all()
    ]
    recording_paths = [
        row[0] for row in db.query(Recording.file_path).filter(Recording.camera_id == camera_id).all()
    ]

    db.query(Detection).filter(Detection.camera_id == camera_id).update(
        {"snapshot_id": None, "recording_id": None}, synchronize_session=False
    )
    db.query(Event).filter(Event.camera_id == camera_id).update(
        {"detection_id": None, "snapshot_id": None, "recording_id": None}, synchronize_session=False
    )
    db.query(Snapshot).filter(Snapshot.camera_id == camera_id).update({"event_id": None}, synchronize_session=False)

    db.query(FaceRecognitionEvent).filter(FaceRecognitionEvent.camera_id == camera_id).delete(synchronize_session=False)
    db.query(Alert).filter(Alert.camera_id == camera_id).delete(synchronize_session=False)
    db.query(Detection).filter(Detection.camera_id == camera_id).delete(synchronize_session=False)
    db.query(Snapshot).filter(Snapshot.camera_id == camera_id).delete(synchronize_session=False)
    db.query(Recording).filter(Recording.camera_id == camera_id).delete(synchronize_session=False)
    db.query(Event).filter(Event.camera_id == camera_id).delete(synchronize_session=False)
    db.query(Zone).filter(Zone.camera_id == camera_id).delete(synchronize_session=False)
    db.query(Tripwire).filter(Tripwire.camera_id == camera_id).delete(synchronize_session=False)
    db.query(CameraStream).filter(CameraStream.camera_id == camera_id).delete(synchronize_session=False)
    db.query(AIRule).filter(AIRule.camera_id == camera_id).update({"camera_id": None}, synchronize_session=False)

    db.delete(camera)
    db.commit()

    for path in snapshot_paths + recording_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass  # best-effort — a missing/locked file must not block the camera delete that already committed

    log_action(
        db, action="CAMERA_DELETED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="camera", resource_id=str(camera_id),
        ip_address=request.client.host if request.client else "",
    )


@router.post("/{camera_id}/test-connection")
def test_connection(
    camera_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_CAMERAS)),
) -> dict:
    """Performs a real reachability check appropriate to the camera's source type. This
    does not decode video (that requires the ai-engine's OpenCV pipeline) — it verifies
    the network endpoint or file actually exists."""
    camera = _get_owned_camera(db, camera_id, user)

    if camera.source_type == CameraSourceType.VIDEO_FILE:
        import os

        ok = os.path.isfile(camera.video_file_path)
        return {"success": ok, "detail": "File found" if ok else f"File not found: {camera.video_file_path}"}

    if camera.source_type in (CameraSourceType.SIMULATED, CameraSourceType.WEBCAM):
        return {"success": True, "detail": "Verified at AI-engine runtime, not from the backend"}

    parsed = urlparse(camera.stream_url)
    host = parsed.hostname
    port = parsed.port or (554 if camera.source_type == CameraSourceType.RTSP else 80)
    if not host:
        return {"success": False, "detail": "No host could be parsed from stream_url"}

    try:
        with socket.create_connection((host, port), timeout=3):
            return {"success": True, "detail": f"TCP connection to {host}:{port} succeeded"}
    except OSError as exc:
        return {"success": False, "detail": f"Could not reach {host}:{port} — {exc}"}


@router.get("/{camera_id}/internal/stream-info", include_in_schema=False, dependencies=[Depends(require_internal_service)])
def get_stream_info_internal(camera_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Returns the DECRYPTED stream URL/credentials for the ai-engine to open a real
    RTSP/MJPEG/IP-camera connection. Only reachable with the shared internal-service
    token (never exposed to a JWT-authenticated dashboard/mobile request) — this is the
    one deliberate exception to 'credentials never leave the backend' (section 14/46),
    because the video capture process itself must have them to connect."""
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    return {
        "stream_url": camera.stream_url,
        "username": camera.username,
        "password": decrypt_secret(camera.password_encrypted),
    }


@router.post("/{camera_id}/heartbeat", include_in_schema=False, dependencies=[Depends(require_internal_service)])
def camera_heartbeat(camera_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Internal endpoint the ai-engine calls periodically while actively processing a
    camera's stream, used to derive real ONLINE/OFFLINE status (section 33)."""
    from datetime import datetime, timezone

    from app.models.camera import CameraStatus

    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    camera.last_heartbeat_at = datetime.now(timezone.utc)
    camera.status = CameraStatus.ONLINE
    db.commit()
    return {"detail": "ok"}


@router.get("/{camera_id}/stream")
async def stream_camera(camera_id: uuid.UUID, token: str, db: Session = Depends(get_db)) -> StreamingResponse:
    """Live MJPEG view (sections 13/38). Proxies the ai-engine's real annotated frame
    stream for this camera through to the browser/mobile client, after checking auth
    and tenant/permission ownership here — the ai-engine's stream server itself has no
    concept of users or tenants, so this endpoint is the only access-control boundary.

    Browsers render this via a plain <img src="..."> tag, which cannot send an
    Authorization header, so the access token travels as a query parameter instead —
    the same pattern used by /ws/live."""
    try:
        payload = decode_access_token(token)
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    if "view_live_video" not in {p.code for p in user.role.permissions}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: view_live_video")

    camera = db.get(Camera, camera_id)
    tenant_id = tenant_filter_value(user)
    if camera is None or (tenant_id and camera.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    upstream_url = f"{settings.ai_engine_stream_url}/stream/{camera_id}"
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=None, write=None, pool=None))

    try:
        upstream_request = client.build_request("GET", upstream_url)
        upstream_response = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"ai-engine stream unavailable: {exc}")

    async def proxy() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream_response.aiter_bytes():
                yield chunk
        finally:
            await upstream_response.aclose()
            await client.aclose()

    return StreamingResponse(
        proxy(),
        media_type=upstream_response.headers.get("content-type", "multipart/x-mixed-replace; boundary=ezframe"),
    )
