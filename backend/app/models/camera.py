import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class CameraSourceType(str, enum.Enum):
    VIDEO_FILE = "VIDEO_FILE"
    SIMULATED = "SIMULATED"
    WEBCAM = "WEBCAM"
    RTSP = "RTSP"
    HTTP_MJPEG = "HTTP_MJPEG"
    IP_CAMERA = "IP_CAMERA"


class CameraStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"
    DISABLED = "DISABLED"


class RecordingMode(str, enum.Enum):
    CONTINUOUS = "CONTINUOUS"
    MOTION = "MOTION"
    AI_EVENT = "AI_EVENT"
    DISABLED = "DISABLED"


class Camera(Base, UUIDPKMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "cameras"

    camera_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")

    source_type: Mapped[CameraSourceType] = mapped_column(Enum(CameraSourceType), nullable=False)
    stream_url: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    username: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    password_encrypted: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    video_file_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    loop_video: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Real user request: footage from a finite video file (looping test/demo clips, or
    # uploaded external-source footage) was producing genuinely "new-looking" events
    # every time the loop replayed the same content — each crossing is >30s apart from
    # the last, so the cooldowns (worker.py's OBJECT_EVENT_COOLDOWN_SECONDS/
    # TRIPWIRE_VIOLATION_COOLDOWN_SECONDS) correctly treat each loop pass as a distinct
    # occurrence, since from the AI's perspective it genuinely is one — there is no
    # frame-content memory spanning an entire loop. video_processed_at is set once
    # (worker.py's _run(), via a new internal endpoint) when a VIDEO_FILE camera with
    # loop_video=False reaches real end-of-file — at that point is_active is also set
    # False so main.py's discovery loop stops restarting it, permanently ending
    # analysis of that footage rather than the previous behavior of retrying it every
    # ~60s forever. Nullable/None for every other camera and for a VIDEO_FILE camera
    # still actively looping.
    video_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    resolution_width: Mapped[int] = mapped_column(Integer, default=1280, nullable=False)
    resolution_height: Mapped[int] = mapped_column(Integer, default=720, nullable=False)
    capture_fps: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    ai_fps: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    motion_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    motion_sensitivity: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)

    recording_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recording_mode: Mapped[RecordingMode] = mapped_column(Enum(RecordingMode), default=RecordingMode.AI_EVENT, nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)

    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)

    # Facial Recognition & Identity Analytics (section 5) — mirrors the ai_enabled/
    # confidence_threshold pattern above rather than a separate per-camera settings
    # table. Operating hours are plain "HH:MM" strings, same convention as
    # AIRule.conditions.time_start/time_end in app/services/rule_engine.py.
    face_recognition_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    face_recognition_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    face_operating_hours_start: Mapped[str] = mapped_column(String(5), nullable=False, default="")
    face_operating_hours_end: Mapped[str] = mapped_column(String(5), nullable=False, default="")

    # AI Video Intelligence Phase 2 (section 6) — opt-in per camera, mirrors the
    # ai_enabled/face_recognition_enabled boolean pattern above. Existing cameras keep
    # the cheap PERSON-only HOG detector unchanged by default; this switches
    # ai-engine's build_detector() to YOLOv8n instead (real multi-class detection —
    # required for ASSET_ZONE/theft detection to see anything at all — but heavier on
    # CPU and pulls in a much larger torch/ultralytics dependency).
    multi_class_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Event-First Cloud Storage Phase 1 (section 1) — nullable so existing cameras
    # (predating the Site concept) keep working unmigrated; the migration backfills a
    # "Default Site" per tenant and points every existing camera at it.
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id"), nullable=True, index=True)

    # Event-First Cloud Storage Phase 1 (section 7) — spec's "Full Cloud Recording"
    # premium tier: off by default (continuous recordings stay local-only, per section
    # 8's default philosophy), lets an admin opt a specific camera's CONTINUOUS-mode
    # recordings into the same S3/MinIO upload path already used unconditionally for
    # snapshots and non-continuous (event/motion) recordings.
    cloud_recording_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[CameraStatus] = mapped_column(Enum(CameraStatus), default=CameraStatus.OFFLINE, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CameraStream(Base, UUIDPKMixin, TimestampMixin):
    """Runtime status of an active camera processing session (one row per active AI-engine worker)."""

    __tablename__ = "camera_streams"

    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_capture_fps: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    current_ai_fps: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    processing_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    device: Mapped[str] = mapped_column(String(10), default="cpu", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
