"""ai-engine's copy of face_embedding.py is intentionally byte-identical to the
backend's (see the module docstring) — this file confirms it behaves the same way
here, using the same real (unmocked) LBP algorithm."""

import cv2
import numpy as np

from app.core import face_embedding


def _structured_image() -> np.ndarray:
    img = np.zeros((200, 200), dtype=np.uint8)
    for r in range(10, 90, 15):
        cv2.circle(img, (100, 100), r, 255, 3)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def test_embedding_deterministic_and_self_match():
    img = _structured_image()
    face = face_embedding.DetectedFace(40, 30, 100, 100)
    v1 = face_embedding.compute_embedding(img, face)
    v2 = face_embedding.compute_embedding(img, face)
    assert face_embedding.compare_embeddings(v1, v2) == 1.0


def test_assess_recognition_quality_accepts_multiple_faces(monkeypatch):
    faces = [face_embedding.DetectedFace(0, 0, 150, 150), face_embedding.DetectedFace(150, 150, 20, 20)]
    monkeypatch.setattr(face_embedding, "detect_faces", lambda frame: faces)
    result = face_embedding.assess_recognition_quality(_structured_image(), 0.0)
    assert result.face_count == 2
    assert result.face is faces[0]


def test_assess_enrollment_quality_rejects_multiple_faces(monkeypatch):
    faces = [face_embedding.DetectedFace(0, 0, 150, 150), face_embedding.DetectedFace(150, 150, 20, 20)]
    monkeypatch.setattr(face_embedding, "detect_faces", lambda frame: faces)
    result = face_embedding.assess_enrollment_quality(_structured_image(), 0.0)
    assert result.passed is False
    assert "Multiple faces" in result.reason
