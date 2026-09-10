import numpy as np

from app.core.motion import MotionDetector


def _blank_frame(color: int = 20) -> np.ndarray:
    return np.full((240, 320, 3), color, dtype=np.uint8)


def test_static_scene_reports_no_motion_once_background_learned():
    detector = MotionDetector("MEDIUM")
    frame = _blank_frame()
    # Feed enough identical frames for MOG2 to learn the background.
    for _ in range(15):
        detector.detect(frame)
    assert detector.detect(frame) is False


def test_large_moving_block_is_detected_as_motion():
    detector = MotionDetector("MEDIUM")
    background = _blank_frame()
    for _ in range(15):
        detector.detect(background)

    moving_frame = background.copy()
    moving_frame[50:150, 50:150] = 220  # a large bright block appears

    assert detector.detect(moving_frame) is True
