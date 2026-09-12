"""Biometric data must be completely isolated between tenants (section 18) — every
face-related query goes through tenant_filter_value the same way every other
tenant-scoped resource in this codebase does."""

import cv2
import numpy as np

from tests.conftest import auth_headers, login
from tests.test_tenant_isolation import make_second_tenant_admin


def _jpeg_bytes(seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def test_tenant_b_cannot_see_tenant_a_person(client, db_session, admin_user, roles, one_face):
    token_a = login(client, admin_user.email)
    enrolled = client.post(
        "/api/faces/enroll",
        data={"first_name": "Jane", "last_name": "Doe", "category": "EMPLOYEE"},
        files={"photo": ("face.jpg", _jpeg_bytes(1), "image/jpeg")},
        headers=auth_headers(token_a),
    ).json()
    person_id = enrolled["person"]["id"]

    _tenant_b, user_b = make_second_tenant_admin(db_session, roles)
    token_b = login(client, user_b.email)

    resp = client.get(f"/api/faces/{person_id}", headers=auth_headers(token_b))
    assert resp.status_code == 404

    list_resp = client.get("/api/faces", headers=auth_headers(token_b))
    assert list_resp.json() == []


def test_tenant_b_cannot_delete_tenant_a_person(client, db_session, admin_user, roles, one_face):
    token_a = login(client, admin_user.email)
    enrolled = client.post(
        "/api/faces/enroll",
        data={"first_name": "Jane", "last_name": "Doe", "category": "EMPLOYEE"},
        files={"photo": ("face.jpg", _jpeg_bytes(2), "image/jpeg")},
        headers=auth_headers(token_a),
    ).json()
    person_id = enrolled["person"]["id"]

    _tenant_b, user_b = make_second_tenant_admin(db_session, roles)
    token_b = login(client, user_b.email)

    resp = client.delete(f"/api/faces/{person_id}", headers=auth_headers(token_b))
    assert resp.status_code == 404


def test_tenant_b_face_enrollment_does_not_flag_as_duplicate_of_tenant_a(client, db_session, admin_user, roles, one_face):
    """Duplicate-enrollment checking must be scoped per tenant — otherwise tenant A's
    biometric data would leak into tenant B's enrollment flow via a "already enrolled"
    rejection message naming tenant A's employee."""
    token_a = login(client, admin_user.email)
    client.post(
        "/api/faces/enroll",
        data={"first_name": "Jane", "last_name": "Doe", "category": "EMPLOYEE"},
        files={"photo": ("face.jpg", _jpeg_bytes(3), "image/jpeg")},
        headers=auth_headers(token_a),
    )

    _tenant_b, user_b = make_second_tenant_admin(db_session, roles)
    token_b = login(client, user_b.email)

    resp = client.post(
        "/api/faces/enroll",
        data={"first_name": "Someone", "last_name": "Else", "category": "EMPLOYEE"},
        files={"photo": ("face.jpg", _jpeg_bytes(3), "image/jpeg")},  # identical photo/embedding
        headers=auth_headers(token_b),
    )
    assert resp.json()["success"] is True
