from datetime import datetime, timezone

from app.models.camera import Camera, CameraSourceType
from app.models.detection import Detection, ObjectType
from app.models.event import Event, EventSeverity, EventType
from app.services.analytics_service import get_analytics_summary
from tests.conftest import auth_headers, login


def _make_camera(db_session, tenant):
    camera = Camera(tenant_id=tenant.id, camera_code="CAM-001", name="Front Gate", source_type=CameraSourceType.SIMULATED)
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)
    return camera


def test_total_counts_are_not_collapsed_by_aggregate_subquery(db_session, tenant):
    """Regression test: total_alerts/total_detections must reflect the real row count,
    not the row count of the GROUP-BY aggregate query (which is always 1 when there's
    at least one matching row, regardless of how many rows actually exist)."""
    camera = _make_camera(db_session, tenant)

    for i in range(3):
        detection = Detection(
            tenant_id=tenant.id, camera_id=camera.id, object_type=ObjectType.PERSON, confidence=0.9,
            bbox_x=0.1, bbox_y=0.1, bbox_width=0.2, bbox_height=0.4, tracking_id=i,
            detected_at=datetime.now(timezone.utc),
        )
        db_session.add(detection)
    db_session.commit()

    summary = get_analytics_summary(db_session, tenant.id, None, None)
    assert summary.total_detections == 3
    assert summary.detections_by_object_type == [{"label": "PERSON", "count": 3}] or summary.detections_by_object_type[0].count == 3


def test_events_by_hour_covers_all_24_hours(db_session, tenant):
    camera = _make_camera(db_session, tenant)
    event = Event(
        tenant_id=tenant.id, camera_id=camera.id, event_type=EventType.MOTION_DETECTED,
        severity=EventSeverity.INFO, occurred_at=datetime.now(timezone.utc), event_metadata={},
    )
    db_session.add(event)
    db_session.commit()

    summary = get_analytics_summary(db_session, tenant.id, None, None)
    assert len(summary.events_by_hour) == 24
    assert sum(h.count for h in summary.events_by_hour) == 1


def test_analytics_endpoint_requires_view_reports_permission(client, viewer_user):
    token = login(client, viewer_user.email)
    resp = client.get("/api/analytics/summary", headers=auth_headers(token))
    assert resp.status_code == 200  # VIEWER has view_reports by default


def test_reports_csv_endpoints_return_real_rows(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    client.post(
        "/api/events",
        json={
            "camera_id": cam["id"], "event_type": "MOTION_DETECTED", "severity": "INFO",
            "occurred_at": "2026-01-01T00:00:00Z", "event_metadata": {},
        },
        headers={"X-Internal-Token": "test-internal-token"},
    )

    resp = client.get("/api/reports/events.csv", headers=auth_headers(token))
    assert resp.status_code == 200
    assert "MOTION_DETECTED" in resp.text
    assert resp.headers["content-type"].startswith("text/csv")


def test_security_report_pdf_is_generated(client, admin_user):
    token = login(client, admin_user.email)
    resp = client.get("/api/reports/security-report.pdf", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"
