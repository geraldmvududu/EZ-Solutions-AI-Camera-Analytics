"""Real analytics aggregates (section 36) — every number here is a GROUP BY query
against Detection/Event/Alert/Camera rows for the requested date range and tenant.
Nothing is precomputed/sampled/faked."""

import shutil
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.alert import Alert
from app.models.camera import Camera
from app.models.detection import Detection
from app.models.event import Event
from app.schemas.analytics import AnalyticsSummary, HourlyCount, NamedCount

settings = get_settings()


def get_analytics_summary(
    db: Session,
    tenant_id: uuid.UUID | None,
    start: datetime | None,
    end: datetime | None,
    camera_id: uuid.UUID | None = None,
) -> AnalyticsSummary:
    range_end = end or datetime.now(timezone.utc)
    range_start = start or (range_end - timedelta(days=7))

    def scope(query, model):
        query = query.filter(model.occurred_at >= range_start, model.occurred_at <= range_end) if hasattr(model, "occurred_at") else query
        if tenant_id:
            query = query.filter(model.tenant_id == tenant_id)
        if camera_id and hasattr(model, "camera_id"):
            query = query.filter(model.camera_id == camera_id)
        return query

    # Events by camera
    events_by_camera_rows = (
        scope(db.query(Camera.name, func.count(Event.id)).join(Event, Event.camera_id == Camera.id), Event)
        .group_by(Camera.name)
        .order_by(func.count(Event.id).desc())
        .all()
    )
    events_by_camera = [NamedCount(label=name, count=count) for name, count in events_by_camera_rows]

    # Events by hour-of-day (0-23)
    hour_expr = func.extract("hour", Event.occurred_at)
    events_by_hour_rows = (
        scope(db.query(hour_expr, func.count(Event.id)), Event).group_by(hour_expr).all()
    )
    hour_counts = {int(hour): count for hour, count in events_by_hour_rows}
    events_by_hour = [HourlyCount(hour=h, count=hour_counts.get(h, 0)) for h in range(24)]

    # Alerts by severity — Alert doesn't have occurred_at, filter on created_at instead.
    alerts_query = db.query(Alert.severity, func.count(Alert.id)).filter(
        Alert.created_at >= range_start, Alert.created_at <= range_end
    )
    if tenant_id:
        alerts_query = alerts_query.filter(Alert.tenant_id == tenant_id)
    if camera_id:
        alerts_query = alerts_query.filter(Alert.camera_id == camera_id)
    alerts_by_severity_rows = alerts_query.group_by(Alert.severity).all()
    alerts_by_severity = [NamedCount(label=sev.value if hasattr(sev, "value") else sev, count=count) for sev, count in alerts_by_severity_rows]

    # Detections by object type
    detections_query = db.query(Detection.object_type, func.count(Detection.id)).filter(
        Detection.detected_at >= range_start, Detection.detected_at <= range_end
    )
    if tenant_id:
        detections_query = detections_query.filter(Detection.tenant_id == tenant_id)
    if camera_id:
        detections_query = detections_query.filter(Detection.camera_id == camera_id)
    detections_by_type_rows = detections_query.group_by(Detection.object_type).all()
    detections_by_object_type = [
        NamedCount(label=obj_type.value if hasattr(obj_type, "value") else obj_type, count=count)
        for obj_type, count in detections_by_type_rows
    ]

    most_active_cameras = sorted(events_by_camera, key=lambda x: x.count, reverse=True)[:5]

    # Camera status summary (current, real-time — not historical uptime tracking yet;
    # see CLAUDE.md "Known limitations" for the honest scope of this metric).
    camera_status_query = db.query(Camera.status, func.count(Camera.id))
    if tenant_id:
        camera_status_query = camera_status_query.filter(Camera.tenant_id == tenant_id)
    camera_status_rows = camera_status_query.group_by(Camera.status).all()
    camera_status_summary = [
        NamedCount(label=status.value if hasattr(status, "value") else status, count=count)
        for status, count in camera_status_rows
    ]

    total_events = scope(db.query(func.count(Event.id)), Event).scalar() or 0

    # NOTE: alerts_query/detections_query above already select an aggregate column
    # (func.count(...)) without GROUP BY applied to the variable itself (.group_by()
    # returns a new Query, it doesn't mutate the original) — calling .count() directly
    # on them would count the single collapsed aggregate row, not the real row count.
    # Use plain row-count queries with the same filters instead.
    total_alerts_query = db.query(Alert).filter(Alert.created_at >= range_start, Alert.created_at <= range_end)
    if tenant_id:
        total_alerts_query = total_alerts_query.filter(Alert.tenant_id == tenant_id)
    if camera_id:
        total_alerts_query = total_alerts_query.filter(Alert.camera_id == camera_id)
    total_alerts = total_alerts_query.count()

    total_detections_query = db.query(Detection).filter(Detection.detected_at >= range_start, Detection.detected_at <= range_end)
    if tenant_id:
        total_detections_query = total_detections_query.filter(Detection.tenant_id == tenant_id)
    if camera_id:
        total_detections_query = total_detections_query.filter(Detection.camera_id == camera_id)
    total_detections = total_detections_query.count()

    try:
        total, used, _free = shutil.disk_usage(settings.storage_path)
    except FileNotFoundError:
        total, used = 0, 0

    return AnalyticsSummary(
        range_start=range_start,
        range_end=range_end,
        total_events=total_events,
        total_alerts=total_alerts,
        total_detections=total_detections,
        events_by_camera=events_by_camera,
        events_by_hour=events_by_hour,
        alerts_by_severity=alerts_by_severity,
        detections_by_object_type=detections_by_object_type,
        most_active_cameras=most_active_cameras,
        camera_status_summary=camera_status_summary,
        storage_used_bytes=used,
        storage_total_bytes=total,
    )
