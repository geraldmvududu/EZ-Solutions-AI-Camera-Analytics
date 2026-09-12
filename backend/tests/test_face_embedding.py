"""Direct tests of the real LBP-histogram algorithm in app/services/face_embedding.py
— no mocking here, unlike the other face_* test files. These exercise the actual
detection/embedding/matching math itself."""

import cv2
import numpy as np

from app.services import face_embedding


def _structured_image() -> np.ndarray:
    img = np.zeros((200, 200), dtype=np.uint8)
    for r in range(10, 90, 15):
        cv2.circle(img, (100, 100), r, 255, 3)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def test_embedding_is_deterministic_and_fixed_length():
    img = _structured_image()
    face = face_embedding.DetectedFace(40, 30, 100, 100)
    v1 = face_embedding.compute_embedding(img, face)
    v2 = face_embedding.compute_embedding(img, face)
    assert v1.shape == (face_embedding.EMBEDDING_DIM,)
    assert np.array_equal(v1, v2)


def test_self_match_confidence_is_perfect():
    img = _structured_image()
    face = face_embedding.DetectedFace(40, 30, 100, 100)
    v1 = face_embedding.compute_embedding(img, face)
    v2 = face_embedding.compute_embedding(img, face)
    assert face_embedding.compare_embeddings(v1, v2) == 1.0


def test_embedding_serialization_round_trips_exactly():
    img = _structured_image()
    face = face_embedding.DetectedFace(40, 30, 100, 100)
    vector = face_embedding.compute_embedding(img, face)
    encoded = face_embedding.embedding_to_base64(vector)
    decoded = face_embedding.embedding_from_base64(encoded)
    assert np.array_equal(vector, decoded)


def test_compare_embeddings_returns_zero_for_mismatched_shapes():
    a = np.zeros(10, dtype=np.float32)
    b = np.zeros(20, dtype=np.float32)
    assert face_embedding.compare_embeddings(a, b) == 0.0


def test_decode_image_bytes_handles_invalid_data():
    assert face_embedding.decode_image_bytes(b"not an image") is None


def test_assess_enrollment_quality_rejects_no_face():
    blank = np.full((200, 200, 3), 128, dtype=np.uint8)
    result = face_embedding.assess_enrollment_quality(blank, 0.70)
    assert result.passed is False
    assert result.face_count == 0


def test_assess_enrollment_quality_rejects_blurry_flat_image(monkeypatch):
    face = face_embedding.DetectedFace(10, 10, 150, 150)
    monkeypatch.setattr(face_embedding, "detect_faces", lambda frame: [face])
    flat = np.full((200, 200, 3), 128, dtype=np.uint8)  # zero edges -> zero blur score
    result = face_embedding.assess_enrollment_quality(flat, 0.70)
    assert result.passed is False
    assert "blurry" in result.reason.lower()


def test_assess_recognition_quality_picks_largest_face_without_rejecting(monkeypatch):
    big = face_embedding.DetectedFace(0, 0, 150, 150)
    small = face_embedding.DetectedFace(150, 150, 20, 20)
    monkeypatch.setattr(face_embedding, "detect_faces", lambda frame: [big, small])
    img = _structured_image()
    result = face_embedding.assess_recognition_quality(img, 0.0)
    assert result.face is big
