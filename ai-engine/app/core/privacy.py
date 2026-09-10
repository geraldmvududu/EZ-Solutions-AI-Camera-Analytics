"""Real privacy-zone masking (section 48). Applied to the raw frame immediately after
capture — before motion detection, AI inference, recording, or the live stream ever see
it — so a PRIVACY zone genuinely hides that region from every downstream consumer, not
just a cosmetic overlay drawn on top of an otherwise-analyzed frame.
"""

import cv2
import numpy as np


def apply_privacy_masks(frame: np.ndarray, privacy_zones: list[dict]) -> np.ndarray:
    if not privacy_zones:
        return frame

    height, width = frame.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)

    for zone in privacy_zones:
        polygon = zone.get("polygon") or []
        if len(polygon) < 3:
            continue
        points = np.array([[int(x * width), int(y * height)] for x, y in polygon], dtype=np.int32)
        cv2.fillPoly(mask, [points], 255)

    if not mask.any():
        return frame

    # A strong blur — large enough that the underlying content is genuinely
    # unrecoverable, not just softened.
    blurred = cv2.GaussianBlur(frame, (0, 0), sigmaX=25, sigmaY=25)
    mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    return np.where(mask_3ch == 255, blurred, frame)
