from fastapi import APIRouter, WebSocket, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.websockets.chat_ws import chat_websocket_handler

router = APIRouter()


@router.websocket("/ws/chat/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: str,
    db: Session = Depends(get_db),
):
    await chat_websocket_handler(
        websocket=websocket,
        session_id=session_id,
        token=token,
        db=db,
    )