import cv2
import numpy as np

from app.detectors.base import Detection, Detector


class HOGPersonDetector(Detector):
    """Real person detection using OpenCV's built-in HOG + Linear SVM pedestrian
    detector (cv2.HOGDescriptor_getDefaultPeopleDetector). This ships inside
    opencv-python with no external model download, so the platform can do genuine
    AI inference offline immediately after `pip install` (section 78's "no cloud
    account, no GPU" requirement).

    This is intentionally the *default*, not the ceiling: it only detects PERSON, at
    lower accuracy than a modern CNN. app/detectors/base.py's Detector interface is
    what makes it swappable — a YOLOv8/ONNX detector (multi-class: person, car, truck,
    bus, motorcycle, bicycle...) can replace this without touching the worker loop.
    See CLAUDE.md "Known limitations" for the upgrade path.
    """

    def __init__(self, confidence_threshold: float = 0.5) -> None:
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self._confidence_threshold = confidence_threshold

    def detect(self, frame: np.ndarray) -> list[Detection]:
        height, width = frame.shape[:2]
        boxes, weights = self._hog.detectMultiScale(
            frame, winStride=(8, 8), padding=(8, 8), scale=1.05
        )

        detections = []
        for (x, y, w, h), weight in zip(boxes, weights):
            # HOG's decision-function weight isn't a probability; squash it into (0,1)
            # so it's comparable to the confidence_threshold used elsewhere.
            confidence = float(1 / (1 + np.exp(-weight)))
            if confidence < self._confidence_threshold:
                continue
            detections.append(
                Detection(
                    object_type="PERSON",
                    confidence=confidence,
                    x=x / width,
                    y=y / height,
                    width=w / width,
                    height=h / height,
                )
            )
        return detections
