"""Multi-frame confirmation (FaceRecognitionSettings.multi_frame_confirmation_enabled,
section 4/13): requires two consecutive recognize calls for the same (camera,
tracking_id) to agree on the same person before a real Event/Alert is created. See
app/api/routes/faces.py's _pending_confirmations.

Uses the shared `one_face` fixture (tests/conftest.py), which mocks compute_embedding
to a deterministic, well-separated vector — the real (unmocked) LBP algorithm's
separation between two random-noise test images is too weak to reliably tell two fake
enrolled people apart (that's a synthetic-test-data limitation, not a real accuracy
bug — see test_face_embedding.py, which exercises the real algorithm directly)."""

import cv2
import numpy as np

from app.services import face_embedding
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _enroll(client, token, seed: int, first_name: str = "Jane", last_name: str = "Doe") -> tuple[dict, list[float]]:
    rng = np.random.default_rng(seed)
    frame = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    resp = client.post(
        "/api/faces/enroll",
        data={"first_name": first_name, "last_name": last_name, "category": "EMPLOYEE"},
        files={"photo": ("face.jpg", buf.tobytes(), "image/jpeg")},
        headers=auth_headers(token),
    )
    assert resp.json()["success"] is True, resp.json()
    person = resp.json()["person"]
    decoded = face_embedding.decode_image_bytes(buf.tobytes())
    face = face_embedding.DetectedFace(40, 30, 100, 100)
    embedding = face_embedding.compute_embedding(decoded, face).tolist()
    return person, embedding


def _enable_multi_frame_confirmation(client, token) -> None:
    resp = client.put("/api/face-settings", json={"multi_frame_confirmation_enabled": True}, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text


def test_first_match_is_pending_and_creates_nothing(client, admin_user, one_face):
    token = login(client, admin_user.email)
    _enable_multi_frame_confirmation(client, token)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    person, embedding = _enroll(client, token, seed=1)

    resp = client.post(
        "/api/faces/recognize",
        json={"camera_id": cam["id"], "tracking_id": 1, "embedding": embedding, "model_version": "lbph-v1", "quality_score": 0.9, "occurred_at": "2026-01-01T12:00:00Z"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["recognition_status"] == "PENDING_CONFIRMATION"
    assert body["event_id"] is None
    assert body["person_id"] == person["id"]

    assert client.get("/api/face-events", headers=auth_headers(token)).json() == []


def test_second_consecutive_match_confirms_and_creates_event(client, admin_user, one_face):
    token = login(client, admin_user.email)
    _enable_multi_frame_confirmation(client, token)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    person, embedding = _enroll(client, token, seed=1)

    payload = {"camera_id": cam["id"], "tracking_id": 1, "embedding": embedding, "model_version": "lbph-v1", "quality_score": 0.9, "occurred_at": "2026-01-01T12:00:00Z"}
    first = client.post("/api/faces/recognize", json=payload, headers=INTERNAL_HEADERS).json()
    assert first["recognition_status"] == "PENDING_CONFIRMATION"

    second = client.post("/api/faces/recognize", json={**payload, "occurred_at": "2026-01-01T12:00:30Z"}, headers=INTERNAL_HEADERS).json()
    assert second["recognition_status"] == "RECOGNIZED"
    assert second["event_id"] is not None

    face_events = client.get("/api/face-events", headers=auth_headers(token)).json()
    assert len(face_events) == 1
    assert face_events[0]["person_id"] == person["id"]


def test_disabled_by_default_confirms_on_first_match(client, admin_user, one_face):
    """Regression guard: multi_frame_confirmation_enabled defaults to False — every
    existing face-matching test relies on a single match being enough."""
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    person, embedding = _enroll(client, token, seed=1)

    resp = client.post(
        "/api/faces/recognize",
        json={"camera_id": cam["id"], "tracking_id": 1, "embedding": embedding, "model_version": "lbph-v1", "quality_score": 0.9, "occurred_at": "2026-01-01T12:00:00Z"},
        headers=INTERNAL_HEADERS,
    ).json()
    assert resp["recognition_status"] == "RECOGNIZED"
    assert resp["person_id"] == person["id"]


def test_different_person_on_second_attempt_resets_pending_state(client, admin_user, one_face):
    """If the two consecutive attempts disagree on WHO it is, that must not silently
    confirm either identity — the second attempt starts a fresh pending state."""
    token = login(client, admin_user.email)
    _enable_multi_frame_confirmation(client, token)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    _person_a, embedding_a = _enroll(client, token, seed=1, first_name="Jane", last_name="Doe")
    _person_b, embedding_b = _enroll(client, token, seed=99, first_name="John", last_name="Smith")

    first = client.post(
        "/api/faces/recognize",
        json={"camera_id": cam["id"], "tracking_id": 1, "embedding": embedding_a, "model_version": "lbph-v1", "quality_score": 0.9, "occurred_at": "2026-01-01T12:00:00Z"},
        headers=INTERNAL_HEADERS,
    ).json()
    assert first["recognition_status"] == "PENDING_CONFIRMATION"

    second = client.post(
        "/api/faces/recognize",
        json={"camera_id": cam["id"], "tracking_id": 1, "embedding": embedding_b, "model_version": "lbph-v1", "quality_score": 0.9, "occurred_at": "2026-01-01T12:00:05Z"},
        headers=INTERNAL_HEADERS,
    ).json()
    # A different person matched — this becomes the new pending candidate, not an
    # instant confirmation of either identity.
    assert second["recognition_status"] == "PENDING_CONFIRMATION"
    assert second["person_id"] == _person_b["id"]
    assert client.get("/api/face-events", headers=auth_headers(token)).json() == []
