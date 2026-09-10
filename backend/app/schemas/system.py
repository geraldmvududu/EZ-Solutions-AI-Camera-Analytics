from pydantic import BaseModel


class ComponentHealth(BaseModel):
    component: str
    status: str
    message: str = ""
    metrics: dict = {}


class SystemHealthResponse(BaseModel):
    overall_status: str
    components: list[ComponentHealth]
    cpu_percent: float
    ram_percent: float
    disk_percent: float
    ai_device: str


class DashboardStats(BaseModel):
    total_cameras: int
    online_cameras: int
    offline_cameras: int
    active_alerts: int
    critical_alerts: int
    events_today: int
    people_detected_today: int
    vehicles_detected_today: int
    motion_events_today: int
    ai_events_today: int
    recording_cameras: int
    storage_used_bytes: int
    storage_total_bytes: int
    cpu_percent: float
    ram_percent: float
    ai_processing_device: str
