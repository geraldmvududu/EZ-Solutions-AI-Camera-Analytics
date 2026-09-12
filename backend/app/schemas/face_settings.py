import uuid

from pydantic import BaseModel


class FaceRecognitionSettingsUpdate(BaseModel):
    facial_recognition_enabled: bool | None = None
    unknown_face_detection_enabled: bool | None = None
    default_match_threshold: float | None = None
    multi_frame_confirmation_enabled: bool | None = None
    liveness_detection_enabled: bool | None = None
    recognition_cooldown_seconds: int | None = None
    max_events_per_person_camera_per_hour: int | None = None
    event_retention_days: int | None = None
    snapshot_retention_days: int | None = None
    face_profile_retention_days: int | None = None


class FaceRecognitionSettingsResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    facial_recognition_enabled: bool
    unknown_face_detection_enabled: bool
    default_match_threshold: float
    multi_frame_confirmation_enabled: bool
    liveness_detection_enabled: bool
    recognition_cooldown_seconds: int
    max_events_per_person_camera_per_hour: int
    event_retention_days: int
    snapshot_retention_days: int
    face_profile_retention_days: int

    model_config = {"from_attributes": True}
