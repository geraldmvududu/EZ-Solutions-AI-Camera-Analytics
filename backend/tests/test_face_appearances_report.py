"""GET /api/reports/face-appearances.csv (section 6/23): a person's real appearance
history as a CSV, including any linked recording so the evidence can be located
directly from the export."""

from app.services import face_embedding
from tests.conftest import auth_headers, login

INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def test_face_appearances_csv_includes_recognized_event(client, admin_user, one_face):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    import cv2
    import numpy as np

    rng = np.random.default_rng(1)
    frame = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    enrolled = client.post(
        "/api/faces/enroll",
        data={"first_name": "Jane", "last_name": "Doe", "category": "EMPLOYEE"},
        files={"photo": ("face.jpg", buf.tobytes(), "image/jpeg")},
        headers=auth_headers(token),
    ).json()
    person_id = enrolled["person"]["id"]
    decoded = face_embedding.decode_image_bytes(buf.tobytes())
    embedding = face_embedding.compute_embedding(decoded, face_embedding.DetectedFace(40, 30, 100, 100)).tolist()

    client.post(
        "/api/faces/recognize",
        json={"camera_id": cam["id"], "tracking_id": 1, "embedding": embedding, "model_version": "lbph-v1", "quality_score": 0.9, "occurred_at": "2026-01-01T12:00:00Z"},
        headers=INTERNAL_HEADERS,
    )

    resp = client.get(f"/api/reports/face-appearances.csv?person_id={person_id}", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "RECOGNIZED" in resp.text
    assert "Event ID" in resp.text.splitlines()[0]


def test_face_appearances_csv_requires_permission(client, viewer_user):
    resp = client.get("/api/reports/face-appearances.csv?person_id=00000000-0000-0000-0000-000000000000", headers=auth_headers(login(client, viewer_user.email)))
    # VIEWER role does not have view_biometric_events per ROLE_PERMISSION_MAP.
    assert resp.status_code == 403
