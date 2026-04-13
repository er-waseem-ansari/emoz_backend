from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from jose import JWTError

from app.websockets.connection_manager import manager
from app.core.security import decode_token
from app.models.user import User


async def chat_websocket_handler(
    websocket: WebSocket,
    session_id: str,
    token: str,
    db: Session,
):
    # ── Step 1: Authenticate user from token ─────────────────
    try:
        payload = decode_token(token)

        # your auth_service stores user_id as "sub" in the token
        # we will confirm this in a second
        user_id = payload.get("sub")
        token_type = payload.get("type")

        # make sure it's an access token, not a refresh token
        if not user_id or token_type != "access":
            await websocket.close(code=4001, reason="Invalid token")
            return

    except JWTError:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # ── Step 2: Fetch user from DB ────────────────────────────
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        await websocket.close(code=4001, reason="User not found")
        return

    # ── Step 3: Accept and register connection ────────────────
    await manager.connect(websocket, session_id, str(user.id))

    await websocket.send_json({
        "type": "connected",
        "message": f"Welcome {user.phone}",
        "session_id": session_id,
    })

    # ── Step 4: Listen for incoming events ────────────────────
    try:
        while True:
            data = await websocket.receive_json()
            event_type = data.get("type")

            print(f"[WS] Event from {user.phone}: {event_type} → {data}")

            # echo back for now — real logic comes in next step
            await websocket.send_json({
                "type": "echo",
                "received": data,
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id, str(user.id))
        print(f"[WS] {user.phone} disconnected")