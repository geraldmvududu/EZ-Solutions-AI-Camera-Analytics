"""Thin HTTP client the ai-engine uses to report real detections/events/recordings back
to the backend API. Every call here corresponds to an internal-service-authenticated
FastAPI endpoint in backend/app/api/routes — there is no local database in this
service; the backend/PostgreSQL is the single source of truth (section 51)."""

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("ai-engine.backend_client")
settings = get_settings()


class BackendClient:
    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=settings.api_url,
            headers={"X-Internal-Token": settings.internal_service_token},
            timeout=10.0,
        )

    def list_active_cameras(self) -> list[dict]:
        try:
            resp = self._client.get("/api/cameras/internal/active")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch active cameras: %s", exc)
            return []

    def get_stream_info(self, camera_id: str) -> dict | None:
        try:
            resp = self._client.get(f"/api/cameras/{camera_id}/internal/stream-info")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch stream info for %s: %s", camera_id, exc)
            return None

    def list_zones(self) -> list[dict]:
        return self._safe_get("/api/zones/internal/all")

    def list_tripwires(self) -> list[dict]:
        return self._safe_get("/api/tripwires/internal/all")

    def _safe_get(self, path: str) -> list[dict]:
        try:
            resp = self._client.get(path)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            logger.warning("GET %s failed: %s", path, exc)
            return []

    def heartbeat(self, camera_id: str) -> None:
        self._safe_post(f"/api/cameras/{camera_id}/heartbeat", {})

    def create_detection(self, payload: dict) -> dict | None:
        return self._safe_post("/api/detections", payload)

    def create_event(self, payload: dict) -> dict | None:
        return self._safe_post("/api/events", payload)

    def create_snapshot(self, payload: dict) -> dict | None:
        return self._safe_post("/api/snapshots", payload)

    def create_recording(self, payload: dict) -> dict | None:
        return self._safe_post("/api/recordings", payload)

    def _safe_post(self, path: str, payload: dict) -> dict | None:
        try:
            resp = self._client.post(path, json=payload)
            resp.raise_for_status()
            return resp.json() if resp.content else None
        except httpx.HTTPError as exc:
            logger.warning("POST %s failed: %s", path, exc)
            return None


backend_client = BackendClient()
