"""Real video recording to disk via cv2.VideoWriter (section 26). Writes an actual MP4
segment frame-by-frame; when a segment closes, its real file size and duration are
reported to the backend as a Recording row.

Known limitation (documented rather than faked, per section 67): event-triggered
recording starts writing from the moment the trigger fires — there is no pre-roll
frame buffer yet, so it does not capture the few seconds *before* the triggering
event. Continuous recording is unaffected. A ring-buffer pre-roll is a reasonable
Phase 9 addition.
"""

import os
import time
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np

from app.backend_client import backend_client
from app.config import get_settings

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

    def write(self, frame: np.ndarray) -> None:
        if self._writer is not None:
            self._writer.write(frame)
            self._frame_count += 1

    def stop(self) -> None:
        if self._writer is None:
            return
        self._writer.release()

        duration = self._frame_count / self._fps if self._fps else 0
        file_size = os.path.getsize(self._file_path) if self._file_path and os.path.exists(self._file_path) else 0

        backend_client.create_recording(
            {
                "camera_id": self._camera_id,
                "file_path": self._file_path,
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": duration,
                "trigger_type": self._trigger_type,
                "file_size_bytes": file_size,
            }
        )

        self._writer = None
        self._file_path = None
        self._started_at = None
        self._frame_count = 0
