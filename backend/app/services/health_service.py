"""Real system health checks — actual psutil metrics and actual connectivity probes to
Postgres/Redis, not hardcoded values (section 33)."""

import os
import shutil

import psutil
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.schemas.system import ComponentHealth, SystemHealthResponse

settings = get_settings()


def _status_for(is_ok: bool, warn: bool = False) -> str:
    if not is_ok:
        return "CRITICAL"
    return "WARNING" if warn else "HEALTHY"


def check_database(db: Session) -> ComponentHealth:
    try:
        db.execute(text("SELECT 1"))
        return ComponentHealth(component="DATABASE", status="HEALTHY")
    except Exception as exc:  # pragma: no cover - depends on live DB state
        return ComponentHealth(component="DATABASE", status="CRITICAL", message=str(exc))


def check_redis() -> ComponentHealth:
    try:
        import redis

        client = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        return ComponentHealth(component="REDIS", status="HEALTHY")
    except Exception as exc:
        return ComponentHealth(component="REDIS", status="WARNING", message=str(exc))


def check_storage() -> ComponentHealth:
    try:
        total, used, free = shutil.disk_usage(settings.storage_path)
        percent_used = (used / total) * 100 if total else 0
        status = _status_for(percent_used < 95, warn=percent_used > 85)
        return ComponentHealth(
            component="STORAGE",
            status=status,
            metrics={"total_bytes": total, "used_bytes": used, "free_bytes": free, "percent_used": round(percent_used, 1)},
        )
    except Exception as exc:
        return ComponentHealth(component="STORAGE", status="WARNING", message=str(exc))


def get_system_health(db: Session) -> SystemHealthResponse:
    cpu_percent = psutil.cpu_percent(interval=0.2)
    ram = psutil.virtual_memory()
    try:
        disk = psutil.disk_usage(settings.storage_path)
    except FileNotFoundError:
        disk = psutil.disk_usage(os.getcwd())

    components = [
        check_database(db),
        check_redis(),
        check_storage(),
        ComponentHealth(component="API", status="HEALTHY"),
    ]

    overall = "HEALTHY"
    if any(c.status == "CRITICAL" for c in components):
        overall = "CRITICAL"
    elif any(c.status == "WARNING" for c in components):
        overall = "WARNING"

    return SystemHealthResponse(
        overall_status=overall,
        components=components,
        cpu_percent=cpu_percent,
        ram_percent=ram.percent,
        disk_percent=disk.percent,
        ai_device=settings.ai_device,
    )
