import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.camera import CameraSourceType, CameraStatus, RecordingMode


class CameraCreate(BaseModel):
    name: str
    location: str = ""
    description: str = ""
    source_type: CameraSourceType
    stream_url: str = ""
    username: str = ""
    password: str = ""
    video_file_path: str = ""
    loop_video: bool = True
    resolution_width: int = 1280
    resolution_height: int = 720
    capture_fps: int = 15
    ai_fps: int = Field(default=5, ge=1, le=15)
    ai_enabled: bool = True
    motion_detection_enabled: bool = True
    motion_sensitivity: str = "MEDIUM"
    recording_enabled: bool = True
    recording_mode: RecordingMode = RecordingMode.AI_EVENT
    retention_days: int = 7
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    face_recognition_enabled: bool = False
    face_recognition_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    face_operating_hours_start: str = ""
    face_operating_hours_end: str = ""


class CameraUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    description: str | None = None
    stream_url: str | None = None
    username: str | None = None
    password: str | None = None
    video_file_path: str | None = None
    loop_video: bool | None = None
    capture_fps: int | None = None
    ai_fps: int | None = None
    ai_enabled: bool | None = None
    motion_detection_enabled: bool | None = None
    motion_sensitivity: str | None = None
    recording_enabled: bool | None = None
    recording_mode: RecordingMode | None = None
    retention_days: int | None = None
    confidence_threshold: float | None = None
    is_active: bool | None = None
    face_recognition_enabled: bool | None = None
    face_recognition_threshold: float | None = None
    face_operating_hours_start: str | None = None
    face_operating_hours_end: str | None = None


class CameraResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    camera_code: str
    name: str
    location: str
    description: str
    source_type: CameraSourceType
    video_file_path: str
    loop_video: bool
    resolution_width: int
    resolution_height: int
    capture_fps: int
    ai_fps: int
    ai_enabled: bool
    motion_detection_enabled: bool
    motion_sensitivity: str
    recording_enabled: bool
    recording_mode: RecordingMode
    retention_days: int
    confidence_threshold: float
    face_recognition_enabled: bool
    face_recognition_threshold: float | None
    face_operating_hours_start: str
    face_operating_hours_end: str
    status: CameraStatus
    is_active: bool
    is_demo: bool
    last_heartbeat_at: datetime | None
    created_at: datetime

    # NOTE: stream_url/username/password are intentionally excluded from the API
    # response — camera credentials must never be exposed to the frontend (section 14).

    model_config = {"from_attributes": True}
