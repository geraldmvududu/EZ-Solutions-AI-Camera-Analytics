import os
import shutil
import socket
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse

import httpx
import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
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
from app.models.face_settings import FaceRecognitionSettings
from app.models.incident import Incident, incident_alerts
from app.models.notification import Notification
from app.models.video_intelligence_settings import VideoIntelligenceSettings
from app.models.recording import Recording
from app.models.rule import AIRule
from app.models.snapshot import Snapshot
from app.models.tripwire import Tripwire
from app.models.user import User
from app.models.zone import Zone
from app.schemas.camera import CameraCreate, CameraInternalResponse, CameraResponse, CameraUpdate, OccupancyDelta

router = APIRouter(prefix="/cameras", tags=["cameras"])
settings = get_settings()

# Video-file upload (section 46 of the original spec — nginx.conf's own
# client_max_body_size 2G comment already referenced this, but no endpoint ever
# actually implemented it until now): lets an admin feed in footage from an external
# source (a hard drive, an old DVR/NVR export, ...) instead of requiring a live camera.
# The browser reads the file from wherever it's actually stored (the user's own
# machine — never this server) and streams it here; VIDEO_FILE cameras already treat
# any server-side path identically whether it arrived this way or was typed in by
# hand, so this needed no new camera-model/ai-engine code, only a real upload path.
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
UPLOAD_CHUNK_BYTES = 1024 * 1024  # 1MB — streamed, never buffered fully in memory
# Real incident this session: the VM's disk hit 100% and took Postgres down with it.
# An upload must never be the thing that does that again — abort (and delete the
# partial file) the moment free space would drop below this margin, checked on every
# chunk actually written, not just once up front.
MIN_FREE_DISK_BYTES_AFTER_UPLOAD = 500 * 1024 * 1024


def _get_owned_camera(db: Session, camera_id: uuid.UUID, user: User) -> Camera:
    camera = db.get(Camera, camera_id)
    tenant_id = tenant_filter_value(user)
    if camera is None or (tenant_id and camera.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera


def _next_camera_code(db: Session, tenant_id: uuid.UUID) -> str:
    count = db.query(Camera).filter(Camera.tenant_id == tenant_id).count()
    return f"CAM-{count + 1:03d}"


@router.get("/internal/active", response_model=list[CameraInternalResponse], include_in_schema=False, dependencies=[Depends(require_internal_service)])
def list_active_cameras_internal(db: Session = Depends(get_db)) -> list[CameraInternalResponse]:
    """Used by the ai-engine to discover which cameras it should be capturing/processing
    across ALL tenants — this is a trusted server-to-server call, not a user request, so
    it deliberately bypasses tenant scoping. Also flattens each camera's tenant's
    liveness_detection_enabled/recognition_cooldown_seconds (FaceRecognitionSettings)
    and gate_jumping_enabled/tailgating_enabled/restricted_area_enabled
    (VideoIntelligenceSettings) onto the response, since ai-engine needs these
    tenant-level settings but has no other way to read them."""
    from app.api.routes.faces import _get_or_create_settings as _get_or_create_face_settings
    from app.api.routes.video_intelligence import _get_or_create_settings as _get_or_create_vi_settings

    cameras = db.query(Camera).filter(Camera.is_active.is_(True)).all()
    face_settings_by_tenant: dict[uuid.UUID, FaceRecognitionSettings] = {}
    vi_settings_by_tenant: dict[uuid.UUID, VideoIntelligenceSettings] = {}
    results: list[CameraInternalResponse] = []
    for camera in cameras:
        if camera.tenant_id not in face_settings_by_tenant:
            face_settings_by_tenant[camera.tenant_id] = _get_or_create_face_settings(db, camera.tenant_id)
        if camera.tenant_id not in vi_settings_by_tenant:
            vi_settings_by_tenant[camera.tenant_id] = _get_or_create_vi_settings(db, camera.tenant_id)
        fr_settings = face_settings_by_tenant[camera.tenant_id]
        vi_settings = vi_settings_by_tenant[camera.tenant_id]
        response = CameraInternalResponse.model_validate(camera)
        response.liveness_detection_enabled = fr_settings.liveness_detection_enabled
        response.recognition_cooldown_seconds = fr_settings.recognition_cooldown_seconds
        response.gate_jumping_enabled = vi_settings.gate_jumping_enabled
        response.tailgating_enabled = vi_settings.tailgating_enabled
        response.restricted_area_enabled = vi_settings.restricted_area_enabled
        response.theft_detection_enabled = vi_settings.theft_detection_enabled
        results.append(response)
    return results


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
        multi_class_detection_enabled=payload.multi_class_detection_enabled,
        site_id=payload.site_id,
        cloud_recording_enabled=payload.cloud_recording_enabled,
        max_occupancy=payload.max_occupancy,
        plate_recognition_enabled=payload.plate_recognition_enabled,
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


@router.post("/upload-video")
async def upload_video(
    request: Request,
    video: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_CAMERAS)),
) -> dict:
    """Streams an uploaded video file to disk and returns the resulting path, for use
    as a VIDEO_FILE camera's video_file_path — see this module's constants above for
    why streaming (not buffering in memory) and a live disk-space check (not just an
    upfront one) both matter here."""
    filename = os.path.basename(video.filename or "upload")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_VIDEO_EXTENSIONS))}",
        )

    dest_dir = os.path.join(settings.upload_path, str(user.tenant_id))
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f"{uuid.uuid4().hex}{ext}")

    total_bytes = 0
    try:
        with open(dest_path, "wb") as f:
            while True:
                chunk = await video.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                if shutil.disk_usage(settings.upload_path).free - len(chunk) < MIN_FREE_DISK_BYTES_AFTER_UPLOAD:
                    raise HTTPException(
                        status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                        detail="Not enough free disk space on the server to accept this upload",
                    )
                f.write(chunk)
                total_bytes += len(chunk)
    except HTTPException:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise
    except Exception:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload failed") from None

    log_action(
        db, action="CAMERA_VIDEO_UPLOADED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="camera_video", resource_id=dest_path,
        ip_address=request.client.host if request.client else "",
        details={"filename": filename, "size_bytes": total_bytes},
    )
    return {"video_file_path": dest_path, "size_bytes": total_bytes}


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
    references out before deleting any of the three. AIRule/Incident are the two
    exceptions — a rule/incident outlives the camera it was scoped to, just unscoped
    (camera_id -> NULL), since deleting someone's configured rule or investigation
    record as a side effect of deleting a camera would be a surprising, unrelated
    data loss.

    Real bug found live on the deployed VM (a genuine `notifications_alert_id_fkey`
    ForeignKeyViolation, confirmed via `docker compose logs backend`): this function
    originally deleted `Alert` rows without first nulling the `Notification` rows
    (push/in-app feed) and `incident_alerts` join rows that reference them — harmless
    on a fresh camera with no activity, but real usage generates both. Both are handled
    below, in the same "unscope rather than destroy" spirit as AIRule/Incident.

    Second real bug found live on the same VM, on a camera that had been running for
    hours (137,927 detections / 26,067 alerts by the time it was deleted): the first
    fix above materialized every matching Alert/Event ID into a Python list and built
    an `IN (...)` clause from it — transmitting tens of thousands of literal UUIDs
    over the wire and asking Postgres to plan against a literal list that large. This
    made the delete take long enough that the browser gave up waiting (nginx logged a
    real `499`, meaning the client closed the connection, not the server). Rewritten
    to use correlated subqueries instead (`Alert.camera_id == camera_id` evaluated
    inside the database, on the existing indexed column, once), which is how every
    other filter in this function already works — this was the one place that broke
    that pattern.

    Third real bug found live on the same VM, on the same camera, immediately after
    the second fix above: even at full subquery speed, the delete still failed with
    `alerts_snapshot_id_fkey` — an Alert's `snapshot_id` pointed at one of this
    camera's snapshots even though that Alert's own `camera_id` didn't match (almost
    certainly a leftover inconsistency from this session's own earlier manual SQL
    cleanup on this VM, but the fix has to hold regardless of how it arose). Every
    null-out below is now scoped by the PARENT row's own camera_id (e.g. "any
    Detection/Event/Alert/FaceRecognitionEvent anywhere whose snapshot_id points at a
    snapshot this camera owns") instead of assuming the referencing row shares the
    same camera_id — the only case that was ever actually cheap to assume, and the
    one that turned out to be wrong. Every column here already has an index (this
    phase's other migrations), so each of these remains a single indexed lookup, not
    a table scan."""
    camera = _get_owned_camera(db, camera_id, user)

    snapshot_paths = [
        row[0] for row in db.query(Snapshot.file_path).filter(Snapshot.camera_id == camera_id).all()
    ]
    recording_paths = [
        row[0] for row in db.query(Recording.file_path).filter(Recording.camera_id == camera_id).all()
    ]
    camera_alert_ids = sa.select(Alert.id).where(Alert.camera_id == camera_id).scalar_subquery()
    camera_event_ids = sa.select(Event.id).where(Event.camera_id == camera_id).scalar_subquery()
    camera_snapshot_ids = sa.select(Snapshot.id).where(Snapshot.camera_id == camera_id).scalar_subquery()
    camera_recording_ids = sa.select(Recording.id).where(Recording.camera_id == camera_id).scalar_subquery()
    camera_detection_ids = sa.select(Detection.id).where(Detection.camera_id == camera_id).scalar_subquery()
    camera_zone_ids = sa.select(Zone.id).where(Zone.camera_id == camera_id).scalar_subquery()
    camera_tripwire_ids = sa.select(Tripwire.id).where(Tripwire.camera_id == camera_id).scalar_subquery()

    db.query(Event).filter(Event.zone_id.in_(camera_zone_ids)).update({"zone_id": None}, synchronize_session=False)
    db.query(Event).filter(Event.tripwire_id.in_(camera_tripwire_ids)).update({"tripwire_id": None}, synchronize_session=False)
    db.query(Detection).filter(Detection.snapshot_id.in_(camera_snapshot_ids)).update({"snapshot_id": None}, synchronize_session=False)
    db.query(Detection).filter(Detection.recording_id.in_(camera_recording_ids)).update({"recording_id": None}, synchronize_session=False)
    db.query(Event).filter(Event.snapshot_id.in_(camera_snapshot_ids)).update({"snapshot_id": None}, synchronize_session=False)
    db.query(Event).filter(Event.recording_id.in_(camera_recording_ids)).update({"recording_id": None}, synchronize_session=False)
    db.query(Event).filter(Event.detection_id.in_(camera_detection_ids)).update({"detection_id": None}, synchronize_session=False)
    db.query(Alert).filter(Alert.snapshot_id.in_(camera_snapshot_ids)).update({"snapshot_id": None}, synchronize_session=False)
    db.query(Alert).filter(Alert.recording_id.in_(camera_recording_ids)).update({"recording_id": None}, synchronize_session=False)
    db.query(FaceRecognitionEvent).filter(FaceRecognitionEvent.snapshot_id.in_(camera_snapshot_ids)).update({"snapshot_id": None}, synchronize_session=False)
    db.query(FaceRecognitionEvent).filter(FaceRecognitionEvent.recording_id.in_(camera_recording_ids)).update({"recording_id": None}, synchronize_session=False)
    db.query(Snapshot).filter(Snapshot.camera_id == camera_id).update({"event_id": None}, synchronize_session=False)

    db.execute(incident_alerts.delete().where(incident_alerts.c.alert_id.in_(camera_alert_ids)))
    db.query(Notification).filter(Notification.alert_id.in_(camera_alert_ids)).update(
        {"alert_id": None}, synchronize_session=False
    )
    db.query(Incident).filter(Incident.source_event_id.in_(camera_event_ids)).update(
        {"source_event_id": None}, synchronize_session=False
    )
    db.query(Incident).filter(Incident.camera_id == camera_id).update({"camera_id": None}, synchronize_session=False)

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
async def camera_heartbeat(camera_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Internal endpoint the ai-engine calls periodically while actively processing a
    camera's stream, used to derive real ONLINE/OFFLINE status (section 33). The reverse
    transition (worker.py::check_camera_health flipping a stale camera to OFFLINE) lives in
    worker/app.py, not here — this endpoint only ever sees a camera that's still alive."""
    from datetime import datetime, timezone

    from app.models.camera import CameraStatus
    from app.models.event import EventSeverity, EventType
    from app.schemas.event import EventCreate
    from app.api.routes.events import create_event_and_process

    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    was_offline = camera.status == CameraStatus.OFFLINE
    camera.last_heartbeat_at = datetime.now(timezone.utc)
    camera.status = CameraStatus.ONLINE
    db.commit()

    if was_offline:
        await create_event_and_process(
            db, camera,
            EventCreate(
                camera_id=camera.id,
                event_type=EventType.CAMERA_ONLINE,
                severity=EventSeverity.LOW,
                description=f'Camera "{camera.name}" is back online.',
                occurred_at=datetime.now(timezone.utc),
            ),
        )

    return {"detail": "ok"}


@router.post("/{camera_id}/internal/mark-video-processed", include_in_schema=False, dependencies=[Depends(require_internal_service)])
def mark_video_processed_internal(camera_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Called once by worker.py when a VIDEO_FILE camera with loop_video=False reaches
    real end-of-file (see Camera.video_processed_at's own docstring for why this
    exists). Sets is_active=False so GET /cameras/internal/active drops this camera
    and main.py's discovery loop stops restarting it — permanently ending analysis of
    that footage instead of retrying it forever. Idempotent: calling it again on an
    already-processed camera is a harmless no-op, not an error."""
    from datetime import datetime, timezone

    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    if camera.video_processed_at is None:
        camera.video_processed_at = datetime.now(timezone.utc)
        camera.is_active = False
        db.commit()
    return {"detail": "ok"}


@router.post("/{camera_id}/internal/occupancy-delta", include_in_schema=False, dependencies=[Depends(require_internal_service)])
async def report_occupancy_delta(camera_id: uuid.UUID, payload: OccupancyDelta, db: Session = Depends(get_db)) -> dict:
    """Master Development Prompt Phase 1, "Crowd/Occupancy Counting" — called by
    worker.py once per real ENTERING (+1) or EXITING (-1) crossing of a tripwire with
    occupancy_counting_enabled, regardless of that tripwire's own `direction` filter or
    TRIPWIRE_VIOLATION_COOLDOWN_SECONDS (those gate violation reporting, not counting —
    a queue of several people passing within the cooldown window must still all be
    counted). Fires MAXIMUM_OCCUPANCY_EXCEEDED only on the transition from at-or-under
    to over max_occupancy, not on every delta while already over, mirroring every other
    debounced event in this codebase."""
    from datetime import datetime, timezone

    from app.api.routes.events import create_event_and_process
    from app.models.event import EventSeverity, EventType
    from app.schemas.event import EventCreate

    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    previous = camera.current_occupancy
    camera.current_occupancy = max(0, previous + payload.delta)
    db.commit()
    db.refresh(camera)

    if camera.max_occupancy is not None and previous <= camera.max_occupancy < camera.current_occupancy:
        await create_event_and_process(
            db, camera,
            EventCreate(
                camera_id=camera.id,
                event_type=EventType.MAXIMUM_OCCUPANCY_EXCEEDED,
                severity=EventSeverity.HIGH,
                description=(
                    f'Camera "{camera.name}" occupancy ({camera.current_occupancy}) exceeded the configured '
                    f"maximum ({camera.max_occupancy})."
                ),
                occurred_at=datetime.now(timezone.utc),
                event_metadata={"current_occupancy": camera.current_occupancy, "max_occupancy": camera.max_occupancy},
            ),
        )

    return {"current_occupancy": camera.current_occupancy}


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
