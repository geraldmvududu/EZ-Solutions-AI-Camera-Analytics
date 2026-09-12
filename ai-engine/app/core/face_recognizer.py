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

import cv2
import numpy as np

from app.backend_client import backend_client
from app.config import get_settings
from app.core import face_embedding
from app.core.snapshotter import save_snapshot
from app.core.zones import point_in_polygon
from app.detectors.base import Detection

logger = logging.getLogger("ai-engine.face_recognizer")
settings = get_settings()

# Liveness (section 13/22, camera["liveness_detection_enabled"] — a tenant setting
# flattened onto the camera dict by GET /cameras/internal/active): a real, but
# deliberately narrow, anti-static-photo check. Downsamples the current face crop and
# compares it to the PREVIOUS recognition attempt's crop for the same track; a nearly
# pixel-identical pair means the camera is looking at a static printed photo or a
# paused video frame held up to it, not a live face (real camera sensor noise alone
# guarantees some difference between two genuinely live captures). This explicitly
# does NOT defend against a moving photo, a played video, or a printed photo held with
# natural hand tremor — real biometric liveness needs IR/depth hardware this lab
# doesn't have. Documented as this exact narrow scope, not oversold.
_LIVENESS_DOWNSAMPLE_SIZE = 32
_LIVENESS_MIN_FRAME_DIFF = 0.5


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


# How long a RECOGNIZED result stays "known" for a track_id after the recognition
# call that produced it — long enough to bridge the gap between a recognition attempt
# and a later tripwire/zone check on the same still-tracked person (see
# worker.py::_check_tripwires/_check_zones, which call identity_for() to attach a
# recognized person's identity to a violation event), short enough that a stale
# identity can't linger indefinitely if a track_id were ever reused.
IDENTITY_FRESHNESS_SECONDS = 300


class FaceRecognizer:
    def __init__(self, camera_id: str) -> None:
        self.camera_id = camera_id
        self._last_attempt: dict[int, float] = {}
        self._known_identities: dict[int, tuple[float, dict]] = {}
        self._last_crop_downsampled: dict[int, np.ndarray] = {}

    def _passes_liveness_check(self, track_id: int, crop) -> bool:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        small = cv2.resize(gray, (_LIVENESS_DOWNSAMPLE_SIZE, _LIVENESS_DOWNSAMPLE_SIZE)).astype(np.float32)

        previous = self._last_crop_downsampled.get(track_id)
        self._last_crop_downsampled[track_id] = small
        if previous is None:
            return True  # nothing to compare against yet — fail open on the first attempt

        mean_diff = float(np.mean(np.abs(small - previous)))
        if mean_diff < _LIVENESS_MIN_FRAME_DIFF:
            logger.info("Camera %s: track %s failed liveness check (frame diff %.3f) — likely a static photo", self.camera_id, track_id, mean_diff)
            return False
        return True

    def identity_for(self, track_id: int) -> dict | None:
        """Returns the most recent RECOGNIZED result for this track_id
        ({"person_id", "person_name", "confidence_score"}), or None if this track has
        never been recognized or its last recognition has aged past
        IDENTITY_FRESHNESS_SECONDS. Used to correlate a known person with a tripwire/
        zone violation that fires independently of the recognition cooldown."""
        entry = self._known_identities.get(track_id)
        if entry is None:
            return None
        seen_at, identity = entry
        if time.time() - seen_at > IDENTITY_FRESHNESS_SECONDS:
            del self._known_identities[track_id]
            return None
        return identity

    def maybe_recognize(
        self, camera: dict, frame, track_id: int, detection: Detection, centroid, face_zones: list[dict], recording_id: str | None = None
    ) -> None:
        try:
            self._maybe_recognize(camera, frame, track_id, detection, centroid, face_zones, recording_id)
        except Exception:
            # Never let a recognition bug take down the worker's capture loop — real
            # motion/AI/recording must keep running even if this stage misbehaves.
            logger.exception("Camera %s: face recognition failed for track %s", self.camera_id, track_id)

    def _maybe_recognize(
        self, camera: dict, frame, track_id: int, detection: Detection, centroid, face_zones: list[dict], recording_id: str | None
    ) -> None:
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

        if camera.get("liveness_detection_enabled") and not self._passes_liveness_check(track_id, crop):
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
                "recording_id": recording_id,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        if result:
            logger.info(
                "Camera %s: face recognition result — %s (%.1f%% confidence)",
                self.camera_id, result.get("recognition_status"), (result.get("confidence_score") or 0) * 100,
            )
            if result.get("recognition_status") == "RECOGNIZED" and result.get("person_id"):
                self._known_identities[track_id] = (
                    now,
                    {
                        "person_id": result["person_id"],
                        "person_name": result.get("person_name"),
                        "confidence_score": result.get("confidence_score"),
                    },
                )
