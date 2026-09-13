"""YoloDetector (AI Video Intelligence Phase 2): real multi-class detection via
Ultralytics YOLOv8n. The `ultralytics.YOLO` model object itself is mocked at the
boundary here — same rationale as test_recorder.py mocking the ffmpeg subprocess: a
real download+inference dependency is correctly verified manually (see CLAUDE.md)
rather than paid on every CI run. What's under test is this platform's own mapping/
filtering logic around that boundary.
"""

import numpy as np
import pytest


class _FakeBox:
    def __init__(self, conf: float, cls: float, xyxy: list[float]) -> None:
        self.conf = [conf]
        self.cls = [cls]
        self.xyxy = [xyxy]


class _FakeResult:
    def __init__(self, boxes: list[_FakeBox]) -> None:
        self.boxes = boxes


class _FakeYoloModel:
    def __init__(self, names: dict[int, str], boxes: list[_FakeBox]) -> None:
        self.names = names
        self._boxes = boxes

    def predict(self, frame, verbose: bool = False):
        return [_FakeResult(self._boxes)]


def _make_detector(monkeypatch, names: dict[int, str], boxes: list[_FakeBox], confidence_threshold: float = 0.5):
    fake_model = _FakeYoloModel(names, boxes)
    monkeypatch.setattr("ultralytics.YOLO", lambda weights_path: fake_model)

    from app.detectors.yolo_detector import YoloDetector

    return YoloDetector(confidence_threshold=confidence_threshold)


def _frame() -> np.ndarray:
    return np.zeros((100, 200, 3), dtype=np.uint8)  # height=100, width=200


def test_maps_known_coco_classes_to_platform_object_types(monkeypatch):
    names = {0: "person", 24: "backpack", 26: "handbag", 28: "suitcase", 2: "car", 16: "dog"}
    boxes = [
        _FakeBox(conf=0.9, cls=0, xyxy=[20.0, 10.0, 60.0, 90.0]),   # person
        _FakeBox(conf=0.8, cls=24, xyxy=[0.0, 0.0, 20.0, 20.0]),    # backpack
        _FakeBox(conf=0.8, cls=26, xyxy=[0.0, 0.0, 20.0, 20.0]),    # handbag -> BAG
        _FakeBox(conf=0.8, cls=28, xyxy=[0.0, 0.0, 20.0, 20.0]),    # suitcase
        _FakeBox(conf=0.8, cls=2, xyxy=[0.0, 0.0, 20.0, 20.0]),     # car
        _FakeBox(conf=0.8, cls=16, xyxy=[0.0, 0.0, 20.0, 20.0]),    # dog -> ANIMAL
    ]
    detector = _make_detector(monkeypatch, names, boxes)

    detections = detector.detect(_frame())

    assert [d.object_type for d in detections] == ["PERSON", "BACKPACK", "BAG", "SUITCASE", "CAR", "ANIMAL"]


def test_bounding_box_is_normalized_to_frame_dimensions(monkeypatch):
    names = {0: "person"}
    boxes = [_FakeBox(conf=0.9, cls=0, xyxy=[20.0, 10.0, 60.0, 90.0])]
    detector = _make_detector(monkeypatch, names, boxes)

    [detection] = detector.detect(_frame())  # frame is height=100, width=200

    assert detection.x == pytest.approx(20.0 / 200)
    assert detection.y == pytest.approx(10.0 / 100)
    assert detection.width == pytest.approx((60.0 - 20.0) / 200)
    assert detection.height == pytest.approx((90.0 - 10.0) / 100)


def test_filters_out_detections_below_confidence_threshold(monkeypatch):
    names = {0: "person"}
    boxes = [_FakeBox(conf=0.3, cls=0, xyxy=[0.0, 0.0, 10.0, 10.0])]
    detector = _make_detector(monkeypatch, names, boxes, confidence_threshold=0.5)

    assert detector.detect(_frame()) == []


def test_drops_coco_classes_outside_platform_vocabulary(monkeypatch):
    names = {56: "chair", 63: "laptop"}
    boxes = [
        _FakeBox(conf=0.9, cls=56, xyxy=[0.0, 0.0, 10.0, 10.0]),
        _FakeBox(conf=0.9, cls=63, xyxy=[0.0, 0.0, 10.0, 10.0]),
    ]
    detector = _make_detector(monkeypatch, names, boxes)

    assert detector.detect(_frame()) == []
