from app.detectors.base import Detection, Detector
from app.detectors.hog_detector import HOGPersonDetector
from app.detectors.yolo_detector import YoloDetector


def build_detector(camera: dict) -> Detector:
    # Pluggable by design (section 51). Existing cameras keep the cheap PERSON-only
    # HOG detector unchanged by default; multi_class_detection_enabled opts a specific
    # camera into the heavier real multi-class YOLOv8n detector (required for
    # ASSET_ZONE/theft detection to see anything but PERSON at all — see
    # yolo_detector.py and CLAUDE.md).
    confidence_threshold = camera.get("confidence_threshold") or 0.5
    if camera.get("multi_class_detection_enabled"):
        return YoloDetector(confidence_threshold=confidence_threshold)
    return HOGPersonDetector(confidence_threshold=confidence_threshold)


__all__ = ["Detection", "Detector", "HOGPersonDetector", "YoloDetector", "build_detector"]
