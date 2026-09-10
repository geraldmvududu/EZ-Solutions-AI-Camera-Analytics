from unittest.mock import MagicMock, patch

from app.models.event import EventSeverity
from app.services import push_service
from tests.conftest import auth_headers, login


def test_register_and_unregister_push_token(client, admin_user):
    token = login(client, admin_user.email)

    resp = client.post(
        "/api/push-tokens",
        json={"token": "ExponentPushToken[abc123]"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201

    # Registering the same token twice is idempotent, not an error.
    resp2 = client.post(
        "/api/push-tokens",
        json={"token": "ExponentPushToken[abc123]"},
        headers=auth_headers(token),
    )
    assert resp2.status_code == 201
    assert resp2.json()["detail"] == "Already registered"

    resp3 = client.request(
        "DELETE", "/api/push-tokens", json={"token": "ExponentPushToken[abc123]"}, headers=auth_headers(token)
    )
    assert resp3.status_code == 200


def test_push_token_requires_auth(client):
    resp = client.post("/api/push-tokens", json={"token": "ExponentPushToken[abc123]"})
    assert resp.status_code == 401


def test_send_push_notifications_filters_invalid_tokens():
    with patch("app.services.push_service.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value.json.return_value = {"data": []}
        mock_client.post.return_value.raise_for_status.return_value = None

        push_service.send_push_notifications(["not-a-real-token", "ExponentPushToken[valid]"], "Title", "Body")

        assert mock_client.post.called
        sent_payload = mock_client.post.call_args.kwargs["json"]
        assert len(sent_payload) == 1
        assert sent_payload[0]["to"] == "ExponentPushToken[valid]"


def test_send_push_notifications_noop_when_no_valid_tokens():
    with patch("app.services.push_service.httpx.Client") as mock_client_cls:
        push_service.send_push_notifications(["garbage"], "Title", "Body")
        mock_client_cls.assert_not_called()


def test_send_push_notifications_swallows_http_errors():
    import httpx

    with patch("app.services.push_service.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.side_effect = httpx.ConnectError("network down")

        # Must not raise — push delivery failures should never break the caller.
        push_service.send_push_notifications(["ExponentPushToken[valid]"], "Title", "Body")


def test_high_severity_alert_creates_notifications_and_sends_push(client, admin_user, db_session):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()

    client.post(
        "/api/push-tokens", json={"token": "ExponentPushToken[admintoken]"}, headers=auth_headers(token)
    )

    client.post(
        "/api/rules",
        json={"name": "Person rule", "conditions": {"event_type": "PERSON_DETECTED"}, "action_severity": "CRITICAL", "action_alert_type": "PERSON_MATCH"},
        headers=auth_headers(token),
    )

    with patch("app.services.notification_service.send_push_notifications") as mock_send:
        resp = client.post(
            "/api/events",
            json={
                "camera_id": cam["id"], "event_type": "PERSON_DETECTED", "severity": "INFO",
                "occurred_at": "2026-01-01T00:00:00Z", "event_metadata": {},
            },
            headers={"X-Internal-Token": "test-internal-token"},
        )
        assert resp.status_code == 201
        assert mock_send.called
        call_tokens = mock_send.call_args.args[0]
        assert "ExponentPushToken[admintoken]" in call_tokens

    notifications = client.get("/api/notifications", headers=auth_headers(token)).json()
    assert len(notifications) == 1
    assert notifications[0]["title"].startswith("CRITICAL")


def test_low_severity_alert_creates_notification_but_no_push(client, admin_user):
    token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(token)).json()
    client.post(
        "/api/rules",
        json={"name": "Low rule", "conditions": {"event_type": "MOTION_DETECTED"}, "action_severity": "LOW", "action_alert_type": "MOTION_MATCH"},
        headers=auth_headers(token),
    )

    with patch("app.services.notification_service.send_push_notifications") as mock_send:
        client.post(
            "/api/events",
            json={"camera_id": cam["id"], "event_type": "MOTION_DETECTED", "severity": "INFO", "occurred_at": "2026-01-01T00:00:00Z", "event_metadata": {}},
            headers={"X-Internal-Token": "test-internal-token"},
        )
        assert not mock_send.called

    notifications = client.get("/api/notifications", headers=auth_headers(token)).json()
    assert len(notifications) == 1


def test_viewer_does_not_receive_alert_notifications(client, admin_user, viewer_user):
    """Only users with manage_alerts (operator/admin/super_admin) get notified —
    matches the RBAC model, viewers are read-only."""
    admin_token = login(client, admin_user.email)
    cam = client.post("/api/cameras", json={"name": "Front Gate", "source_type": "SIMULATED"}, headers=auth_headers(admin_token)).json()
    client.post(
        "/api/rules",
        json={"name": "R", "conditions": {"event_type": "PERSON_DETECTED"}, "action_severity": "HIGH", "action_alert_type": "X"},
        headers=auth_headers(admin_token),
    )

    with patch("app.services.notification_service.send_push_notifications"):
        client.post(
            "/api/events",
            json={"camera_id": cam["id"], "event_type": "PERSON_DETECTED", "severity": "INFO", "occurred_at": "2026-01-01T00:00:00Z", "event_metadata": {}},
            headers={"X-Internal-Token": "test-internal-token"},
        )

    viewer_token = login(client, viewer_user.email)
    viewer_notifications = client.get("/api/notifications", headers=auth_headers(viewer_token)).json()
    assert viewer_notifications == []
