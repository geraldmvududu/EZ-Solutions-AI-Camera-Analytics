import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.alert import Alert
from app.models.event import Event
from app.models.face_recognition_event import FaceRecognitionEvent
from app.models.tenant import Tenant
from app.models.user import User
from app.services.analytics_service import get_analytics_summary, get_face_recognition_report_data
from app.services.report_service import alerts_to_csv, build_security_report_pdf, events_to_csv, face_appearances_to_csv

router = APIRouter(prefix="/reports", tags=["reports"])


def _apply_range(query, model, start: datetime | None, end: datetime | None, date_field: str):
    if start:
        query = query.filter(getattr(model, date_field) >= start)
    if end:
        query = query.filter(getattr(model, date_field) <= end)
    return query


@router.get("/events.csv")
def export_events_csv(
    start: datetime | None = None,
    end: datetime | None = None,
    camera_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_REPORTS)),
) -> Response:
    query = db.query(Event)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Event.tenant_id == tenant_id)
    if camera_id:
        query = query.filter(Event.camera_id == camera_id)
    query = _apply_range(query, Event, start, end, "occurred_at")

    events = query.order_by(Event.occurred_at.desc()).limit(50_000).all()
    csv_content = events_to_csv(events)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=events.csv"},
    )


@router.get("/alerts.csv")
def export_alerts_csv(
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_REPORTS)),
) -> Response:
    query = db.query(Alert)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(Alert.tenant_id == tenant_id)
    query = _apply_range(query, Alert, start, end, "created_at")

    alerts = query.order_by(Alert.created_at.desc()).limit(50_000).all()
    csv_content = alerts_to_csv(alerts)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=alerts.csv"},
    )


@router.get("/face-appearances.csv")
def export_face_appearances_csv(
    person_id: uuid.UUID,
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_BIOMETRIC_EVENTS)),
) -> Response:
    query = db.query(FaceRecognitionEvent).filter(FaceRecognitionEvent.person_id == person_id)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(FaceRecognitionEvent.tenant_id == tenant_id)
    query = _apply_range(query, FaceRecognitionEvent, start, end, "event_timestamp")

    appearances = query.order_by(FaceRecognitionEvent.event_timestamp.desc()).limit(50_000).all()
    csv_content = face_appearances_to_csv(appearances)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=face-appearances.csv"},
    )


@router.get("/security-report.pdf")
def export_security_report_pdf(
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_REPORTS)),
) -> Response:
    tenant_id = tenant_filter_value(user)
    range_end = end or datetime.now(timezone.utc)
    range_start = start or (range_end - timedelta(days=1))

    summary = get_analytics_summary(db, tenant_id, range_start, range_end)
    tenant = db.get(Tenant, user.tenant_id)

    # Same permission that gates the dedicated face-appearances.csv export — a user
    # who can't view biometric events gets a complete report minus this one section,
    # not a 403 on the whole PDF.
    face_recognition_by_status = None
    top_recognized_people = None
    if Permissions.VIEW_BIOMETRIC_EVENTS in {p.code for p in user.role.permissions}:
        face_recognition_by_status, top_recognized_people = get_face_recognition_report_data(db, tenant_id, range_start, range_end)

    pdf_bytes = build_security_report_pdf(
        summary,
        tenant.name if tenant else "EZ Solutions",
        face_recognition_by_status=face_recognition_by_status,
        top_recognized_people=top_recognized_people,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=security-report.pdf"},
    )
