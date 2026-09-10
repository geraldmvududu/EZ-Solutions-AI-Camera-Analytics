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
