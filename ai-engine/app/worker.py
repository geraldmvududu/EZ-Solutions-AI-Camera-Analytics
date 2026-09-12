"""Per-camera processing loop — this is where sections 8-28 of the spec actually
happen for real: capture -> motion detection -> AI detection -> tracking -> zone/
tripwire/loitering evaluation -> snapshot/recording -> reporting to the backend, which
in turn runs the rule engine and broadcasts over WebSocket. Nothing in this file
fabricates a detection, event, snapshot, or recording — every one of those is produced
from an actual decoded video frame.
"""

import logging
import threading
import time
from datetime import datetime, timezone

import cv2

from app import streaming
from app.backend_client import backend_client
from app.config import get_settings
from app.core.motion import MotionDetector
from app.core.overlay import draw_overlay
from app.core.privacy import apply_privacy_masks
from app.core.face_recognizer import FaceRecognizer
from app.core.recorder import SegmentRecorder
from app.core.snapshotter import save_snapshot
from app.core.tracker import CentroidTracker
from app.core.zones import LoiteringTracker, crossed_line, point_in_polygon
from app.detectors import build_detector
from app.detectors.base import Detection
from app.sources import build_source

logger = logging.getLogger("ai-engine.worker")
settings = get_settings()

VEHICLE_TYPES = {"CAR", "TRUCK", "BUS", "MOTORCYCLE", "BICYCLE"}

# How long a MOTION/AI_EVENT recording keeps rolling after the last trigger before it
# closes (there is no pre-roll buffer yet — see core/recorder.py).
POST_TRIGGER_RECORD_SECONDS = 10
CONTINUOUS_SEGMENT_SECONDS = 300


class CameraWorker:
    def __init__(self, camera: dict, zones: list[dict], tripwires: list[dict]) -> None:
        self.camera = camera
        self.camera_id = camera["id"]
        self.zones = [z for z in zones if z["camera_id"] == self.camera_id]
        self.tripwires = [t for t in tripwires if t["camera_id"] == self.camera_id]
        self._privacy_zones = [z for z in self.zones if z["zone_type"] == "PRIVACY"]
        self._face_zones = [z for z in self.zones if z["zone_type"] in ("FACE_DETECTION", "FACE_EXCLUSION")]
        self._face_recognizer = FaceRecognizer(self.camera_id) if camera.get("face_recognition_enabled") else None

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"camera-{camera['camera_code']}")

        self._motion = MotionDetector(camera.get("motion_sensitivity", "MEDIUM")) if camera["motion_detection_enabled"] else None
        self._detector = build_detector() if camera["ai_enabled"] else None
        self._tracker = CentroidTracker()
        self._loitering = LoiteringTracker()
        self._recorder = SegmentRecorder(self.camera_id)
        self._reported_track_ids: set[int] = set()
        self._last_tracked: dict[int, Detection] = {}

        self._last_heartbeat = 0.0
        self._last_motion_time = 0.0
        self._last_detection_time = 0.0
        self._segment_started_at = 0.0
        self._frame_index = 0
        self._last_publish_time = 0.0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5)

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def _run(self) -> None:
        try:
            source = build_source(self.camera)
        except Exception as exc:
            logger.error("Camera %s: failed to open source — %s", self.camera["name"], exc)
            return

        capture_fps = self.camera.get("capture_fps") or 15
        ai_fps = max(1, self.camera.get("ai_fps") or 5)
        ai_frame_interval = max(1, capture_fps // ai_fps)

        logger.info("Camera %s: worker started (%s)", self.camera["name"], self.camera["source_type"])

        try:
            while not self._stop_event.is_set():
                frame = source.read()
                if frame is None:
                    logger.warning("Camera %s: source returned no frame, stopping worker", self.camera["name"])
                    break

                if self._privacy_zones:
                    frame = apply_privacy_masks(frame, self._privacy_zones)

                self._frame_index += 1
                self._maybe_heartbeat()

                motion_detected = self._motion.detect(frame) if self._motion else False
                if motion_detected:
                    self._last_motion_time = time.time()
                    self._on_motion_detected()

                if self._detector and self._frame_index % ai_frame_interval == 0:
                    detections = self._detector.detect(frame)
                    tracked = self._tracker.update(detections)
                    if tracked:
                        self._last_detection_time = time.time()
                    self._last_tracked = tracked
                    self._process_tracked_detections(frame, tracked)
                elif self._detector:
                    # Keep track ages current even on skipped frames.
                    self._last_tracked = self._tracker.update([])

                self._handle_recording(frame, capture_fps, motion_detected)
                self._publish_live_frame(frame)
                time.sleep(max(0.0, 1 / capture_fps))
        finally:
            self._recorder.stop()
            source.release()
            streaming.clear_frame(self.camera_id)
            logger.info("Camera %s: worker stopped", self.camera["name"])

    def _publish_live_frame(self, frame) -> None:
        now = time.time()
        if now - self._last_publish_time < 1 / settings.stream_fps:
            return
        self._last_publish_time = now

        annotated = draw_overlay(frame, self.camera["name"], self._last_tracked, self._recorder.is_recording)
        ok, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, settings.stream_jpeg_quality])
        if ok:
            streaming.publish_frame(self.camera_id, buffer.tobytes())

    def _maybe_heartbeat(self) -> None:
        now = time.time()
        if now - self._last_heartbeat >= settings.camera_heartbeat_interval_seconds:
            backend_client.heartbeat(self.camera_id)
            self._last_heartbeat = now

    def _on_motion_detected(self) -> None:
        # Throttle so a continuously-moving scene doesn't spam an event every frame.
        if time.time() - getattr(self, "_last_motion_event_sent", 0) < 30:
            return
        self._last_motion_event_sent = time.time()
        backend_client.create_event(
            {
                "camera_id": self.camera_id,
                "event_type": "MOTION_DETECTED",
                "severity": "INFO",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "event_metadata": {},
            }
        )

    def _process_tracked_detections(self, frame, tracked: dict[int, Detection]) -> None:
        for track_id, detection in tracked.items():
            record = backend_client.create_detection(
                {
                    "camera_id": self.camera_id,
                    "object_type": detection.object_type,
                    "confidence": detection.confidence,
                    "bbox_x": detection.x,
                    "bbox_y": detection.y,
                    "bbox_width": detection.width,
                    "bbox_height": detection.height,
                    "tracking_id": track_id,
                    "frame_number": self._frame_index,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            detection_id = record.get("id") if record else None

            is_new_track = track_id not in self._reported_track_ids
            if is_new_track:
                self._reported_track_ids.add(track_id)
                self._emit_object_event(frame, detection, detection_id)

            centroid = ((detection.x + detection.width / 2), (detection.y + detection.height / 2))
            self._check_tripwires(track_id, centroid, frame, detection_id)
            self._check_zones(track_id, centroid, frame, detection_id)

            if self._face_recognizer and detection.object_type == "PERSON":
                self._face_recognizer.maybe_recognize(
                    self.camera, frame, track_id, detection, centroid, self._face_zones, self._recorder.recording_id
                )

    def _emit_object_event(self, frame, detection, detection_id) -> None:
        event_type = "PERSON_DETECTED" if detection.object_type == "PERSON" else (
            "VEHICLE_DETECTED" if detection.object_type in VEHICLE_TYPES else "AI_DETECTION"
        )
        snapshot_id = self._save_and_report_snapshot(frame, detection)
        backend_client.create_event(
            {
                "camera_id": self.camera_id,
                "event_type": event_type,
                "severity": "INFO",
                "detection_id": detection_id,
                "snapshot_id": snapshot_id,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "event_metadata": {"object_type": detection.object_type, "confidence": detection.confidence},
            }
        )

    def _identity_metadata(self, track_id: int) -> dict:
        """Attaches a known person's identity (if this track was recently recognized —
        see FaceRecognizer.identity_for) to a tripwire/zone violation event, so a
        "Person + Behaviour" combined event (spec section 9) is possible: the
        recognized identity and the boundary violation are correlated by track_id, not
        claimed to be the same signal. Empty when face recognition isn't enabled for
        this camera or this track was never recognized — a violation by an unenrolled/
        unrecognized person is still reported, just without a person_id attached."""
        if not self._face_recognizer:
            return {}
        identity = self._face_recognizer.identity_for(track_id)
        if not identity:
            return {}
        return {
            "person_id": identity["person_id"],
            "person_name": identity.get("person_name"),
            "person_recognition_confidence": identity.get("confidence_score"),
        }

    def _check_tripwires(self, track_id: int, centroid, frame, detection_id) -> None:
        history = self._tracker.history_for(track_id)
        if len(history) < 2:
            return
        prev_point = history[-2]

        for tripwire in self.tripwires:
            if not tripwire.get("is_enabled", True) or len(tripwire.get("line", [])) != 2:
                continue
            direction = crossed_line(prev_point, centroid, tripwire["line"])
            if direction is None:
                continue
            configured_direction = tripwire.get("direction", "BOTH")
            if configured_direction != "BOTH" and configured_direction != direction:
                continue

            snapshot_id = self._save_and_report_snapshot(frame, None)
            backend_client.create_event(
                {
                    "camera_id": self.camera_id,
                    "event_type": "TRIPWIRE_VIOLATION",
                    "severity": "HIGH",
                    "detection_id": detection_id,
                    "tripwire_id": tripwire["id"],
                    "snapshot_id": snapshot_id,
                    "recording_id": self._recorder.recording_id,
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "event_metadata": {"direction": direction, "tracking_id": track_id, **self._identity_metadata(track_id)},
                }
            )

    def _check_zones(self, track_id: int, centroid, frame, detection_id) -> None:
        for zone in self.zones:
            if not zone.get("is_enabled", True):
                continue
            inside = point_in_polygon(centroid, zone.get("polygon", []))

            if zone["zone_type"] == "INTRUSION" and inside:
                snapshot_id = self._save_and_report_snapshot(frame, None)
                backend_client.create_event(
                    {
                        "camera_id": self.camera_id,
                        "event_type": "INTRUSION_DETECTED",
                        "severity": "CRITICAL",
                        "detection_id": detection_id,
                        "zone_id": zone["id"],
                        "snapshot_id": snapshot_id,
                        "recording_id": self._recorder.recording_id,
                        "occurred_at": datetime.now(timezone.utc).isoformat(),
                        "event_metadata": {"tracking_id": track_id, **self._identity_metadata(track_id)},
                    }
                )

            if zone["zone_type"] == "LOITERING":
                threshold = zone.get("loitering_threshold_seconds", settings.default_loitering_seconds)
                if self._loitering.observe(track_id, zone["id"], inside, threshold):
                    snapshot_id = self._save_and_report_snapshot(frame, None)
                    backend_client.create_event(
                        {
                            "camera_id": self.camera_id,
                            "event_type": "LOITERING_DETECTED",
                            "severity": "MEDIUM",
                            "detection_id": detection_id,
                            "zone_id": zone["id"],
                            "snapshot_id": snapshot_id,
                            "occurred_at": datetime.now(timezone.utc).isoformat(),
                            "event_metadata": {"tracking_id": track_id, "threshold_seconds": threshold},
                        }
                    )

    def _save_and_report_snapshot(self, frame, detection) -> str | None:
        file_path = save_snapshot(self.camera_id, frame)
        record = backend_client.create_snapshot(
            {
                "camera_id": self.camera_id,
                "file_path": file_path,
                "taken_at": datetime.now(timezone.utc).isoformat(),
                "object_type": detection.object_type if detection else "",
                "confidence": detection.confidence if detection else None,
            }
        )
        return record.get("id") if record else None

    def _handle_recording(self, frame, capture_fps: float, motion_detected: bool) -> None:
        mode = self.camera.get("recording_mode", "AI_EVENT")
        if not self.camera.get("recording_enabled") or mode == "DISABLED":
            return

        now = time.time()

        if mode == "CONTINUOUS":
            if not self._recorder.is_recording:
                self._recorder.start(frame, capture_fps, "CONTINUOUS")
                self._segment_started_at = now
            elif now - self._segment_started_at >= CONTINUOUS_SEGMENT_SECONDS:
                self._recorder.stop()
                self._recorder.start(frame, capture_fps, "CONTINUOUS")
                self._segment_started_at = now
            self._recorder.write(frame)
            return

        trigger_active = (mode == "MOTION" and motion_detected) or (mode == "AI_EVENT" and now - self._last_detection_time < 1)

        if trigger_active and not self._recorder.is_recording:
            self._recorder.start(frame, capture_fps, mode)
        if self._recorder.is_recording:
            self._recorder.write(frame)
            last_trigger = self._last_motion_time if mode == "MOTION" else self._last_detection_time
            if now - last_trigger > POST_TRIGGER_RECORD_SECONDS:
                self._recorder.stop()
