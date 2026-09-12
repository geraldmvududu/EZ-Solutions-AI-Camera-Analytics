from fastapi import APIRouter

from app.api.routes import (
    alerts,
    analytics,
    audit_logs,
    auth,
    cameras,
    detections,
    events,
    faces,
    incidents,
    notifications,
    push_tokens,
    recordings,
    reports,
    rules,
    snapshots,
    system,
    tripwires,
    users,
    video_intelligence,
    ws,
    zones,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(cameras.router)
api_router.include_router(events.router)
api_router.include_router(alerts.router)
api_router.include_router(recordings.router)
api_router.include_router(snapshots.router)
api_router.include_router(detections.router)
api_router.include_router(faces.router)
api_router.include_router(rules.router)
api_router.include_router(zones.router)
api_router.include_router(tripwires.router)
api_router.include_router(incidents.router)
api_router.include_router(system.router)
api_router.include_router(audit_logs.router)
api_router.include_router(analytics.router)
api_router.include_router(reports.router)
api_router.include_router(push_tokens.router)
api_router.include_router(notifications.router)
api_router.include_router(video_intelligence.router)
api_router.include_router(ws.router)
