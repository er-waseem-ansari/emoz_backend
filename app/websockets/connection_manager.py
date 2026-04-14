import logging
from typing import Dict, List

from fastapi import WebSocket

LOGGER = logging.getLogger(__name__)


class ConnectionManager:
    """
    Tracks all active WebSocket connections in memory, keyed by user_id.

    One user may have multiple connections (multiple devices/tabs). All
    conversation events are routed by user_id — there is no per-conversation
    room concept at the network layer.

    ⚠ Scale note: this is a single-process, in-memory store. For multi-server
    deployments (e.g. behind a load balancer) replace send_to_user with a
    Redis Pub/Sub fan-out while keeping this interface identical.
    """

    def __init__(self):
        # user_id → list of active WebSocket connections (one per device/tab)
        self.user_connections: Dict[int, List[WebSocket]] = {}

    # ── Connection lifecycle ───────────────────────────────────────────────────

    def connect(self, websocket: WebSocket, user_id: int) -> None:
        """Register a new authenticated connection for a user."""
        self.user_connections.setdefault(user_id, []).append(websocket)
        count = len(self.user_connections[user_id])
        LOGGER.info(f"[WS] User {user_id} connected ({count} active connection(s))")

    def disconnect(self, websocket: WebSocket, user_id: int) -> None:
        """Remove a specific WebSocket from the user's connection list."""
        connections = self.user_connections.get(user_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.user_connections.pop(user_id, None)
        LOGGER.info(f"[WS] User {user_id} disconnected")

    # ── Sending ────────────────────────────────────────────────────────────────

    async def send_to_user(self, user_id: int, data: dict) -> None:
        """
        Send a JSON payload to all active connections of a user.
        Dead connections are silently removed.
        """
        connections = self.user_connections.get(user_id, [])
        dead: List[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            connections.remove(ws)
        if not connections:
            self.user_connections.pop(user_id, None)

    # ── Presence ───────────────────────────────────────────────────────────────

    def is_user_online(self, user_id: int) -> bool:
        return bool(self.user_connections.get(user_id))


# Single shared instance used across the entire app process
manager = ConnectionManager()
