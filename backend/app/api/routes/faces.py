"""Face Recognition & Identity Analytics (spec sections 1-16). Reuses the existing
events/alerts/rule-engine/WebSocket/notification pipeline end-to-end — see
app/api/routes/events.py::create_event, which this module's /faces/recognize mirrors
closely on purpose. See CLAUDE.md for the full architecture writeup."""

import os
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
from anyio import to_thread
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import log_action
from app.core.deps import require_internal_service, require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.core.security import decrypt_face_embedding, encrypt_face_embedding
from app.database import get_db
from app.models.alert import Alert, AlertStatus
from app.models.camera import Camera
from app.models.event import Event, EventSeverity, EventType
from app.models.face_profile import FaceProfile, FaceProfileStatus
from app.models.face_recognition_event import FaceRecognitionEvent, RecognitionStatus
from app.models.face_settings import FaceRecognitionSettings
from app.models.person import Person, PersonCategory, PersonStatus
from app.models.user import User
from app.schemas.face_event import (
    FaceEventReviewRequest,
    FaceRecognitionEventResponse,
    FaceRecognizeRequest,
    FaceRecognizeResult,
)
from app.schemas.face_settings import FaceRecognitionSettingsResponse, FaceRecognitionSettingsUpdate
from app.schemas.person import EnrollmentResult, PersonResponse, PersonUpdate
from app.services import face_embedding, rule_engine
from app.services.notification_service import notify_users_of_alert
from app.services.ws_manager import manager

router = APIRouter(tags=["faces"])
settings = get_settings()

# A near-identical LBP histogram match at enrollment time almost certainly means the
# same person is already enrolled (section 2: "Prevent accidental duplicate
# enrollment") — deliberately higher than the recognition match threshold, since this
# guards against re-enrolling the same photo/person, not everyday recognition.
_DUPLICATE_MATCH_THRESHOLD = 0.92
_FACE_EVENT_TYPES = (EventType.FACE_RECOGNIZED, EventType.UNKNOWN_FACE_DETECTED)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _get_or_create_settings(db: Session, tenant_id: uuid.UUID) -> FaceRecognitionSettings:
    """First row for a tenant is seeded from the global FACE_* env vars (section 21)
    — after that, the tenant's own admin-configured values (section 22) take over and
    the env vars no longer apply to this tenant."""
    row = db.query(FaceRecognitionSettings).filter(FaceRecognitionSettings.tenant_id == tenant_id).first()
    if row is None:
        row = FaceRecognitionSettings(
            tenant_id=tenant_id,
            facial_recognition_enabled=settings.face_recognition_enabled,
            default_match_threshold=settings.face_match_threshold,
            event_retention_days=settings.face_retention_days,
            snapshot_retention_days=settings.face_image_retention_days,
            recognition_cooldown_seconds=settings.face_event_cooldown,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _get_owned_person(db: Session, person_id: uuid.UUID, user: User) -> Person:
    person = db.get(Person, person_id)
    tenant_id = tenant_filter_value(user)
    if person is None or (tenant_id and person.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    return person


def _active_profiles(db: Session, tenant_id: uuid.UUID) -> list[tuple[FaceProfile, Person]]:
    rows = (
        db.query(FaceProfile, Person)
        .join(Person, FaceProfile.person_id == Person.id)
        .filter(
            FaceProfile.tenant_id == tenant_id,
            FaceProfile.status == FaceProfileStatus.ACTIVE,
            Person.status != PersonStatus.DELETED,
        )
        .all()
    )
    return rows


# ---- Enrollment & person management (sections 2-3) ----


@router.post("/faces/enroll", response_model=EnrollmentResult, status_code=status.HTTP_201_CREATED)
async def enroll_face(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    category: PersonCategory = Form(...),
    external_reference: str = Form(""),
    department: str = Form(""),
    notes: str = Form(""),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_BIOMETRICS)),
) -> EnrollmentResult:
    raw = await photo.read()
    frame = face_embedding.decode_image_bytes(raw)
    if frame is None:
        return EnrollmentResult(success=False, message="Uploaded file is not a valid image")

    quality = face_embedding.assess_enrollment_quality(frame, settings.face_min_quality)
    if not quality.passed:
        return EnrollmentResult(success=False, message=quality.reason, quality_score=quality.quality_score)

    vector = face_embedding.compute_embedding(frame, quality.face)

    for profile, existing_person in _active_profiles(db, user.tenant_id):
        stored = face_embedding.embedding_from_base64(decrypt_face_embedding(profile.embedding_encrypted))
        if face_embedding.compare_embeddings(vector, stored) >= _DUPLICATE_MATCH_THRESHOLD:
            return EnrollmentResult(
                success=False,
                message=f"A very similar face is already enrolled as {existing_person.first_name} {existing_person.last_name} — possible duplicate enrollment",
            )

    person = Person(
        tenant_id=user.tenant_id,
        external_reference=external_reference,
        first_name=first_name,
        last_name=last_name,
        category=category,
        department=department,
        notes=notes,
    )
    db.add(person)
    db.commit()
    db.refresh(person)

    person_dir = os.path.join(settings.face_path, str(user.tenant_id))
    os.makedirs(person_dir, exist_ok=True)
    image_path = os.path.join(person_dir, f"{person.id}.jpg")
    with open(image_path, "wb") as f:
        f.write(raw)

    profile = FaceProfile(
        tenant_id=user.tenant_id,
        person_id=person.id,
        embedding_encrypted=encrypt_face_embedding(face_embedding.embedding_to_base64(vector)),
        model_version=face_embedding.FACE_MODEL_VERSION,
        image_reference=image_path,
        quality_score=quality.quality_score,
    )
    db.add(profile)
    db.commit()
    db.refresh(person)

    log_action(
        db, action="FACE_ENROLL", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="person", resource_id=str(person.id), ip_address=_client_ip(request),
        details={"name": f"{first_name} {last_name}", "category": category.value},
    )
    return EnrollmentResult(success=True, message="Face successfully enrolled", person=person, quality_score=quality.quality_score)


@router.get("/faces", response_model=list[PersonResponse])
def list_persons(
    q: str | None = None,
    category: PersonCategory | None = None,
    person_status: PersonStatus | None = Query(None, alias="status"),
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_BIOMETRIC_EVENTS)),
) -> list[Person]:
    query = db.query(Person)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Person.tenant_id == tenant_id)
    if category:
        query = query.filter(Person.category == category)
    if person_status:
        query = query.filter(Person.status == person_status)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Person.first_name.ilike(like)) | (Person.last_name.ilike(like)) | (Person.external_reference.ilike(like))
        )
    return query.order_by(Person.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/faces/{person_id}", response_model=PersonResponse)
def get_person(
    person_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_BIOMETRIC_EVENTS)),
) -> Person:
    return _get_owned_person(db, person_id, user)


@router.put("/faces/{person_id}", response_model=PersonResponse)
def update_person(
    person_id: uuid.UUID,
    payload: PersonUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_BIOMETRICS)),
) -> Person:
    person = _get_owned_person(db, person_id, user)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(person, field, value)
    db.commit()
    db.refresh(person)
    log_action(
        db, action="FACE_MODIFY", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="person", resource_id=str(person.id), ip_address=_client_ip(request), details=data,
    )
    return person


@router.delete("/faces/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(
    person_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_BIOMETRICS)),
) -> None:
    """Secure deletion (section 15): the embedding rows are hard-deleted (and the
    enrolled photo removed from disk) immediately — the Person row itself is kept,
    marked DELETED, only so historical FaceRecognitionEvent rows retain a valid FK for
    audit purposes."""
    person = _get_owned_person(db, person_id, user)
    for profile in list(person.face_profiles):
        if profile.image_reference and os.path.exists(profile.image_reference):
            os.remove(profile.image_reference)
        db.delete(profile)
    person.status = PersonStatus.DELETED
    db.commit()
    log_action(
        db, action="FACE_DELETE", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="person", resource_id=str(person_id), ip_address=_client_ip(request),
    )


@router.get("/faces/{person_id}/photo")
def get_person_photo(
    person_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_BIOMETRIC_EVENTS)),
) -> FileResponse:
    person = _get_owned_person(db, person_id, user)
    active = next((p for p in person.face_profiles if p.status == FaceProfileStatus.ACTIVE), None)
    if active is None or not os.path.exists(active.image_reference):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No enrolled photo")
    log_action(
        db, action="FACE_VIEW", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="person", resource_id=str(person_id), ip_address=_client_ip(request),
    )
    return FileResponse(active.image_reference, media_type="image/jpeg")


# ---- Recognition (called by the ai-engine — section 4/6/7) ----


@router.post("/faces/recognize", response_model=FaceRecognizeResult, dependencies=[Depends(require_internal_service)])
async def recognize_face(payload: FaceRecognizeRequest, db: Session = Depends(get_db)) -> FaceRecognizeResult:
    camera = db.get(Camera, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    tenant_id = camera.tenant_id
    fr_settings = _get_or_create_settings(db, tenant_id)
    threshold = camera.face_recognition_threshold or fr_settings.default_match_threshold

    candidate_vector = np.array(payload.embedding, dtype="float32")

    best_confidence = 0.0
    best_person: Person | None = None
    best_profile: FaceProfile | None = None
    for profile, person in _active_profiles(db, tenant_id):
        stored = face_embedding.embedding_from_base64(decrypt_face_embedding(profile.embedding_encrypted))
        confidence = face_embedding.compare_embeddings(candidate_vector, stored)
        if confidence > best_confidence:
            best_confidence, best_person, best_profile = confidence, person, profile

    if best_person is not None and best_confidence >= threshold:
        recognition_status = RecognitionStatus.RECOGNIZED
    elif best_person is not None and best_confidence >= threshold - 0.15:
        recognition_status = RecognitionStatus.LOW_CONFIDENCE
    else:
        recognition_status = RecognitionStatus.UNKNOWN
        best_person = None
        best_profile = None
        best_confidence = 0.0

    if recognition_status == RecognitionStatus.UNKNOWN and not fr_settings.unknown_face_detection_enabled:
        # Administrator has disabled unknown-person detection entirely (section 7) —
        # nothing is recorded, matching "the administrator must be able to disable
        # facial recognition globally or for individual cameras" (section 14).
        return FaceRecognizeResult(
            recognition_status=recognition_status, person_id=None, person_name=None,
            confidence_score=0.0, event_id=uuid.uuid4(),
        )

    # Maximum recognition events per person/camera (section 4) — an hourly cap so a
    # continuously-visible person/unknown face can't flood the event feed.
    window_start = datetime.now(timezone.utc) - timedelta(hours=1)
    cap_query = db.query(FaceRecognitionEvent).filter(
        FaceRecognitionEvent.tenant_id == tenant_id,
        FaceRecognitionEvent.camera_id == payload.camera_id,
        FaceRecognitionEvent.event_timestamp >= window_start,
    )
    cap_query = cap_query.filter(FaceRecognitionEvent.person_id == best_person.id) if best_person else cap_query.filter(FaceRecognitionEvent.person_id.is_(None))
    if cap_query.count() >= fr_settings.max_events_per_person_camera_per_hour:
        return FaceRecognizeResult(
            recognition_status=recognition_status,
            person_id=best_person.id if best_person else None,
            person_name=f"{best_person.first_name} {best_person.last_name}" if best_person else None,
            confidence_score=best_confidence, event_id=uuid.uuid4(),
        )

    event_type = EventType.FACE_RECOGNIZED if recognition_status == RecognitionStatus.RECOGNIZED else EventType.UNKNOWN_FACE_DETECTED
    severity = EventSeverity.INFO if recognition_status == RecognitionStatus.RECOGNIZED else EventSeverity.MEDIUM

    event = Event(
        tenant_id=tenant_id,
        camera_id=payload.camera_id,
        event_type=event_type,
        severity=severity,
        description="Face recognized" if best_person else "Unknown person detected",
        snapshot_id=payload.snapshot_id,
        occurred_at=payload.occurred_at,
        event_metadata={
            "person_category": best_person.category.value if best_person else None,
            "person_status": best_person.status.value if best_person else None,
            "person_name": f"{best_person.first_name} {best_person.last_name}" if best_person else None,
            "confidence": best_confidence,
            "recognition_status": recognition_status.value,
            "tracking_id": payload.tracking_id,
        },
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    face_event = FaceRecognitionEvent(
        tenant_id=tenant_id,
        event_id=event.id,
        camera_id=payload.camera_id,
        person_id=best_person.id if best_person else None,
        face_profile_id=best_profile.id if best_profile else None,
        confidence_score=best_confidence,
        recognition_status=recognition_status,
        model_version=payload.model_version,
        event_timestamp=payload.occurred_at,
        snapshot_id=payload.snapshot_id,
    )
    db.add(face_event)
    db.commit()

    alerts = rule_engine.evaluate_event(db, event)

    await manager.broadcast(tenant_id, {"type": "event", "event": {"id": str(event.id), "event_type": event_type.value}})
    for alert in alerts:
        from app.schemas.alert import AlertResponse

        await manager.broadcast(tenant_id, {"type": "alert", "alert": AlertResponse.model_validate(alert).model_dump(mode="json")})
        await to_thread.run_sync(notify_users_of_alert, db, alert, camera)

    return FaceRecognizeResult(
        recognition_status=recognition_status,
        person_id=best_person.id if best_person else None,
        person_name=f"{best_person.first_name} {best_person.last_name}" if best_person else None,
        confidence_score=best_confidence,
        event_id=event.id,
    )


# ---- Recognition event review (section 6/12) ----


@router.get("/face-events", response_model=list[FaceRecognitionEventResponse])
def list_face_events(
    camera_id: uuid.UUID | None = None,
    person_id: uuid.UUID | None = None,
    recognition_status: RecognitionStatus | None = None,
    reviewed: bool | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_BIOMETRIC_EVENTS)),
) -> list[FaceRecognitionEvent]:
    query = db.query(FaceRecognitionEvent)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(FaceRecognitionEvent.tenant_id == tenant_id)
    if camera_id:
        query = query.filter(FaceRecognitionEvent.camera_id == camera_id)
    if person_id:
        query = query.filter(FaceRecognitionEvent.person_id == person_id)
    if recognition_status:
        query = query.filter(FaceRecognitionEvent.recognition_status == recognition_status)
    if reviewed is not None:
        query = query.filter(FaceRecognitionEvent.reviewed == reviewed)
    if start:
        query = query.filter(FaceRecognitionEvent.event_timestamp >= start)
    if end:
        query = query.filter(FaceRecognitionEvent.event_timestamp <= end)
    return query.order_by(FaceRecognitionEvent.event_timestamp.desc()).offset(offset).limit(limit).all()


def _get_owned_face_event(db: Session, event_id: uuid.UUID, user: User) -> FaceRecognitionEvent:
    row = db.get(FaceRecognitionEvent, event_id)
    tenant_id = tenant_filter_value(user)
    if row is None or (tenant_id and row.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recognition event not found")
    return row


@router.get("/face-events/{event_id}", response_model=FaceRecognitionEventResponse)
def get_face_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_BIOMETRIC_EVENTS)),
) -> FaceRecognitionEvent:
    return _get_owned_face_event(db, event_id, user)


@router.post("/face-events/{event_id}/review", response_model=FaceRecognitionEventResponse)
def review_face_event(
    event_id: uuid.UUID,
    payload: FaceEventReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_ALERTS)),
) -> FaceRecognitionEvent:
    row = _get_owned_face_event(db, event_id, user)
    row.reviewed = True
    row.review_decision = payload.decision
    row.review_notes = payload.notes
    row.reviewed_by = user.id
    row.review_timestamp = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    log_action(
        db, action="FACE_EVENT_REVIEWED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="face_recognition_event", resource_id=str(event_id), ip_address=_client_ip(request),
        details={"decision": payload.decision},
    )
    return row


# ---- Alerts / violations / statistics (sections 10/11) — all backed by the existing
# Alert table; a "face alert" is simply an Alert whose Event is a face event. ----


def _face_alerts_query(db: Session, tenant_id: uuid.UUID | None):
    query = db.query(Alert).join(Event, Alert.event_id == Event.id).filter(Event.event_type.in_(_FACE_EVENT_TYPES))
    if tenant_id:
        query = query.filter(Alert.tenant_id == tenant_id)
    return query


@router.get("/face-alerts", response_model=list[dict])
def list_face_alerts(
    camera_id: uuid.UUID | None = None,
    severity: EventSeverity | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_BIOMETRIC_EVENTS)),
) -> list[dict]:
    from app.schemas.alert import AlertResponse

    query = _face_alerts_query(db, tenant_filter_value(user))
    if camera_id:
        query = query.filter(Alert.camera_id == camera_id)
    if severity:
        query = query.filter(Alert.severity == severity)
    rows = query.order_by(Alert.created_at.desc()).limit(limit).all()
    return [AlertResponse.model_validate(a).model_dump(mode="json") for a in rows]


@router.get("/face-violations", response_model=list[dict])
def list_face_violations(
    camera_id: uuid.UUID | None = None,
    department: str | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_BIOMETRIC_EVENTS)),
) -> list[dict]:
    """A "violation" is any face-related alert whose severity is MEDIUM or above —
    RECOGNIZED events on authorized persons stay INFO and never surface here."""
    from app.schemas.alert import AlertResponse

    query = _face_alerts_query(db, tenant_filter_value(user)).filter(
        Alert.severity.in_([EventSeverity.MEDIUM, EventSeverity.HIGH, EventSeverity.CRITICAL])
    )
    if camera_id:
        query = query.filter(Alert.camera_id == camera_id)
    if department:
        query = (
            query.join(FaceRecognitionEvent, FaceRecognitionEvent.event_id == Alert.event_id)
            .join(Person, Person.id == FaceRecognitionEvent.person_id)
            .filter(Person.department == department)
        )
    rows = query.order_by(Alert.created_at.desc()).limit(limit).all()
    return [AlertResponse.model_validate(a).model_dump(mode="json") for a in rows]


@router.post("/face-alerts/{alert_id}/acknowledge", response_model=dict)
def acknowledge_face_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_ALERTS)),
) -> dict:
    from app.schemas.alert import AlertResponse

    tenant_id = tenant_filter_value(user)
    alert = db.get(Alert, alert_id)
    if alert is None or (tenant_id and alert.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return AlertResponse.model_validate(alert).model_dump(mode="json")


@router.get("/face-statistics")
def face_statistics(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_BIOMETRIC_EVENTS)),
) -> dict:
    tenant_id = tenant_filter_value(user)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    fe_query = db.query(FaceRecognitionEvent)
    if tenant_id:
        fe_query = fe_query.filter(FaceRecognitionEvent.tenant_id == tenant_id)
    today_events = fe_query.filter(FaceRecognitionEvent.event_timestamp >= today_start)

    alerts_today = _face_alerts_query(db, tenant_id).filter(Alert.created_at >= today_start)
    active_alerts = _face_alerts_query(db, tenant_id).filter(Alert.status != AlertStatus.RESOLVED)

    return {
        "recognized_today": today_events.filter(FaceRecognitionEvent.recognition_status == RecognitionStatus.RECOGNIZED).count(),
        "unknown_faces_today": today_events.filter(
            FaceRecognitionEvent.recognition_status.in_([RecognitionStatus.UNKNOWN, RecognitionStatus.LOW_CONFIDENCE])
        ).count(),
        "active_alerts": active_alerts.count(),
        "high_severity_active": active_alerts.filter(Alert.severity.in_([EventSeverity.HIGH, EventSeverity.CRITICAL])).count(),
        "violations_today": alerts_today.filter(
            Alert.severity.in_([EventSeverity.MEDIUM, EventSeverity.HIGH, EventSeverity.CRITICAL])
        ).count(),
        "after_hours_events_today": alerts_today.filter(Alert.alert_type == "FACE_AFTER_HOURS").count(),
        "restricted_area_events_today": alerts_today.filter(Alert.alert_type == "FACE_RESTRICTED_AREA").count(),
    }


# ---- Settings (section 22) ----


@router.get("/face-settings", response_model=FaceRecognitionSettingsResponse)
def get_face_settings(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_BIOMETRICS)),
) -> FaceRecognitionSettings:
    return _get_or_create_settings(db, user.tenant_id)


@router.put("/face-settings", response_model=FaceRecognitionSettingsResponse)
def update_face_settings(
    payload: FaceRecognitionSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_BIOMETRICS)),
) -> FaceRecognitionSettings:
    row = _get_or_create_settings(db, user.tenant_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    log_action(
        db, action="FACE_SETTINGS_UPDATED", tenant_id=user.tenant_id, user_id=user.id,
        resource_type="face_recognition_settings", resource_id=str(row.id),
        ip_address=_client_ip(request), details=data,
    )
    return row
