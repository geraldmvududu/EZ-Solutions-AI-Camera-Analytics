"""Real push notification delivery via Expo's push notification service (section 39).

This deliberately does NOT talk to Firebase Cloud Messaging or APNs directly — Expo's
push service (https://docs.expo.dev/push-notifications/overview/) sits in front of
both and is available to any app built with Expo without the deploying organization
provisioning its own Firebase project or Apple Developer account. That's what makes
this feature buildable and testable in this environment.

Delivery is fire-and-forget from the caller's perspective: failures are logged, not
raised, so a push-notification outage never blocks alert creation.
"""

import logging

import httpx

logger = logging.getLogger("app.push_service")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
BATCH_SIZE = 100  # Expo's documented maximum per request


def _looks_like_expo_token(token: str) -> bool:
    return token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")


def send_push_notifications(tokens: list[str], title: str, body: str, data: dict | None = None) -> None:
    valid_tokens = [t for t in tokens if _looks_like_expo_token(t)]
    if not valid_tokens:
        return

    messages = [
        {"to": token, "title": title, "body": body, "data": data or {}, "sound": "default", "priority": "high"}
        for token in valid_tokens
    ]

    try:
        with httpx.Client(timeout=10.0) as client:
            for i in range(0, len(messages), BATCH_SIZE):
                batch = messages[i : i + BATCH_SIZE]
                resp = client.post(EXPO_PUSH_URL, json=batch, headers={"Content-Type": "application/json"})
                resp.raise_for_status()
                _log_receipts(resp.json())
    except httpx.HTTPError as exc:
        logger.warning("Push notification delivery failed: %s", exc)


def _log_receipts(response_body: dict) -> None:
    for entry in response_body.get("data", []):
        if entry.get("status") == "error":
            logger.warning("Expo push rejected a message: %s", entry.get("message"))
