import logging

import cv2
import numpy as np

from app.sources.base import FrameSource

logger = logging.getLogger("ai-engine.sources.opencv")


class OpenCVCaptureSource(FrameSource):
    """Wraps cv2.VideoCapture — this covers VIDEO_FILE, WEBCAM, RTSP, HTTP_MJPEG and
    IP_CAMERA uniformly, since OpenCV/FFmpeg already know how to decode all of them
    from a single path/URL/device-index argument."""

    def __init__(self, source: str | int, loop: bool = False) -> None:
        self._source = source
        self._loop = loop
        self._cap = cv2.VideoCapture(source)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open video source: {source}")

    def read(self) -> np.ndarray | None:
        ok, frame = self._cap.read()
        if not ok:
            if self._loop and isinstance(self._source, str):
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self._cap.read()
                if ok:
                    return frame
            return None
        return frame

    def release(self) -> None:
        self._cap.release()

    @property
    def fps_hint(self) -> float:
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        return fps if fps and fps > 0 else 15.0
