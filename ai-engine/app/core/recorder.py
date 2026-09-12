"""Real video recording to disk via cv2.VideoWriter (section 26). A Recording row is
created the moment a segment STARTS, not when it closes — specifically so a real
recording_id exists (self.recording_id) to attach to a face-recognition/violation
event that happens WHILE the segment is still being written (Facial Recognition Phase
2's "linked to camera recordings" requirement). When the segment closes, the same row
is finalized (ended_at/duration/file_size) via a separate PATCH call rather than
creating a second row.

Known limitation (documented rather than faked, per section 67): event-triggered
recording starts writing from the moment the trigger fires — there is no pre-roll
frame buffer yet, so it does not capture the few seconds *before* the triggering
event. Continuous recording is unaffected. A ring-buffer pre-roll is a reasonable
Phase 9 addition.

IMPORTANT (found while building Facial Recognition Phase 2's "View in recording"
player): cv2.VideoWriter's mp4v fourcc (MPEG-4 Part 2) is the only codec this
environment's OpenCV/FFmpeg build can actually open for writing — H.264 (avc1/H264/
X264 fourccs) failed to open here because the OpenH264 shared library OpenCV's FFmpeg
tries to load for it isn't present. mp4v output is real, valid video (cv2 itself and
tools like VLC/ffplay read it fine), but Chrome's <video> tag flatly refuses it
(MEDIA_ERR_SRC_NOT_SUPPORTED) — confirmed directly against a real recorded file in a
real browser. stop() now re-encodes the segment to H.264 via the system `ffmpeg`
binary (installed via apt in ai-engine/Dockerfile, a full Ubuntu ffmpeg build — not
the same as OpenCV's bundled/limited one) immediately after closing it, replacing the
file in place so the existing DB row's file_path is unaffected. If ffmpeg is missing
or the transcode fails for any reason, the original mp4v file is kept rather than
losing the recording — it just won't play in a browser (still downloadable/usable in
VLC/ffplay as real evidence). This transcode step could not be verified end-to-end on
this Windows dev machine (no local ffmpeg binary, and the OpenH264 failure above is
itself Windows/build-specific) — verify for real once deployed by recording a clip and
confirming it plays from the Recordings page.
"""

import logging
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np

from app.backend_client import backend_client
from app.config import get_settings

logger = logging.getLogger("ai-engine.recorder")

settings = get_settings()


class SegmentRecorder:
    def __init__(self, camera_id: str, tenant_dir: str | None = None) -> None:
        self._camera_id = camera_id
        self._writer: cv2.VideoWriter | None = None
        self._file_path: str | None = None
        self._started_at: datetime | None = None
        self._frame_count = 0
        self._fps = 15.0
        self._trigger_type = "MOTION"
        self.recording_id: str | None = None

    @property
    def is_recording(self) -> bool:
        return self._writer is not None

    def start(self, frame: np.ndarray, fps: float, trigger_type: str) -> None:
        camera_dir = os.path.join(settings.recording_path, self._camera_id)
        os.makedirs(camera_dir, exist_ok=True)

        filename = f"{int(time.time())}_{uuid.uuid4().hex[:8]}.mp4"
        self._file_path = os.path.join(camera_dir, filename)
        self._fps = fps or 15.0
        self._trigger_type = trigger_type

        height, width = frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(self._file_path, fourcc, self._fps, (width, height))
        self._started_at = datetime.now(timezone.utc)
        self._frame_count = 0

        try:
            record = backend_client.create_recording(
                {
                    "camera_id": self._camera_id,
                    "file_path": self._file_path,
                    "started_at": self._started_at.isoformat(),
                    "trigger_type": self._trigger_type,
                }
            )
            self.recording_id = record.get("id") if record else None
        except Exception:
            logger.exception("Camera %s: failed to create recording row at segment start", self._camera_id)
            self.recording_id = None

    def write(self, frame: np.ndarray) -> None:
        if self._writer is not None:
            self._writer.write(frame)
            self._frame_count += 1

    def _transcode_to_h264(self, path: str) -> None:
        """Best-effort re-encode to a browser-playable codec — see this module's
        docstring. Never raises; a failed/skipped transcode just leaves the original
        (still real, still valid) mp4v file in place."""
        transcoded_path = path + ".h264.mp4"
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", path,
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", transcoded_path,
                ],
                capture_output=True, timeout=120,
            )
            if result.returncode == 0 and os.path.exists(transcoded_path):
                os.replace(transcoded_path, path)
            else:
                stderr_tail = result.stderr.decode(errors="replace")[-500:] if result.stderr else ""
                logger.warning("Camera %s: ffmpeg transcode failed (rc=%s): %s", self._camera_id, result.returncode, stderr_tail)
                if os.path.exists(transcoded_path):
                    os.remove(transcoded_path)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            logger.warning(
                "Camera %s: ffmpeg transcode skipped (%s) — recording saved in its original (non-browser-playable) format",
                self._camera_id, exc,
            )
            if os.path.exists(transcoded_path):
                os.remove(transcoded_path)

    def stop(self) -> None:
        if self._writer is None:
            return
        self._writer.release()

        if self._file_path and os.path.exists(self._file_path):
            self._transcode_to_h264(self._file_path)

        duration = self._frame_count / self._fps if self._fps else 0
        file_size = os.path.getsize(self._file_path) if self._file_path and os.path.exists(self._file_path) else 0

        if self.recording_id:
            backend_client.finalize_recording(
                self.recording_id,
                {
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "duration_seconds": duration,
                    "file_size_bytes": file_size,
                },
            )

        self._writer = None
        self._file_path = None
        self._started_at = None
        self._frame_count = 0
        self.recording_id = None
