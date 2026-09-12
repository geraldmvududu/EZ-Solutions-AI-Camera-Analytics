"""PDF security report's Face Recognition section (app/services/analytics_service.py
::get_face_recognition_report_data, app/services/report_service.py
::build_security_report_pdf): a real GROUP BY aggregate over FaceRecognitionEvent rows,
gated behind the same view_biometric_events permission as the existing
face-appearances.csv export — a user who can't see biometric events gets a complete
report minus this one section, not a 403 on the whole PDF."""

from datetime import datetime, timezone

import app.api.routes.reports as reports_module
from app.models.camera import Camera, CameraSourceType
from app.models.event import Event, EventType
from app.models.face_recognition_event import FaceRecognitionEvent, RecognitionStatus
from app.models.person import Person, PersonCategory
from app.services.analytics_service import get_face_recognition_report_data
from tests.conftest import auth_headers, login

RANGE_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
RANGE_END = datetime(2026, 1, 2, tzinfo=timezone.utc)


def _make_camera(db_session, tenant) -> Camera:
    camera = Camera(tenant_id=tenant.id, camera_code="CAM-001", name="Front Gate", source_type=CameraSourceType.SIMULATED)
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)
    return camera


def _make_person(db_session, tenant, first_name: str) -> Person:
    person = Person(tenant_id=tenant.id, first_name=first_name, last_name="Doe", category=PersonCategory.EMPLOYEE)
    db_session.add(person)
    db_session.commit()
    db_session.refresh(person)
    return person


def _make_face_event(db_session, tenant, camera, person, status: RecognitionStatus, when: datetime) -> FaceRecognitionEvent:
    event = Event(
        tenant_id=tenant.id, camera_id=camera.id,
        event_type=EventType.FACE_RECOGNIZED if status == RecognitionStatus.RECOGNIZED else EventType.UNKNOWN_FACE_DETECTED,
        occurred_at=when,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    face_event = FaceRecognitionEvent(
        tenant_id=tenant.id, event_id=event.id, camera_id=camera.id,
        person_id=person.id if person else None,
        confidence_score=0.9, recognition_status=status, event_timestamp=when,
    )
    db_session.add(face_event)
    db_session.commit()
    return face_event


def test_get_face_recognition_report_data_counts_by_status_and_ranks_top_people(db_session, tenant):
    camera = _make_camera(db_session, tenant)
    jane = _make_person(db_session, tenant, "Jane")
    bob = _make_person(db_session, tenant, "Bob")
    when = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    _make_face_event(db_session, tenant, camera, jane, RecognitionStatus.RECOGNIZED, when)
    _make_face_event(db_session, tenant, camera, jane, RecognitionStatus.RECOGNIZED, when)
    _make_face_event(db_session, tenant, camera, bob, RecognitionStatus.RECOGNIZED, when)
    _make_face_event(db_session, tenant, camera, None, RecognitionStatus.UNKNOWN, when)

    by_status, top_people = get_face_recognition_report_data(db_session, tenant.id, RANGE_START, RANGE_END)

    status_counts = {c.label: c.count for c in by_status}
    assert status_counts["RECOGNIZED"] == 3
    assert status_counts["UNKNOWN"] == 1

    assert len(top_people) == 2
    assert top_people[0].label == "Jane Doe"
    assert top_people[0].count == 2
    assert top_people[1].label == "Bob Doe"
    assert top_people[1].count == 1


def test_get_face_recognition_report_data_excludes_events_outside_range(db_session, tenant):
    camera = _make_camera(db_session, tenant)
    jane = _make_person(db_session, tenant, "Jane")
    _make_face_event(db_session, tenant, camera, jane, RecognitionStatus.RECOGNIZED, datetime(2025, 6, 1, tzinfo=timezone.utc))

    by_status, top_people = get_face_recognition_report_data(db_session, tenant.id, RANGE_START, RANGE_END)

    assert by_status == []
    assert top_people == []


def test_security_report_pdf_includes_face_section_for_permitted_user(client, db_session, admin_user, tenant, monkeypatch):
    camera = _make_camera(db_session, tenant)
    jane = _make_person(db_session, tenant, "Jane")
    _make_face_event(db_session, tenant, camera, jane, RecognitionStatus.RECOGNIZED, datetime.now(timezone.utc))

    captured = {}
    real_builder = reports_module.build_security_report_pdf

    def spy(summary, tenant_name, face_recognition_by_status=None, top_recognized_people=None, video_intelligence_incidents=None):
        captured["face_recognition_by_status"] = face_recognition_by_status
        captured["top_recognized_people"] = top_recognized_people
        return real_builder(summary, tenant_name, face_recognition_by_status, top_recognized_people, video_intelligence_incidents)

    monkeypatch.setattr(reports_module, "build_security_report_pdf", spy)

    token = login(client, admin_user.email)
    resp = client.get("/api/reports/security-report.pdf", headers=auth_headers(token))

    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"
    # ADMIN has view_biometric_events (ROLE_PERMISSION_MAP) — the section must be populated.
    assert captured["face_recognition_by_status"] is not None
    assert any(c.label == "RECOGNIZED" and c.count == 1 for c in captured["face_recognition_by_status"])
    assert captured["top_recognized_people"][0].label == "Jane Doe"


def test_security_report_pdf_omits_face_section_without_permission(client, viewer_user, monkeypatch):
    captured = {}
    real_builder = reports_module.build_security_report_pdf

    def spy(summary, tenant_name, face_recognition_by_status=None, top_recognized_people=None, video_intelligence_incidents=None):
        captured["face_recognition_by_status"] = face_recognition_by_status
        captured["top_recognized_people"] = top_recognized_people
        return real_builder(summary, tenant_name, face_recognition_by_status, top_recognized_people, video_intelligence_incidents)

    monkeypatch.setattr(reports_module, "build_security_report_pdf", spy)

    token = login(client, viewer_user.email)
    resp = client.get("/api/reports/security-report.pdf", headers=auth_headers(token))

    # VIEWER has view_reports but not view_biometric_events (ROLE_PERMISSION_MAP) —
    # the whole report must still succeed, just without the biometric section.
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"
    assert captured["face_recognition_by_status"] is None
    assert captured["top_recognized_people"] is None
