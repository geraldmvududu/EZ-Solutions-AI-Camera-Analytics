"""Face enrollment (section 2): quality gates, duplicate detection, RBAC. Face
detection itself is monkeypatched to a fixed bounding box — Haar cascades don't
reliably fire on synthetic test images, and that's not what these tests are
verifying; they verify the enrollment pipeline (validation, DB writes, duplicate
rejection, permissions) around it. face_embedding's real blur/brightness/LBP math
runs unmodified against the synthetic images below."""

import numpy as np
import cv2
import pytest

from app.services import face_embedding
from tests.conftest import auth_headers, login


def _textured_jpeg_bytes(seed: int) -> bytes:
    # Uniform random noise gives a high (not zero) Laplacian variance, so the real
    # blur-quality check passes — a flat/solid image would fail it for real reasons
    # unrelated to what these tests check.
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


@pytest.fixture
def no_face(monkeypatch):
    monkeypatch.setattr(face_embedding, "detect_faces", lambda frame: [])


@pytest.fixture
def two_faces(monkeypatch):
    faces = [face_embedding.DetectedFace(10, 10, 80, 80), face_embedding.DetectedFace(100, 100, 80, 80)]
    monkeypatch.setattr(face_embedding, "detect_faces", lambda frame: faces)


def _enroll(client, token, seed=1, first_name="Jane", last_name="Doe", category="EMPLOYEE"):
    return client.post(
        "/api/faces/enroll",
        data={"first_name": first_name, "last_name": last_name, "category": category},
        files={"photo": ("face.jpg", _textured_jpeg_bytes(seed), "image/jpeg")},
        headers=auth_headers(token),
    )


def test_enroll_success(client, admin_user, one_face):
    token = login(client, admin_user.email)
    resp = _enroll(client, token)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Face successfully enrolled"
    assert body["person"]["first_name"] == "Jane"
    assert len(body["person"]["face_profiles"]) == 1


def test_enroll_rejects_no_face(client, admin_user, no_face):
    token = login(client, admin_user.email)
    resp = _enroll(client, token)
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is False
    assert "No face detected" in body["message"]


def test_enroll_rejects_multiple_faces(client, admin_user, two_faces):
    token = login(client, admin_user.email)
    resp = _enroll(client, token)
    body = resp.json()
    assert body["success"] is False
    assert "Multiple faces" in body["message"]


def test_enroll_rejects_duplicate(client, admin_user, one_face):
    token = login(client, admin_user.email)
    first = _enroll(client, token, seed=7, first_name="Jane", last_name="Doe")
    assert first.json()["success"] is True

    duplicate = _enroll(client, token, seed=7, first_name="John", last_name="Smith")
    body = duplicate.json()
    assert body["success"] is False
    assert "already enrolled" in body["message"]
    assert "Jane" in body["message"]


def test_enroll_allows_different_people(client, admin_user, one_face):
    token = login(client, admin_user.email)
    first = _enroll(client, token, seed=1, first_name="Jane", last_name="Doe")
    second = _enroll(client, token, seed=99, first_name="John", last_name="Smith")
    assert first.json()["success"] is True
    assert second.json()["success"] is True


def test_enroll_requires_manage_biometrics_permission(client, viewer_user, one_face):
    token = login(client, viewer_user.email)
    resp = _enroll(client, token)
    assert resp.status_code == 403


def test_embedding_never_returned_in_api_response(client, admin_user, one_face):
    token = login(client, admin_user.email)
    enrolled = _enroll(client, token).json()
    person_id = enrolled["person"]["id"]

    resp = client.get(f"/api/faces/{person_id}", headers=auth_headers(token))
    body_text = resp.text
    assert "embedding_encrypted" not in body_text
    assert "embedding" not in resp.json()["face_profiles"][0]


def test_delete_person_removes_face_profile(client, db_session, admin_user, one_face):
    import uuid

    from app.models.face_profile import FaceProfile
    from app.models.person import Person, PersonStatus

    token = login(client, admin_user.email)
    enrolled = _enroll(client, token).json()
    person_id = enrolled["person"]["id"]

    resp = client.delete(f"/api/faces/{person_id}", headers=auth_headers(token))
    assert resp.status_code == 204

    person = db_session.get(Person, uuid.UUID(person_id))
    assert person.status == PersonStatus.DELETED
    remaining_profiles = db_session.query(FaceProfile).filter(FaceProfile.person_id == person.id).count()
    assert remaining_profiles == 0
