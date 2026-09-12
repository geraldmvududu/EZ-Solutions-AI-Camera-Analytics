import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.face_recognition_event import RecognitionStatus


class FaceRecognizeRequest(BaseModel):
    """Posted by the ai-engine (internal-service-authenticated) for one recognition
    attempt against one tracked face crop — see ai-engine/app/core/face_recognizer.py.
    `embedding` travels in plaintext over the trusted internal Docker network (same
    trust boundary as /api/detections and /api/events); it is never persisted
    plaintext — app/api/routes/faces.py encrypts before any DB write, and this
    candidate vector itself is never stored at all, only compared then discarded."""

    camera_id: uuid.UUID
    tracking_id: int
    embedding: list[float]
    model_version: str
    quality_score: float
    snapshot_id: uuid.UUID | None = None
    recording_id: uuid.UUID | None = None
    occurred_at: datetime


class FaceRecognizeResult(BaseModel):
    # A plain str, not RecognitionStatus, because this can also carry
    # "PENDING_CONFIRMATION" (section 4/13's multi-frame confirmation — see
    # app/api/routes/faces.py) which is never written to the DB enum, only ever
    # returned transiently to ai-engine for logging/cooldown bookkeeping.
    recognition_status: str
    person_id: uuid.UUID | None
    person_name: str | None
    confidence_score: float
    event_id: uuid.UUID | None = None


class FaceRecognitionEventResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    event_id: uuid.UUID
    camera_id: uuid.UUID
    person_id: uuid.UUID | None
    confidence_score: float
    recognition_status: RecognitionStatus
    model_version: str
    event_timestamp: datetime
    snapshot_id: uuid.UUID | None
    recording_id: uuid.UUID | None
    reviewed: bool
    review_decision: str
    review_notes: str
    reviewed_by: uuid.UUID | None
    review_timestamp: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FaceEventReviewRequest(BaseModel):
    decision: str  # CONFIRMED | REJECTED | FALSE_POSITIVE | ESCALATED
    notes: str = ""
