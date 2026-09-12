"""Every biometric-touching action must be audited (section 3/14) — reuses the
existing AuditLog/log_action, not a separate biometric_audit_log table."""

import cv2
import numpy as np

from app.models.audit import AuditLog
from tests.conftest import auth_headers, login


def _jpeg_bytes(seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _enroll(client, token, seed=1):
    return client.post(
        "/api/faces/enroll",
        data={"first_name": "Jane", "last_name": "Doe", "category": "EMPLOYEE"},
        files={"photo": ("face.jpg", _jpeg_bytes(seed), "image/jpeg")},
        headers=auth_headers(token),
    )


def test_enroll_writes_audit_log(client, db_session, admin_user, one_face):
    token = login(client, admin_user.email)
    _enroll(client, token)

    entries = db_session.query(AuditLog).filter(AuditLog.action == "FACE_ENROLL").all()
    assert len(entries) == 1
    assert entries[0].user_id == admin_user.id
    assert entries[0].resource_type == "person"


def test_delete_writes_audit_log(client, db_session, admin_user, one_face):
    token = login(client, admin_user.email)
    person_id = _enroll(client, token).json()["person"]["id"]
    client.delete(f"/api/faces/{person_id}", headers=auth_headers(token))

    entries = db_session.query(AuditLog).filter(AuditLog.action == "FACE_DELETE").all()
    assert len(entries) == 1
    assert entries[0].resource_id == person_id


def test_view_photo_writes_audit_log(client, db_session, admin_user, one_face):
    token = login(client, admin_user.email)
    person_id = _enroll(client, token).json()["person"]["id"]
    client.get(f"/api/faces/{person_id}/photo", headers=auth_headers(token))

    entries = db_session.query(AuditLog).filter(AuditLog.action == "FACE_VIEW").all()
    assert len(entries) == 1
