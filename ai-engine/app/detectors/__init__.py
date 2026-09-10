from app.detectors.base import Detection, Detector
from app.detectors.hog_detector import HOGPersonDetector


def build_detector() -> Detector:
    # Pluggable by design (section 51): swap this for a YOLO/ONNX detector later
    # without touching the worker loop, as long as it implements Detector.detect().
    return HOGPersonDetector()


__all__ = ["Detection", "Detector", "HOGPersonDetector", "build_detector"]
