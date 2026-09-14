"""Master Development Prompt Phase 1, "License Plate Reading (ANPR)": mirrors
face_recognizer.py's structure exactly — per-track cooldown, an exception-safe wrapper
so a recognition bug can never stop the camera's capture loop — applied to already-
tracked CAR/TRUCK/BUS/MOTORCYCLE detections (needs Camera.multi_class_detection_enabled,
same as theft detection, since the default HOG detector never emits vehicle-class
detections for this to run against at all).

Real, honest, staged approach (see CLAUDE.md for the full disclosure). Stage A uses
OpenCV's bundled Haar cascade (haarcascade_russian_plate_number.xml) for the plate-
region bounding box — the same "no downloaded model weights" precedent already used for
face detection — then reads the plate text with a real Tesseract OCR pass (pytesseract).
This cascade is Russian-plate-trained; real accuracy against other plate formats
(including South African plates) is unverified and may be poor. Ship it, measure real
accuracy against real footage (the same discipline that tuned the gate-jump threshold
from real logged data), and only then decide whether a downloaded general-purpose
plate-detection model is worth the investment — not pre-committed to here.

A plain regex sanity check rejects obvious OCR garbage (a single stray character, a run
of punctuation) before a read is ever treated as real — this is a coarse plausibility
check, not a country-specific plate format validator, since formats vary too much to
hard-code here.
"""

import logging
import re
import time

import cv2
import pytesseract

from app.backend_client import backend_client
from app.detectors.base import Detection

logger = logging.getLogger("ai-engine.plate_reader")

_PLATE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_russian_plate_number.xml")

# Alphanumeric, 4-10 characters after stripping whitespace/punctuation OCR commonly
# hallucinates at crop edges — deliberately coarse, not a real plate-format validator.
_PLATE_TEXT_RE = re.compile(r"^[A-Z0-9]{4,10}$")

PLATE_RECOGNITION_COOLDOWN_SECONDS = 30


def clean_plate_text(raw: str) -> str | None:
    cleaned = re.sub(r"[^A-Z0-9]", "", raw.upper())
    return cleaned if _PLATE_TEXT_RE.match(cleaned) else None


def find_plate_region(vehicle_crop_bgr) -> tuple[int, int, int, int] | None:
    """Returns the largest candidate plate bounding box (x, y, w, h) within a vehicle
    crop, or None if the cascade found nothing. Real, unmocked OpenCV inference — not a
    trained plate-detection model, see this module's own docstring for the honest
    Russian-cascade accuracy caveat."""
    if vehicle_crop_bgr.size == 0:
        return None
    gray = cv2.cvtColor(vehicle_crop_bgr, cv2.COLOR_BGR2GRAY) if vehicle_crop_bgr.ndim == 3 else vehicle_crop_bgr
    candidates = _PLATE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 12))
    if len(candidates) == 0:
        return None
    x, y, w, h = max(candidates, key=lambda c: c[2] * c[3])
    return int(x), int(y), int(w), int(h)


class PlateReader:
    def __init__(self, camera_id: str) -> None:
        self.camera_id = camera_id
        self._last_attempt: dict[int, float] = {}

    def maybe_read_plate(
        self, camera: dict, frame, track_id: int, detection: Detection, recording_id: str | None = None
    ) -> None:
        try:
            self._maybe_read_plate(camera, frame, track_id, detection, recording_id)
        except Exception:
            # Never let an ANPR bug take down the worker's capture loop — same
            # exception-safety convention as FaceRecognizer.maybe_recognize.
            logger.exception("Camera %s: license plate read failed for track %s", self.camera_id, track_id)

    def _maybe_read_plate(self, camera: dict, frame, track_id: int, detection: Detection, recording_id: str | None) -> None:
        cooldown = camera.get("plate_recognition_cooldown_seconds", PLATE_RECOGNITION_COOLDOWN_SECONDS)
        now = time.time()
        if now - self._last_attempt.get(track_id, 0.0) < cooldown:
            return

        h, w = frame.shape[:2]
        x1 = max(0, int(detection.x * w))
        y1 = max(0, int(detection.y * h))
        x2 = min(w, int((detection.x + detection.width) * w))
        y2 = min(h, int((detection.y + detection.height) * h))
        if x2 <= x1 or y2 <= y1:
            return
        vehicle_crop = frame[y1:y2, x1:x2]

        self._last_attempt[track_id] = now

        plate_region = find_plate_region(vehicle_crop)
        if plate_region is None:
            logger.info("Camera %s: track %s no plate region found in %s crop", self.camera_id, track_id, detection.object_type)
            return

        px, py, pw, ph = plate_region
        gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY) if vehicle_crop.ndim == 3 else vehicle_crop
        plate_crop = gray[py : py + ph, px : px + pw]

        raw_text = pytesseract.image_to_string(plate_crop, config="--psm 7")
        plate_text = clean_plate_text(raw_text)
        if plate_text is None:
            logger.info(
                "Camera %s: track %s OCR read rejected as implausible (raw=%r)",
                self.camera_id, track_id, raw_text.strip(),
            )
            return

        from datetime import datetime, timezone

        backend_client.recognize_plate(
            {
                "camera_id": self.camera_id,
                "tracking_id": track_id,
                "plate_text": plate_text,
                "vehicle_type": detection.object_type,
                "confidence": detection.confidence,
                "recording_id": recording_id,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
        )
