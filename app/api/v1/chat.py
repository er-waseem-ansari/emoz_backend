import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, status
from sqlalchemy.orm import Session

from app.core.routing import AliasRoute
from app.core.security import get_current_user_id
from app.database import get_db
from app.schemas.chat import ConversationOut, MessageOut
from app.services.chat_service import ChatService
from app.websockets.chat_ws import chat_websocket_handler

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"], route_class=AliasRoute)


# ── WebSocket ──────────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Global real-time WebSocket endpoint — one connection per user session.
    All conversations are multiplexed over this single connection.

    Authentication uses first-message auth — the token is NOT in the URL.
    After connecting, the client must immediately send:
        {"type": "auth", "token": "<jwt>"}
    The connection is closed if no valid auth message arrives within 10 seconds.

    All subsequent events carry a conversation_id in their data payload.

    URL: ws://host/api/v1/chat/ws
    """
    await chat_websocket_handler(websocket=websocket)


# ── Conversations ──────────────────────────────────────────────────────────────

@router.get("/conversations", response_model=List[ConversationOut])
async def list_conversations(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """Return all conversations for the authenticated user, ordered by most recent message."""
    return ChatService.get_conversations(db, current_user_id)


# ── Messages ───────────────────────────────────────────────────────────────────

@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageOut])
async def get_messages(
    conversation_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    before_id: Optional[int] = Query(default=None, description="Cursor — fetch messages older than this ID"),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """
    Paginated message history for a conversation (newest first).
    Use before_id for infinite scroll: pass the oldest message ID you have
    to fetch the next page of older messages.
    """
    conversation = ChatService.get_conversation(db, conversation_id, current_user_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )

    return ChatService.get_messages(db, conversation_id, limit=limit, before_id=before_id)
