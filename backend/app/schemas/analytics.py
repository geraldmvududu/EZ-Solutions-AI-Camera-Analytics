from datetime import datetime

from pydantic import BaseModel


class NamedCount(BaseModel):
    label: str
    count: int


class HourlyCount(BaseModel):
    hour: int  # 0-23
    count: int


class AnalyticsSummary(BaseModel):
    range_start: datetime
    range_end: datetime
    total_events: int
    total_alerts: int
    total_detections: int
    events_by_camera: list[NamedCount]
    events_by_hour: list[HourlyCount]
    alerts_by_severity: list[NamedCount]
    detections_by_object_type: list[NamedCount]
    most_active_cameras: list[NamedCount]
    camera_status_summary: list[NamedCount]
    storage_used_bytes: int
    storage_total_bytes: int
