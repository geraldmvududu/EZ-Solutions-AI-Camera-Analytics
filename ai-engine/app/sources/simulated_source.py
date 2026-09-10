import time

import cv2
import numpy as np

from app.sources.base import FrameSource


class SimulatedSource(FrameSource):
    """A synthetic test-pattern camera for when no real footage is assigned (section 9).
    It generates real, freshly-rendered frames every call — a moving shape plus a live
    timestamp overlay — so the full pipeline (motion detection, recording, snapshots,
    tripwire/zone geometry) can be exercised end-to-end without video hardware.

    Honesty note: this is NOT a substitute for real AI object detection testing. The
    HOG person detector (app/detectors/hog_detector.py) is trained on real pedestrian
    image gradients and will correctly find nothing in a synthetic shape — that is
    correct behavior, not a bug. Use a VIDEO_FILE camera with real footage of people to
    exercise person/vehicle detection (section 8's primary recommended testing method).
    """

    WIDTH, HEIGHT = 1280, 720

    def __init__(self) -> None:
        self._start = time.time()

    def read(self) -> np.ndarray:
        frame = np.full((self.HEIGHT, self.WIDTH, 3), (24, 24, 20), dtype=np.uint8)

        elapsed = time.time() - self._start
        x = int((np.sin(elapsed / 4) * 0.4 + 0.5) * (self.WIDTH - 120))
        cv2.rectangle(frame, (x, 300), (x + 120, 500), (60, 140, 60), -1)

        cv2.putText(
            frame,
            f"SIMULATED CAMERA  {time.strftime('%Y-%m-%d %H:%M:%S')}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (200, 200, 200),
            2,
        )
        time.sleep(1 / 15)
        return frame

    def release(self) -> None:
        pass

    @property
    def fps_hint(self) -> float:
        return 15.0
