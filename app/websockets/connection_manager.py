from fastapi import WebSocket


class ConnectionManager:
    """
    Keeps track of all active WebSocket connections.

    Think of this like a dictionary:
        session_id → [list of connected users in that chat]
        user_id    → their WebSocket connection
    """

    def __init__(self):
        # session_id → list of WebSocket connections
        self.active_connections: dict[str, list[WebSocket]] = {}

        # user_id → WebSocket (so we can send directly to a user)
        self.user_connections: dict[str, WebSocket] = {}

    async def connect(
            self,
            websocket: WebSocket,
            session_id: str,
            user_id: str
    ):
        """Accept connection and register it."""
        await websocket.accept()

        # add to session room
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

        # map user_id → websocket
        self.user_connections[user_id] = websocket

        print(f"[WS] User {user_id} connected to session {session_id}")

    def disconnect(
            self,
            websocket: WebSocket,
            session_id: str,
            user_id: str
    ):
        """Remove connection on disconnect."""
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

        if user_id in self.user_connections:
            del self.user_connections[user_id]

        print(f"[WS] User {user_id} disconnected from session {session_id}")

    async def send_to_user(self, user_id: str, data: dict):
        """Send a message to a specific user if they are online."""
        websocket = self.user_connections.get(user_id)
        if websocket:
            await websocket.send_json(data)

    def is_user_online(self, user_id: str) -> bool:
        """Check if a user currently has an active connection."""
        return user_id in self.user_connections


# Single shared instance used across the entire app
manager = ConnectionManager()