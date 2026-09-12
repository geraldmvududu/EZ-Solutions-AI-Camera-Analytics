"""PDF security report's "AI Video Intelligence Incidents" section
(app/services/analytics_service.py::get_incident_type_report_data) — a real GROUP BY
over Incident rows, same convention as the Face Recognition section. Unlike that
section, no extra permission gate: Incidents are already visible to anyone who can
view the report."""

import app.api.routes.reports as reports_module
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def test_get_incident_type_report_data_counts_by_category(db_session, tenant):
    from app.models.camera import Camera, CameraSourceType
    from app.models.incident import Incident, IncidentStatus
    from app.models.event import EventSeverity
    from app.services.analytics_service import get_incident_type_report_data
    from datetime import datetime, timezone

    camera = Camera(tenant_id=tenant.id, camera_code="CAM-001", name="Perimeter", source_type=CameraSourceType.SIMULATED)
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)

    for incident_type in ["GATE_JUMPING_DETECTED", "GATE_JUMPING_DETECTED", "TAILGATING_DETECTED"]:
        db_session.add(Incident(
            tenant_id=tenant.id, title="x", severity=EventSeverity.HIGH, camera_id=camera.id,
            status=IncidentStatus.OPEN, incident_type=incident_type,
        ))
    db_session.commit()

    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = datetime(2030, 1, 1, tzinfo=timezone.utc)
    rows = get_incident_type_report_data(db_session, tenant.id, start, end)
    counts = {r.label: r.count for r in rows}
    assert counts["GATE_JUMPING_DETECTED"] == 2
    assert counts["TAILGATING_DETECTED"] == 1


def test_security_report_pdf_includes_video_intelligence_section(client, admin_user, monkeypatch):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Perimeter", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "GATE_JUMPING_DETECTED", "severity": "HIGH",
            "occurred_at": "2026-01-01T12:00:00Z", "event_metadata": {"tracking_id": 1, "confidence": 0.9},
        },
        headers=INTERNAL_HEADERS,
    )

    captured = {}
    real_builder = reports_module.build_security_report_pdf

    def spy(summary, tenant_name, face_recognition_by_status=None, top_recognized_people=None, video_intelligence_incidents=None):
        captured["video_intelligence_incidents"] = video_intelligence_incidents
        return real_builder(summary, tenant_name, face_recognition_by_status, top_recognized_people, video_intelligence_incidents)

    monkeypatch.setattr(reports_module, "build_security_report_pdf", spy)

    resp = client.get("/api/reports/security-report.pdf?start=2020-01-01T00:00:00Z&end=2030-01-01T00:00:00Z", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"
    assert captured["video_intelligence_incidents"] is not None
    assert any(c.label == "GATE_JUMPING_DETECTED" and c.count == 1 for c in captured["video_intelligence_incidents"])
