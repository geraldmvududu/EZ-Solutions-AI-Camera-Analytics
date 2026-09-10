"""Draws real annotations (bounding boxes, confidence, tracking ID, camera name/time,
REC indicator) onto a frame for the live view (section 16: "Draw bounding box, display
confidence, assign tracking ID"). Operates on a copy — never mutates the frame used for
recording/AI processing.
"""

import time

import cv2
import numpy as np

from app.detectors.base import Detection

_BOX_COLOR = (60, 200, 90)
_TEXT_COLOR = (240, 240, 240)


def draw_overlay(
    frame: np.ndarray,
    camera_name: str,
    tracked: dict[int, Detection],
    is_recording: bool,
) -> np.ndarray:
    annotated = frame.copy()
    height, width = annotated.shape[:2]

    for track_id, detection in tracked.items():
        x1 = int(detection.x * width)
        y1 = int(detection.y * height)
        x2 = int((detection.x + detection.width) * width)
        y2 = int((detection.y + detection.height) * height)

        cv2.rectangle(annotated, (x1, y1), (x2, y2), _BOX_COLOR, 2)
        label = f"#{track_id} {detection.object_type} {detection.confidence * 100:.0f}%"
        (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x1, max(0, y1 - label_h - 8)), (x1 + label_w + 6, y1), _BOX_COLOR, -1)
        cv2.putText(annotated, label, (x1 + 3, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (10, 20, 10), 1)

    header = f"{camera_name}  {time.strftime('%Y-%m-%d %H:%M:%S')}"
    cv2.putText(annotated, header, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, _TEXT_COLOR, 1)

    if is_recording:
        cv2.circle(annotated, (width - 20, 20), 6, (60, 60, 230), -1)
        cv2.putText(annotated, "REC", (width - 60, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 60, 230), 1)

    return annotated
