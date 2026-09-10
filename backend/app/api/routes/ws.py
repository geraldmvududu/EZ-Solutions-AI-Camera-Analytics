import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.core.security import decode_access_token
from app.services.ws_manager import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/live")
async def live_events(websocket: WebSocket, token: str) -> None:
    """Real-time event/alert feed for the dashboard (section 25). Browsers cannot set
    Authorization headers on a WebSocket handshake, so the JWT access token is passed
    as a query parameter instead: wss://.../ws/live?token=<access_token>."""
    try:
        payload = decode_access_token(token)
        tenant_id = uuid.UUID(payload["tenant_id"])
    except (JWTError, KeyError, ValueError):
        await websocket.close(code=4401)
        return

    await manager.connect(tenant_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(tenant_id, websocket)
