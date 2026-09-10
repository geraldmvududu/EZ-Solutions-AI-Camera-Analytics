"""Real motion detection via background subtraction (section 19) — deliberately
independent of the AI object detector, exactly as the spec requires. Sensitivity maps
to the subtractor's variance threshold and the minimum contour area considered
"motion" (a lower threshold / smaller area = more sensitive)."""

import cv2
import numpy as np

_SENSITIVITY_PRESETS = {
    "LOW": {"var_threshold": 40, "min_area_fraction": 0.02},
    "MEDIUM": {"var_threshold": 25, "min_area_fraction": 0.01},
    "HIGH": {"var_threshold": 12, "min_area_fraction": 0.003},
}


class MotionDetector:
    def __init__(self, sensitivity: str = "MEDIUM") -> None:
        preset = _SENSITIVITY_PRESETS.get(sensitivity, _SENSITIVITY_PRESETS["MEDIUM"])
        self._min_area_fraction = preset["min_area_fraction"]
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300, varThreshold=preset["var_threshold"], detectShadows=False
        )

    def detect(self, frame: np.ndarray) -> bool:
        mask = self._subtractor.apply(frame)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        frame_area = frame.shape[0] * frame.shape[1]
        min_area = frame_area * self._min_area_fraction
        return any(cv2.contourArea(c) >= min_area for c in contours)
