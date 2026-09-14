"""Master Development Prompt Phase 1, "License Plate Reading (ANPR)". Mirrors
test_face_recognizer.py's structure — cooldown, exception-safety — plus the regex
sanity check that rejects obvious OCR garbage. The real (unmocked) Haar cascade +
Tesseract OCR pipeline was verified separately by hand: rendered known text into a
synthetic image and confirmed pytesseract read it back exactly (see CLAUDE.md) — here,
pytesseract/find_plate_region are mocked at the boundary, the same rationale already
used for ultralytics.YOLO and the ffmpeg subprocess elsewhere in this test suite, since
not every machine running `pytest` has the real tesseract binary installed."""

import numpy as np
import pytest

from app.core import plate_reader as plate_reader_module
from app.core.plate_reader import PlateReader, clean_plate_text
from app.detectors.base import Detection

CAMERA = {"id": "cam-1", "plate_recognition_enabled": True}


def _frame() -> np.ndarray:
    return np.zeros((200, 200, 3), dtype=np.uint8)


def _detection() -> Detection:
    return Detection(object_type="CAR", confidence=0.9, x=0.1, y=0.1, width=0.5, height=0.5)


def test_clean_plate_text_accepts_a_plausible_read():
    assert clean_plate_text("ca 123-456") == "CA123456"


def test_clean_plate_text_rejects_garbage():
    assert clean_plate_text("##") is None
    assert clean_plate_text("") is None
    assert clean_plate_text("A") is None


def test_reads_and_reports_a_valid_plate(monkeypatch):
    calls = []
    monkeypatch.setattr(plate_reader_module, "find_plate_region", lambda crop: (5, 5, 40, 15))
    monkeypatch.setattr(plate_reader_module.pytesseract, "image_to_string", lambda crop, config=None: "CA123456")
    monkeypatch.setattr(plate_reader_module.backend_client, "recognize_plate", lambda payload: calls.append(payload))

    reader = PlateReader("cam-1")
    reader.maybe_read_plate(CAMERA, _frame(), 1, _detection(), recording_id="rec-1")

    assert len(calls) == 1
    assert calls[0]["plate_text"] == "CA123456"
    assert calls[0]["vehicle_type"] == "CAR"
    assert calls[0]["tracking_id"] == 1
    assert calls[0]["recording_id"] == "rec-1"


def test_no_plate_region_found_does_not_call_recognize(monkeypatch):
    calls = []
    monkeypatch.setattr(plate_reader_module, "find_plate_region", lambda crop: None)
    monkeypatch.setattr(plate_reader_module.backend_client, "recognize_plate", lambda payload: calls.append(payload))

    reader = PlateReader("cam-1")
    reader.maybe_read_plate(CAMERA, _frame(), 1, _detection())

    assert calls == []


def test_implausible_ocr_read_is_rejected(monkeypatch):
    calls = []
    monkeypatch.setattr(plate_reader_module, "find_plate_region", lambda crop: (5, 5, 40, 15))
    monkeypatch.setattr(plate_reader_module.pytesseract, "image_to_string", lambda crop, config=None: "##")
    monkeypatch.setattr(plate_reader_module.backend_client, "recognize_plate", lambda payload: calls.append(payload))

    reader = PlateReader("cam-1")
    reader.maybe_read_plate(CAMERA, _frame(), 1, _detection())

    assert calls == []


def test_cooldown_prevents_a_second_attempt_too_soon(monkeypatch):
    calls = []
    monkeypatch.setattr(plate_reader_module, "find_plate_region", lambda crop: (5, 5, 40, 15))
    monkeypatch.setattr(plate_reader_module.pytesseract, "image_to_string", lambda crop, config=None: "CA123456")
    monkeypatch.setattr(plate_reader_module.backend_client, "recognize_plate", lambda payload: calls.append(payload))

    reader = PlateReader("cam-1")
    reader.maybe_read_plate(CAMERA, _frame(), 1, _detection())
    reader.maybe_read_plate(CAMERA, _frame(), 1, _detection())

    assert len(calls) == 1, "a second attempt within the cooldown window must not re-read"


def test_cooldown_is_scoped_per_track(monkeypatch):
    calls = []
    monkeypatch.setattr(plate_reader_module, "find_plate_region", lambda crop: (5, 5, 40, 15))
    monkeypatch.setattr(plate_reader_module.pytesseract, "image_to_string", lambda crop, config=None: "CA123456")
    monkeypatch.setattr(plate_reader_module.backend_client, "recognize_plate", lambda payload: calls.append(payload))

    reader = PlateReader("cam-1")
    reader.maybe_read_plate(CAMERA, _frame(), 1, _detection())
    reader.maybe_read_plate(CAMERA, _frame(), 2, _detection())

    assert len(calls) == 2, "a genuinely different tracked vehicle must not share the first one's cooldown"


def test_a_recognition_bug_never_propagates(monkeypatch):
    """Exception-safety: maybe_read_plate must never raise, the same convention as
    FaceRecognizer.maybe_recognize — an ANPR bug must never stop the capture loop."""

    def _boom(crop):
        raise RuntimeError("boom")

    monkeypatch.setattr(plate_reader_module, "find_plate_region", _boom)

    reader = PlateReader("cam-1")
    reader.maybe_read_plate(CAMERA, _frame(), 1, _detection())  # must not raise
