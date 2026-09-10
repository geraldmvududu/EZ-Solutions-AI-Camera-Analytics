"""ai-engine entrypoint: discovers active cameras from the backend and keeps one
CameraWorker running per camera, restarting discovery periodically so newly-added or
newly-enabled cameras get picked up without a restart (and removed ones get stopped).
"""

import json
import logging
import signal
import sys
import time

from app.backend_client import backend_client
from app.config import get_settings
from app.streaming import start_stream_server
from app.worker import CameraWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ai-engine.main")
settings = get_settings()

_running = True


def _handle_shutdown(signum, frame) -> None:
    global _running
    logger.info("Shutdown signal received")
    _running = False


# Fields that change as a side effect of a worker simply running (its own heartbeat
# calls, status flips) — these must be excluded from the fingerprint, or every camera
# would look "changed" on every discovery cycle and restart forever.
_VOLATILE_CAMERA_FIELDS = {"last_heartbeat_at", "status", "created_at", "updated_at"}


def _config_fingerprint(camera: dict, zones: list[dict], tripwires: list[dict]) -> str:
    """A CameraWorker only reads its camera/zones/tripwires once, at construction —
    so if any of them change (a zone added/edited, recording settings changed) while a
    worker is already running, that change is invisible until the worker restarts.
    Comparing this fingerprint each discovery cycle lets main() restart just the
    affected worker instead of requiring a manual/full ai-engine restart."""
    stable_camera = {k: v for k, v in camera.items() if k not in _VOLATILE_CAMERA_FIELDS}
    relevant_zones = [z for z in zones if z["camera_id"] == camera["id"]]
    relevant_tripwires = [t for t in tripwires if t["camera_id"] == camera["id"]]
    return json.dumps([stable_camera, relevant_zones, relevant_tripwires], sort_keys=True, default=str)


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    workers: dict[str, CameraWorker] = {}
    worker_fingerprints: dict[str, str] = {}
    failed_until: dict[str, float] = {}
    RETRY_BACKOFF_SECONDS = 60

    logger.info("EZ Solutions AI Engine starting — device=%s, backend=%s", settings.ai_device, settings.api_url)
    start_stream_server(settings.stream_port)

    while _running:
        cameras = backend_client.list_active_cameras()
        zones = backend_client.list_zones()
        tripwires = backend_client.list_tripwires()
        active_ids = {c["id"] for c in cameras}

        for camera_id in list(workers):
            if camera_id not in active_ids or not workers[camera_id].is_alive():
                logger.info("Stopping worker for camera %s", camera_id)
                workers.pop(camera_id).stop()
                worker_fingerprints.pop(camera_id, None)
                # A worker that exited on its own (e.g. couldn't open its source) is
                # backed off rather than retried every discovery cycle.
                failed_until[camera_id] = time.time() + RETRY_BACKOFF_SECONDS

        # Restart any still-running worker whose camera config, zones, or tripwires
        # changed since it was started (see _config_fingerprint's docstring).
        for camera in cameras:
            camera_id = camera["id"]
            if camera_id not in workers:
                continue
            fingerprint = _config_fingerprint(camera, zones, tripwires)
            if worker_fingerprints.get(camera_id) != fingerprint:
                logger.info("Config changed for camera '%s' — restarting worker", camera["name"])
                workers.pop(camera_id).stop()
                worker_fingerprints.pop(camera_id, None)

        now = time.time()
        for camera in cameras:
            if camera["id"] in workers:
                continue
            if now < failed_until.get(camera["id"], 0):
                continue
            logger.info("Starting worker for camera '%s' (%s)", camera["name"], camera["source_type"])
            try:
                worker = CameraWorker(camera, zones, tripwires)
                worker.start()
                workers[camera["id"]] = worker
                worker_fingerprints[camera["id"]] = _config_fingerprint(camera, zones, tripwires)
            except Exception:
                logger.exception("Failed to start worker for camera %s", camera["name"])
                failed_until[camera["id"]] = time.time() + RETRY_BACKOFF_SECONDS

        for _ in range(settings.camera_discovery_interval_seconds):
            if not _running:
                break
            time.sleep(1)

    logger.info("Stopping all camera workers...")
    for worker in workers.values():
        worker.stop()
    sys.exit(0)


if __name__ == "__main__":
    main()
