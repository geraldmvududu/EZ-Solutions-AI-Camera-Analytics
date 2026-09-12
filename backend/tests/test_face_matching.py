"""POST /api/faces/recognize (section 4/6/7): the ai-engine-facing internal endpoint
that does real server-side embedding comparison, event/alert creation via the SAME
rule engine as every other event type, and respects the max-events-per-hour cap."""

from unittest.mock import patch

import cv2
import numpy as np

from app.services import face_embedding
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _textured_frame(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)


def _enroll_and_get_embedding(client, token, seed: int) -> list[float]:
    frame = _textured_frame(seed)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    jpeg_bytes = buf.tobytes()
    resp = client.post(
        "/api/faces/enroll",
        data={"first_name": "Jane", "last_name": "Doe", "category": "EMPLOYEE"},
        files={"photo": ("face.jpg", jpeg_bytes, "image/jpeg")},
        headers=auth_headers(token),
    )
    assert resp.json()["success"] is True
    # Recompute from the JPEG-decoded bytes, not the pre-encode array — JPEG is lossy,
    # so the server's decoded frame (what it actually embedded) differs slightly from
    # the original array, which would otherwise flip the deterministic test hash.
    decoded = face_embedding.decode_image_bytes(jpeg_bytes)
    face = face_embedding.DetectedFace(40, 30, 100, 100)
    vector = face_embedding.compute_embedding(decoded, face)
    return vector.tolist(), resp.json()["person"]["id"]


def test_recognize_matches_enrolled_person(client, admin_user, one_face):
    token = login(client, admin_user.email)
    embedding, person_id = _enroll_and_get_embedding(client, token, seed=5)

    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    resp = client.post(
        "/api/faces/recognize",
        json={
            "camera_id": cam["id"], "tracking_id": 1, "embedding": embedding,
            "model_version": "lbph-v1", "quality_score": 0.9, "occurred_at": "2026-01-01T00:00:00Z",
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["recognition_status"] == "RECOGNIZED"
    assert body["person_id"] == person_id
    assert body["confidence_score"] > 0.8


def test_recognize_unknown_person(client, admin_user, one_face):
    token = login(client, admin_user.email)
    _enroll_and_get_embedding(client, token, seed=5)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    # A wildly different random embedding (different seed) should not match.
    unrelated_frame = _textured_frame(777)
    unrelated_vector = face_embedding.compute_embedding(unrelated_frame, face_embedding.DetectedFace(40, 30, 100, 100)).tolist()

    resp = client.post(
        "/api/faces/recognize",
        json={
            "camera_id": cam["id"], "tracking_id": 2, "embedding": unrelated_vector,
            "model_version": "lbph-v1", "quality_score": 0.9, "occurred_at": "2026-01-01T00:00:00Z",
        },
        headers=INTERNAL_HEADERS,
    )
    body = resp.json()
    assert body["recognition_status"] == "UNKNOWN"
    assert body["person_id"] is None


def test_recognize_requires_internal_token(client):
    resp = client.post(
        "/api/faces/recognize",
        json={"camera_id": "00000000-0000-0000-0000-000000000000", "tracking_id": 1, "embedding": [0.0], "model_version": "lbph-v1", "quality_score": 0.9, "occurred_at": "2026-01-01T00:00:00Z"},
    )
    assert resp.status_code == 401


def test_recognized_event_triggers_rule_engine_and_alert(client, admin_user, one_face):
    token = login(client, admin_user.email)
    embedding, _ = _enroll_and_get_embedding(client, token, seed=5)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    client.post(
        "/api/rules",
        json={"name": "Recognized rule", "conditions": {"event_type": "FACE_RECOGNIZED"}, "action_severity": "HIGH", "action_alert_type": "FACE_RECOGNIZED_ALERT"},
        headers=auth_headers(token),
    )

    with patch("app.services.notification_service.send_push_notifications"):
        resp = client.post(
            "/api/faces/recognize",
            json={
                "camera_id": cam["id"], "tracking_id": 1, "embedding": embedding,
                "model_version": "lbph-v1", "quality_score": 0.9, "occurred_at": "2026-01-01T00:00:00Z",
            },
            headers=INTERNAL_HEADERS,
        )
    assert resp.status_code == 200

    alerts = client.get("/api/face-alerts", headers=auth_headers(token)).json()
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "HIGH"


def test_suspended_person_rule_matches_via_person_status_condition(client, admin_user, one_face):
    """Section 8's Suspended Person rule: person_status condition, populated into
    event_metadata by /faces/recognize, matched by rule_engine._rule_matches."""
    import uuid

    from app.models.person import Person, PersonStatus

    token = login(client, admin_user.email)
    embedding, person_id = _enroll_and_get_embedding(client, token, seed=5)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    client.put(f"/api/faces/{person_id}", json={"status": "SUSPENDED"}, headers=auth_headers(token))

    client.post(
        "/api/rules",
        json={
            "name": "Suspended person rule",
            "conditions": {"event_type": "FACE_RECOGNIZED", "person_status": "SUSPENDED"},
            "action_severity": "CRITICAL", "action_alert_type": "FACE_SUSPENDED_PERSON",
        },
        headers=auth_headers(token),
    )

    with patch("app.services.notification_service.send_push_notifications"):
        client.post(
            "/api/faces/recognize",
            json={
                "camera_id": cam["id"], "tracking_id": 1, "embedding": embedding,
                "model_version": "lbph-v1", "quality_score": 0.9, "occurred_at": "2026-01-01T00:00:00Z",
            },
            headers=INTERNAL_HEADERS,
        )

    alerts = client.get("/api/face-alerts", headers=auth_headers(token)).json()
    assert any(a["alert_type"] == "FACE_SUSPENDED_PERSON" and a["severity"] == "CRITICAL" for a in alerts)
