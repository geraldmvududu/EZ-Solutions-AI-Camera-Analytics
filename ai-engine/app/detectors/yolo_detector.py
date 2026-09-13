import numpy as np

from app.config import get_settings
from app.detectors.base import Detection, Detector

settings = get_settings()

# COCO class name -> this platform's existing object-type vocabulary (already
# anticipated verbatim in Detection's docstring: "PERSON, CAR, TRUCK, BUS, MOTORCYCLE,
# BICYCLE, ANIMAL, BACKPACK, BAG, SUITCASE"). Any COCO class not listed here (chair,
# laptop, etc.) is dropped — not part of this platform's vocabulary, matching
# worker.py's VEHICLE_TYPES and everywhere else that only knows this set.
#
# Real, honest scope limit (see CLAUDE.md): COCO has no generic "box"/"package"
# class. "Theft" detection here means backpack/handbag/suitcase specifically, not
# literal cardboard boxes/packages — there is no feasible way to add that class
# without training a custom model, which this environment can't do.
_COCO_NAME_TO_OBJECT_TYPE = {
    "person": "PERSON",
    "bicycle": "BICYCLE",
    "car": "CAR",
    "motorcycle": "MOTORCYCLE",
    "bus": "BUS",
    "truck": "TRUCK",
    "backpack": "BACKPACK",
    "handbag": "BAG",
    "suitcase": "SUITCASE",
    "cat": "ANIMAL",
    "dog": "ANIMAL",
    "horse": "ANIMAL",
    "sheep": "ANIMAL",
    "cow": "ANIMAL",
    "elephant": "ANIMAL",
    "bear": "ANIMAL",
    "zebra": "ANIMAL",
    "giraffe": "ANIMAL",
}


class YoloDetector(Detector):
    """Real multi-class object detection via Ultralytics YOLOv8n (opt-in per camera —
    see Camera.multi_class_detection_enabled and app/detectors/__init__.py::
    build_detector). This is what makes AI Video Intelligence Phase 2's "potential
    theft" detection possible at all: the default HOGPersonDetector only ever sees
    PERSON, so there is no way to notice a backpack/handbag/suitcase being removed
    from a monitored area without this.

    `ultralytics` (and its `torch` dependency) is only imported here, lazily, inside
    __init__ — a process running only HOG-only cameras never pays torch's import
    cost. Weights are loaded from a path on the persistent ./data/models Docker
    volume mount (settings.model_path), not a bare filename, so Ultralytics'
    missing-file auto-download lands there directly and survives container
    restarts/rebuilds instead of re-downloading into some image-local cache.
    """

    def __init__(self, confidence_threshold: float = 0.5) -> None:
        from ultralytics import YOLO  # lazy: avoid paying torch's import cost unless used

        weights_path = f"{settings.model_path.rstrip('/')}/yolov8n.pt"
        self._model = YOLO(weights_path)
        self._confidence_threshold = confidence_threshold

    def detect(self, frame: np.ndarray) -> list[Detection]:
        height, width = frame.shape[:2]
        results = self._model.predict(frame, verbose=False)
        if not results:
            return []
        boxes = results[0].boxes

        detections = []
        for box in boxes:
            confidence = float(box.conf[0])
            if confidence < self._confidence_threshold:
                continue
            class_name = self._model.names[int(box.cls[0])]
            object_type = _COCO_NAME_TO_OBJECT_TYPE.get(class_name)
            if object_type is None:
                continue
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
            detections.append(
                Detection(
                    object_type=object_type,
                    confidence=confidence,
                    x=x1 / width,
                    y=y1 / height,
                    width=(x2 - x1) / width,
                    height=(y2 - y1) / height,
                )
            )
        return detections
