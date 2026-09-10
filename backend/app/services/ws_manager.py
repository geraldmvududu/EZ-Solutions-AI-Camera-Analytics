import uuid
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """Broadcasts real-time events/alerts to connected dashboard/mobile clients, scoped
    per tenant so one tenant never receives another tenant's live feed (section 44)."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)

    async def connect(self, tenant_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[tenant_id].add(websocket)

    def disconnect(self, tenant_id: uuid.UUID, websocket: WebSocket) -> None:
        self._connections[tenant_id].discard(websocket)

    async def broadcast(self, tenant_id: uuid.UUID, message: dict) -> None:
        dead = []
        for ws in self._connections.get(tenant_id, set()):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(tenant_id, ws)


manager = ConnectionManager()
