"""Dashboard aggregate statistics — every number here is a real query against the
database; there is no seeded/fake data path (section 1)."""

import shutil
import uuid
from datetime import datetime, time, timezone

import psutil
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.alert import Alert, AlertStatus
from app.models.camera import Camera, CameraStatus
from app.models.event import Event, EventSeverity, EventType
from app.schemas.system import DashboardStats

settings = get_settings()


def get_dashboard_stats(db: Session, tenant_id: uuid.UUID | None) -> DashboardStats:
    def scoped(query):
        return query.filter(Camera.tenant_id == tenant_id) if tenant_id else query

    camera_q = scoped(db.query(Camera))
    total_cameras = camera_q.count()
    online_cameras = camera_q.filter(Camera.status == CameraStatus.ONLINE).count()
    offline_cameras = total_cameras - online_cameras
    recording_cameras = camera_q.filter(Camera.recording_enabled.is_(True), Camera.status == CameraStatus.ONLINE).count()

    def scoped_alerts(query):
        return query.filter(Alert.tenant_id == tenant_id) if tenant_id else query

    active_alert_statuses = [AlertStatus.NEW, AlertStatus.ACKNOWLEDGED, AlertStatus.INVESTIGATING]
    active_alerts = scoped_alerts(db.query(Alert)).filter(Alert.status.in_(active_alert_statuses)).count()
    critical_alerts = scoped_alerts(db.query(Alert)).filter(
        Alert.status.in_(active_alert_statuses), Alert.severity == EventSeverity.CRITICAL
    ).count()

    today_start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)

    def scoped_events(query):
        query = query.filter(Event.occurred_at >= today_start)
        return query.filter(Event.tenant_id == tenant_id) if tenant_id else query

    events_today = scoped_events(db.query(Event)).count()
    people_detected_today = scoped_events(db.query(Event)).filter(Event.event_type == EventType.PERSON_DETECTED).count()
    vehicles_detected_today = scoped_events(db.query(Event)).filter(Event.event_type == EventType.VEHICLE_DETECTED).count()
    motion_events_today = scoped_events(db.query(Event)).filter(Event.event_type == EventType.MOTION_DETECTED).count()
    ai_events_today = scoped_events(db.query(Event)).filter(Event.event_type == EventType.AI_DETECTION).count()

    try:
        total, used, _free = shutil.disk_usage(settings.storage_path)
    except FileNotFoundError:
        total, used = 0, 0

    return DashboardStats(
        total_cameras=total_cameras,
        online_cameras=online_cameras,
        offline_cameras=offline_cameras,
        active_alerts=active_alerts,
        critical_alerts=critical_alerts,
        events_today=events_today,
        people_detected_today=people_detected_today,
        vehicles_detected_today=vehicles_detected_today,
        motion_events_today=motion_events_today,
        ai_events_today=ai_events_today,
        recording_cameras=recording_cameras,
        storage_used_bytes=used,
        storage_total_bytes=total,
        cpu_percent=psutil.cpu_percent(interval=0.1),
        ram_percent=psutil.virtual_memory().percent,
        ai_processing_device=settings.ai_device,
    )
