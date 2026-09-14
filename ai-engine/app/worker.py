"""Per-camera processing loop — this is where sections 8-28 of the spec actually
happen for real: capture -> motion detection -> AI detection -> tracking -> zone/
tripwire/loitering evaluation -> snapshot/recording -> reporting to the backend, which
in turn runs the rule engine and broadcasts over WebSocket. Nothing in this file
fabricates a detection, event, snapshot, or recording — every one of those is produced
from an actual decoded video frame.
"""

import logging
import math
import threading
import time
from datetime import datetime, timezone

import cv2

from app import streaming
from app.backend_client import backend_client
from app.config import get_settings
from app.core.motion import MotionDetector
from app.core.object_tracking import AssetZoneTracker
from app.core.overlay import draw_overlay
from app.core.privacy import apply_privacy_masks
from app.core.face_recognizer import FaceRecognizer
from app.core.frame_similarity import average_hash, frames_are_duplicates
from app.core.recorder import SegmentRecorder
from app.core.snapshotter import save_snapshot
from app.core.tracker import CentroidTracker
from app.core.tripwire_analysis import (
    GATE_JUMP_MIN_VERTICAL_STEP,
    GATE_JUMP_VELOCITY_RATIO,
    TailgatingTracker,
    gate_jump_confidence,
    gate_jump_trajectory_stats,
)
from app.core.zones import LoiteringTracker, crossed_line, point_in_polygon
from app.detectors import build_detector
from app.detectors.base import Detection
from app.sources import build_source

logger = logging.getLogger("ai-engine.worker")
settings = get_settings()

VEHICLE_TYPES = {"CAR", "TRUCK", "BUS", "MOTORCYCLE", "BICYCLE"}
# AI Video Intelligence Phase 2 (section 6) — the only COCO classes YOLOv8n gives us
# that represent an "ownable item" someone could remove from a monitored area. See
# yolo_detector.py's module docstring for the honest scope limit (no generic
# box/package class).
MONITORED_ASSET_TYPES = {"BACKPACK", "BAG", "SUITCASE"}
# Reuses the same normalized-distance scale CentroidTracker's default max_distance
# already treats as "the same object across frames" — good enough as a rough
# proximity radius for "was a person standing near this item when it left."
NEARBY_PERSON_MAX_DISTANCE = 0.15

# How long a MOTION/AI_EVENT recording keeps rolling after the last trigger before it
# closes (there is no pre-roll buffer yet — see core/recorder.py). Real bug found live
# on the deployed VM: one camera produced 57 separate recording segments in under 6
# hours, most only tens of seconds long — a SIMULATED source's motion pattern (or any
# camera whose detector briefly loses the object) creates a gap in tracked detections
# just over the old 10s threshold, closing the current recording and opening a new one
# for what is really the same ongoing scene. Widened to 30s so a brief gap merges into
# one continuous recording instead of fragmenting into several near-identical ones.
POST_TRIGGER_RECORD_SECONDS = 30
CONTINUOUS_SEGMENT_SECONDS = 300

# Real bug found live on the same VM: CentroidTracker briefly losing and re-acquiring
# the same physical object hands out a new track_id, and _emit_object_event fires a
# brand-new PERSON_DETECTED/VEHICLE_DETECTED/AI_DETECTION event — with its own
# snapshot — every single time, even though it's really the same ongoing presence. The
# same camera produced ~30k snapshots in under a day this way. This is the same
# throttle _on_motion_detected already applies to MOTION_DETECTED, extended to
# object-detection events for the same reason: a time-based cooldown, not a real "is
# this the same image" comparison (this codebase has no frame-similarity check) — see
# CLAUDE.md's "do not hallucinate accuracy we don't have" convention.
OBJECT_EVENT_COOLDOWN_SECONDS = 30

# Real bug found live on the deployed VM: one camera produced 535 TRIPWIRE_VIOLATION
# events in ~2 hours, all attached to the SAME recording_id (i.e. reported as 535
# separate "videos" for what was really one continuous scene) — a tracked object
# jittering right at the tripwire line crosses it, CentroidTracker loses and
# re-acquires it under a brand-new track_id every ~10-25s (the same track-churn root
# cause OBJECT_EVENT_COOLDOWN_SECONDS already fixes for plain detections), and
# _check_tripwires had NO debounce at all — unlike LoiteringTracker's "once per
# continuous stay" gate, every crossing by every fresh track_id fired its own event.
# One cooldown per tripwire (not per track_id, since the whole point is that track_id
# keeps changing for what's really the same presence) — same accepted trade-off as
# OBJECT_EVENT_COOLDOWN_SECONDS: two genuinely different people crossing the same
# tripwire within the window means only the first is reported.
TRIPWIRE_VIOLATION_COOLDOWN_SECONDS = 30


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
        self._detector = build_detector(camera) if camera["ai_enabled"] else None
        self._tracker = CentroidTracker()
        self._loitering = LoiteringTracker()
        self._tailgating = TailgatingTracker()
        self._asset_zone = AssetZoneTracker()
        self._recorder = SegmentRecorder(
            self.camera_id,
            tenant_id=camera.get("tenant_id", ""),
            site_id=camera.get("site_id"),
            cloud_recording_enabled=camera.get("cloud_recording_enabled", False),
        )
        self._reported_track_ids: set[int] = set()
        self._last_tracked: dict[int, Detection] = {}

        self._last_heartbeat = 0.0
        self._last_object_event_sent = 0.0
        self._last_tripwire_violation_sent: dict[str, float] = {}
        self._last_snapshot_hash: int | None = None
        self._last_snapshot_id: str | None = None
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
                    # Real user request: a finite video file that isn't looping has
                    # genuinely reached its end, not failed — mark it processed so
                    # main.py's discovery loop stops retrying it forever (the previous
                    # behavior kept re-opening and re-analyzing the same footage every
                    # ~60s, producing "new" events for content that was never new).
                    # Scoped tightly to VIDEO_FILE + loop_video=False specifically —
                    # a live RTSP/webcam source returning no frame is a transient
                    # glitch, never "done."
                    if self.camera["source_type"] == "VIDEO_FILE" and not self.camera.get("loop_video", True):
                        backend_client.mark_video_processed(self.camera_id)
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
            self._check_zones(track_id, centroid, frame, detection_id, detection, tracked)

            if self._face_recognizer and detection.object_type == "PERSON":
                self._face_recognizer.maybe_recognize(
                    self.camera, frame, track_id, detection, centroid, self._face_zones, self._recorder.recording_id
                )

    def _emit_object_event(self, frame, detection, detection_id) -> None:
        # See OBJECT_EVENT_COOLDOWN_SECONDS's docstring: a "new" track_id doesn't
        # always mean a genuinely new appearance — this throttle prevents a tracker
        # briefly losing/reacquiring the same object from spamming a fresh
        # event+snapshot+recording-trigger every time it does.
        if time.time() - self._last_object_event_sent < OBJECT_EVENT_COOLDOWN_SECONDS:
            return
        self._last_object_event_sent = time.time()

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

            now = time.time()
            last_sent = self._last_tripwire_violation_sent.get(tripwire["id"], 0.0)
            if now - last_sent < TRIPWIRE_VIOLATION_COOLDOWN_SECONDS:
                continue
            self._last_tripwire_violation_sent[tripwire["id"]] = now

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

            # AI Video Intelligence Phase 1 (section 4): opt-in per tripwire (a line
            # actually drawn across a gate/fence, not a general counting line) AND the
            # tenant-wide kill switch — see tripwire_analysis.py for exactly what this
            # heuristic does and doesn't verify.
            if tripwire.get("gate_jump_detection_enabled") and self.camera.get("gate_jumping_enabled", True):
                track_history = self._tracker.history_for(track_id)
                confidence = gate_jump_confidence(track_history)
                if confidence is None:
                    # Real, honest instrumentation for an admittedly-approximate
                    # heuristic (see tripwire_analysis.py's module docstring): tuned
                    # only against synthetic trajectories, so seeing what a real
                    # crossing actually measures as — rather than only ever a silent
                    # None — is how GATE_JUMP_MIN_VERTICAL_STEP/GATE_JUMP_VELOCITY_RATIO
                    # get tuned against real footage instead of guessed at blindly.
                    stats = gate_jump_trajectory_stats(track_history)
                    if stats is not None:
                        peak_vertical, avg_horizontal, window_len = stats
                        logger.info(
                            "Camera %s: tripwire '%s' crossing by track %s NOT classified as a gate jump "
                            "(peak_vertical=%.3f avg_horizontal=%.3f window=%d samples — "
                            "needs peak_vertical>=%.2f AND peak_vertical>=%.1fx avg_horizontal)",
                            self.camera_id, tripwire["name"], track_id, peak_vertical, avg_horizontal, window_len,
                            GATE_JUMP_MIN_VERTICAL_STEP, GATE_JUMP_VELOCITY_RATIO,
                        )
                if confidence is not None:
                    backend_client.create_event(
                        {
                            "camera_id": self.camera_id,
                            "event_type": "GATE_JUMPING_DETECTED",
                            "severity": "HIGH",
                            "detection_id": detection_id,
                            "tripwire_id": tripwire["id"],
                            "snapshot_id": snapshot_id,
                            "recording_id": self._recorder.recording_id,
                            "occurred_at": datetime.now(timezone.utc).isoformat(),
                            "event_metadata": {
                                "direction": direction, "tracking_id": track_id, "confidence": confidence,
                                **self._identity_metadata(track_id),
                            },
                        }
                    )

            if tripwire.get("tailgating_detection_enabled") and self.camera.get("tailgating_enabled", True):
                window = tripwire.get("tailgating_window_seconds", 5)
                tailgated_track_id = self._tailgating.observe(tripwire["id"], track_id, time.time(), window)
                if tailgated_track_id is not None:
                    backend_client.create_event(
                        {
                            "camera_id": self.camera_id,
                            "event_type": "TAILGATING_DETECTED",
                            "severity": "MEDIUM",
                            "detection_id": detection_id,
                            "tripwire_id": tripwire["id"],
                            "snapshot_id": snapshot_id,
                            "recording_id": self._recorder.recording_id,
                            "occurred_at": datetime.now(timezone.utc).isoformat(),
                            "event_metadata": {
                                "tracking_id": track_id, "leading_tracking_id": tailgated_track_id,
                                "window_seconds": window, **self._identity_metadata(track_id),
                            },
                        }
                    )

    def _closest_person_track_id(self, centroid, tracked: dict[int, Detection]) -> int | None:
        best_id, best_dist = None, NEARBY_PERSON_MAX_DISTANCE
        for other_id, other_detection in tracked.items():
            if other_detection.object_type != "PERSON":
                continue
            other_centroid = (other_detection.x + other_detection.width / 2, other_detection.y + other_detection.height / 2)
            dist = math.hypot(centroid[0] - other_centroid[0], centroid[1] - other_centroid[1])
            if dist < best_dist:
                best_id, best_dist = other_id, dist
        return best_id

    def _check_zones(self, track_id: int, centroid, frame, detection_id, detection: Detection, tracked: dict[int, Detection]) -> None:
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

            # AI Video Intelligence Phase 1 (section 5): same configurable-dwell
            # mechanism as LOITERING above (LoiteringTracker is zone-type-agnostic,
            # keyed by track_id+zone_id) — reported as its own category rather than a
            # generic LOITERING_DETECTED so it's dashboarded/reported separately.
            if zone["zone_type"] == "RESTRICTED_AREA" and self.camera.get("restricted_area_enabled", True):
                threshold = zone.get("loitering_threshold_seconds", settings.default_loitering_seconds)
                if self._loitering.observe(track_id, zone["id"], inside, threshold):
                    snapshot_id = self._save_and_report_snapshot(frame, None)
                    backend_client.create_event(
                        {
                            "camera_id": self.camera_id,
                            "event_type": "RESTRICTED_AREA_VIOLATION",
                            "severity": "HIGH",
                            "detection_id": detection_id,
                            "zone_id": zone["id"],
                            "snapshot_id": snapshot_id,
                            "recording_id": self._recorder.recording_id,
                            "occurred_at": datetime.now(timezone.utc).isoformat(),
                            "event_metadata": {"tracking_id": track_id, "threshold_seconds": threshold, **self._identity_metadata(track_id)},
                        }
                    )

            # AI Video Intelligence Phase 2 (section 6): only fires for a camera with
            # a real multi-class detector enabled (multi_class_detection_enabled) —
            # HOG never emits BACKPACK/BAG/SUITCASE detections, so this branch simply
            # never matches on a HOG-only camera. See object_tracking.py::
            # AssetZoneTracker for exactly what this dwell-then-exit heuristic does
            # and does not verify.
            if (
                zone["zone_type"] == "ASSET_ZONE"
                and detection.object_type in MONITORED_ASSET_TYPES
                and self.camera.get("theft_detection_enabled", True)
            ):
                threshold = zone.get("loitering_threshold_seconds", settings.default_loitering_seconds)
                if self._asset_zone.observe(track_id, zone["id"], inside, threshold, time.time()):
                    nearby_track_id = self._closest_person_track_id(centroid, tracked)
                    snapshot_id = self._save_and_report_snapshot(frame, detection)
                    backend_client.create_event(
                        {
                            "camera_id": self.camera_id,
                            "event_type": "POTENTIAL_THEFT_DETECTED",
                            "severity": "HIGH",
                            "detection_id": detection_id,
                            "zone_id": zone["id"],
                            "snapshot_id": snapshot_id,
                            "recording_id": self._recorder.recording_id,
                            "occurred_at": datetime.now(timezone.utc).isoformat(),
                            "event_metadata": {
                                "object_type": detection.object_type,
                                "tracking_id": track_id,
                                "threshold_seconds": threshold,
                                **self._identity_metadata(nearby_track_id if nearby_track_id is not None else track_id),
                            },
                        }
                    )

    def _save_and_report_snapshot(self, frame, detection) -> str | None:
        # Real, content-based duplicate detection (requested directly by the user,
        # testing against a looping demo video): OBJECT_EVENT_COOLDOWN_SECONDS/
        # TRIPWIRE_VIOLATION_COOLDOWN_SECONDS above only throttle by elapsed time, so
        # once a video loop's period exceeds the cooldown window, a "new" event fires
        # for a frame that's visually identical to one already saved. This compares
        # the actual pixels (a real perceptual hash, not a timer) against the last
        # snapshot taken for this camera, and — when it's the same picture — reuses
        # that existing snapshot instead of writing/uploading yet another
        # near-identical JPEG. The event itself is still created and logged; only the
        # redundant image file is skipped, since the event history (who/when/what)
        # stays meaningful even when the picture doesn't change.
        current_hash = average_hash(frame)
        if self._last_snapshot_hash is not None and frames_are_duplicates(current_hash, self._last_snapshot_hash):
            return self._last_snapshot_id

        saved = save_snapshot(self.camera, frame)
        record = backend_client.create_snapshot(
            {
                "camera_id": self.camera_id,
                "file_path": saved.file_path,
                "storage_key": saved.storage_key,
                "file_size_bytes": saved.file_size_bytes,
                "taken_at": datetime.now(timezone.utc).isoformat(),
                "object_type": detection.object_type if detection else "",
                "confidence": detection.confidence if detection else None,
            }
        )
        snapshot_id = record.get("id") if record else None
        self._last_snapshot_hash = current_hash
        self._last_snapshot_id = snapshot_id
        return snapshot_id

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
