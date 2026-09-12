"""Live facial-recognition pipeline stage (spec sections 4/19): runs on already-
tracked PERSON detections only (never every frame — worker.py already throttles AI
inference to ai_fps, and this adds a further per-track cooldown on top), respects
FACE_DETECTION/FACE_EXCLUSION zones and a per-camera operating-hours window, and never
lets a recognition failure interrupt the camera's capture/recording loop — every
public method here is exception-safe by design (see maybe_recognize's try/except).
"""

import logging
import time
from datetime import datetime, timezone
from datetime import time as dt_time

from app.backend_client import backend_client
from app.config import get_settings
from app.core import face_embedding
from app.core.snapshotter import save_snapshot
from app.core.zones import point_in_polygon
from app.detectors.base import Detection

logger = logging.getLogger("ai-engine.face_recognizer")
settings = get_settings()


def _within_operating_hours(camera: dict, now: dt_time | None = None) -> bool:
    start, end = camera.get("face_operating_hours_start") or "", camera.get("face_operating_hours_end") or ""
    if not start or not end:
        return True
    try:
        sh, sm = (int(p) for p in start.split(":"))
        eh, em = (int(p) for p in end.split(":"))
    except ValueError:
        return True
    now = now if now is not None else datetime.now().time()
    start_t, end_t = dt_time(sh, sm), dt_time(eh, em)
    if start_t <= end_t:
        return start_t <= now <= end_t
    return now >= start_t or now <= end_t  # window wraps past midnight


class FaceRecognizer:
    def __init__(self, camera_id: str) -> None:
        self.camera_id = camera_id
        self._last_attempt: dict[int, float] = {}

    def maybe_recognize(self, camera: dict, frame, track_id: int, detection: Detection, centroid, face_zones: list[dict]) -> None:
        try:
            self._maybe_recognize(camera, frame, track_id, detection, centroid, face_zones)
        except Exception:
            # Never let a recognition bug take down the worker's capture loop — real
            # motion/AI/recording must keep running even if this stage misbehaves.
            logger.exception("Camera %s: face recognition failed for track %s", self.camera_id, track_id)

    def _maybe_recognize(self, camera: dict, frame, track_id: int, detection: Detection, centroid, face_zones: list[dict]) -> None:
        cooldown = settings.face_event_cooldown
        now = time.time()
        if now - self._last_attempt.get(track_id, 0.0) < cooldown:
            return

        if not _within_operating_hours(camera):
            return

        exclusion_zones = [z for z in face_zones if z["zone_type"] == "FACE_EXCLUSION"]
        if any(point_in_polygon(centroid, z.get("polygon", [])) for z in exclusion_zones):
            return

        detection_zones = [z for z in face_zones if z["zone_type"] == "FACE_DETECTION"]
        if detection_zones and not any(point_in_polygon(centroid, z.get("polygon", [])) for z in detection_zones):
            return

        h, w = frame.shape[:2]
        x1 = max(0, int(detection.x * w))
        y1 = max(0, int(detection.y * h))
        x2 = min(w, int((detection.x + detection.width) * w))
        y2 = min(h, int((detection.y + detection.height) * h))
        if x2 <= x1 or y2 <= y1:
            return
        crop = frame[y1:y2, x1:x2]

        quality = face_embedding.assess_recognition_quality(crop, settings.face_min_quality)
        if not quality.passed:
            return

        vector = face_embedding.compute_embedding(crop, quality.face)
        self._last_attempt[track_id] = now

        snapshot_id = None
        try:
            file_path = save_snapshot(self.camera_id, frame)
            record = backend_client.create_snapshot(
                {
                    "camera_id": self.camera_id,
                    "file_path": file_path,
                    "taken_at": datetime.now(timezone.utc).isoformat(),
                    "object_type": "PERSON",
                    "confidence": detection.confidence,
                }
            )
            snapshot_id = record.get("id") if record else None
        except Exception:
            logger.exception("Camera %s: failed to save face-recognition snapshot", self.camera_id)

        result = backend_client.recognize_face(
            {
                "camera_id": self.camera_id,
                "tracking_id": track_id,
                "embedding": vector.tolist(),
                "model_version": face_embedding.FACE_MODEL_VERSION,
                "quality_score": quality.quality_score,
                "snapshot_id": snapshot_id,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        if result:
            logger.info(
                "Camera %s: face recognition result — %s (%.1f%% confidence)",
                self.camera_id, result.get("recognition_status"), (result.get("confidence_score") or 0) * 100,
            )
