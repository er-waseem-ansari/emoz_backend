"""
WebSocket Chat Handler — Global (one connection per user session)
=================================================================
A single WebSocket is opened when the user logs in and stays open for the
entire app session. All conversations are multiplexed over this connection.

Authentication — first-message auth (token never in URL):
  1. Client connects
  2. Client immediately sends: {"type": "auth", "token": "<jwt>"}
  3. Server replies:           {"type": "connected", "data": {"userId": 10}}
  Connection is closed if no valid auth arrives within AUTH_TIMEOUT seconds.

Client → Server events (all after auth)
─────────────────────────────────────────────────────────────────────────────
  Send a message (existing conversation):
    {"type": "sendMessage",      "data": {"conversationId": 5, "content": "...", "messageType": "text"}}

  Send a message (first ever message — creates conversation lazily):
    {"type": "sendMessage",      "data": {"targetUserId": 42, "content": "...", "messageType": "text"}}

  User opened a conversation (marks pending messages as delivered):
    {"type": "conversationOpen", "data": {"conversationId": 5}}

  Typing indicators:
    {"type": "typingStart",      "data": {"conversationId": 5}}
    {"type": "typingStop",       "data": {"conversationId": 5}}

  Mark messages as read:
    {"type": "messageRead",      "data": {"conversationId": 5}}

  Heartbeat reply:
    {"type": "pong"}

Server → Client events
─────────────────────────────────────────────────────────────────────────────
  {"type": "connected",        "data": {"userId": 10}}
  {"type": "newMessage",       "data": {"conversationId": 5, "id": 42, "senderId": 3, ...}}
  {"type": "messageAck",       "data": {"conversationId": 5, "messageId": 42, "status": "sent"}}
  {"type": "messageDelivered", "data": {"conversationId": 5, "messageIds": [42]}}
  {"type": "messageRead",      "data": {"conversationId": 5, "messageIds": [42, 43]}}
  {"type": "typing",           "data": {"conversationId": 5, "userId": 3, "isTyping": true}}
  {"type": "ping"}
  {"type": "error",            "data": {"message": "..."}}
"""

import asyncio
import logging
import time
from typing import Dict, Optional

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import decode_token
from app.database import SessionLocal
from app.models.user import User
from app.services.chat_service import ChatService
from app.websockets.connection_manager import manager

LOGGER = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30   # seconds between server pings
HEARTBEAT_TIMEOUT  = 90   # seconds — close if no pong received in this window
AUTH_TIMEOUT       = 10   # seconds the client has to send the auth message


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _safe_close(websocket: WebSocket, code: int, reason: str) -> None:
    """Close the WebSocket, swallowing errors if the client already disconnected."""
    try:
        await websocket.close(code=code, reason=reason)
    except Exception:
        pass


# ── Heartbeat ──────────────────────────────────────────────────────────────────

async def _heartbeat_loop(websocket: WebSocket, state: dict) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            if time.monotonic() - state["last_pong"] > HEARTBEAT_TIMEOUT:
                LOGGER.warning("[WS] Heartbeat timeout — closing connection")
                await websocket.close(code=4008, reason="Heartbeat timeout")
                return
            await websocket.send_json({"type": "ping"})
        except Exception:
            return  # WebSocket already closed


# ── Authentication ─────────────────────────────────────────────────────────────

def _authenticate(token: str) -> Optional[int]:
    """Decode JWT and return user_id, or None on any failure."""
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError, TypeError):
        return None


# ── Conversation cache helpers ─────────────────────────────────────────────────
# Each WS session keeps a small in-memory dict:
#   conv_cache: {conversation_id: other_user_id}
# This avoids a DB round-trip on every event for the same conversation.

async def _resolve_other_user(
    websocket: WebSocket,
    conversation_id: int,
    user_id: int,
    conv_cache: Dict[int, int],
) -> Optional[int]:
    """
    Return the other participant's user_id for conversation_id.
    Fetches from DB on first access, then uses the cache.
    Sends an error frame and returns None if the conversation is inaccessible.
    """
    if conversation_id in conv_cache:
        return conv_cache[conversation_id]

    db = SessionLocal()
    try:
        conv = ChatService.get_conversation(db, conversation_id, user_id)
        if not conv:
            await websocket.send_json({"type": "error", "data": {
                "message": f"Conversation {conversation_id} not found or access denied.",
            }})
            return None
        other_user_id = (
            conv.participant2_id
            if conv.participant1_id == user_id
            else conv.participant1_id
        )
        conv_cache[conversation_id] = other_user_id
        return other_user_id
    finally:
        db.close()


def _get_conversation_id(data: dict) -> Optional[int]:
    cid = data.get("conversationId")
    return cid if isinstance(cid, int) else None


# ── Event handlers ─────────────────────────────────────────────────────────────

async def _handle_send_message(
    websocket: WebSocket,
    data: dict,
    user_id: int,
    conv_cache: Dict[int, int],
) -> None:
    conversation_id = _get_conversation_id(data)
    target_user_id = data.get("targetUserId")

    if conversation_id is None and not isinstance(target_user_id, int):
        await websocket.send_json({"type": "error", "data": {
            "message": "conversationId or targetUserId is required.",
        }})
        return

    is_new_conversation = False
    if conversation_id is None:
        # First message to this user — lazily create the conversation
        db = SessionLocal()
        try:
            conv, is_new_conversation = ChatService.get_or_create_conversation(db, user_id, target_user_id)
            conversation_id = conv.id
            other_user_id = (
                conv.participant2_id
                if conv.participant1_id == user_id
                else conv.participant1_id
            )
            conv_cache[conversation_id] = other_user_id
        except HTTPException as e:
            await websocket.send_json({"type": "error", "data": {"message": e.detail}})
            return
        except SQLAlchemyError:
            await websocket.send_json({"type": "error", "data": {
                "message": "Failed to create conversation. Please try again.",
            }})
            return
        finally:
            db.close()
    else:
        other_user_id = await _resolve_other_user(websocket, conversation_id, user_id, conv_cache)
        if other_user_id is None:
            return

    content = str(data.get("content", "")).strip()
    message_type = str(data.get("messageType", "text"))

    if not content:
        await websocket.send_json({"type": "error", "data": {"message": "Content cannot be empty."}})
        return
    if len(content) > 4096:
        await websocket.send_json({"type": "error", "data": {"message": "Message too long (max 4096 chars)."}})
        return
    if message_type not in ("text", "image", "file"):
        message_type = "text"

    db = SessionLocal()
    try:
        message = ChatService.save_message(db, conversation_id, user_id, content, message_type)

        message_payload = {
            "conversationId": conversation_id,
            "id": message.id,
            "senderId": message.sender_id,
            "content": message.content,
            "messageType": message.message_type,
            "status": message.status,
            "createdAt": message.created_at.isoformat(),
        }

        # Acknowledge to sender
        await websocket.send_json({"type": "messageAck", "data": {
            "conversationId": conversation_id,
            "messageId": message.id,
            "status": "sent",
        }})

        # Deliver to recipient if online
        if manager.is_user_online(other_user_id):
            # If this is a brand-new conversation, notify the recipient first so they
            # can insert the inbox row before the message arrives.
            if is_new_conversation:
                sender = db.query(User).filter(User.id == user_id).first()
                await manager.send_to_user(other_user_id, {
                    "type": "newConversation",
                    "data": {
                        "id": conversation_id,
                        "participant1Id": min(user_id, other_user_id),
                        "participant2Id": max(user_id, other_user_id),
                        "createdAt": message.created_at.isoformat(),
                        "lastMessageAt": message.created_at.isoformat(),
                        "otherUser": {
                            "id": user_id,
                            "username": sender.username if sender else None,
                            "phoneNumber": sender.phone if sender else None,
                            "profilePictureUrl": sender.profile_picture_url if sender else None,
                        },
                    },
                })

            await manager.send_to_user(other_user_id, {
                "type": "newMessage",
                "data": message_payload,
            })
            delivered_ids = ChatService.mark_messages_delivered(db, conversation_id, other_user_id)
            if delivered_ids:
                await websocket.send_json({"type": "messageDelivered", "data": {
                    "conversationId": conversation_id,
                    "messageIds": delivered_ids,
                }})

    except ValueError as e:
        await websocket.send_json({"type": "error", "data": {"message": str(e)}})
    except SQLAlchemyError:
        await websocket.send_json({"type": "error", "data": {"message": "Failed to send message. Please try again."}})
    finally:
        db.close()


async def _handle_conversation_open(
    websocket: WebSocket,
    data: dict,
    user_id: int,
    conv_cache: Dict[int, int],
) -> None:
    """
    Called when the user navigates into a conversation screen.
    Marks all undelivered messages as 'delivered' and notifies the sender.
    """
    conversation_id = _get_conversation_id(data)
    if conversation_id is None:
        return

    other_user_id = await _resolve_other_user(websocket, conversation_id, user_id, conv_cache)
    if other_user_id is None:
        return

    db = SessionLocal()
    try:
        delivered_ids = ChatService.mark_messages_delivered(db, conversation_id, user_id)
        if delivered_ids and manager.is_user_online(other_user_id):
            await manager.send_to_user(other_user_id, {
                "type": "messageDelivered",
                "data": {
                    "conversationId": conversation_id,
                    "messageIds": delivered_ids,
                },
            })
    except SQLAlchemyError:
        pass  # delivery receipts are best-effort
    finally:
        db.close()


async def _handle_typing(
    websocket: WebSocket,
    is_typing: bool,
    data: dict,
    user_id: int,
    conv_cache: Dict[int, int],
) -> None:
    conversation_id = _get_conversation_id(data)
    if conversation_id is None:
        return

    other_user_id = await _resolve_other_user(websocket, conversation_id, user_id, conv_cache)
    if other_user_id is None:
        return

    if manager.is_user_online(other_user_id):
        await manager.send_to_user(other_user_id, {
            "type": "typing",
            "data": {"conversationId": conversation_id, "userId": user_id, "isTyping": is_typing},
        })


async def _handle_message_read(
    websocket: WebSocket,
    data: dict,
    user_id: int,
    conv_cache: Dict[int, int],
) -> None:
    conversation_id = _get_conversation_id(data)
    if conversation_id is None:
        return

    other_user_id = await _resolve_other_user(websocket, conversation_id, user_id, conv_cache)
    if other_user_id is None:
        return

    db = SessionLocal()
    try:
        read_ids = ChatService.mark_messages_read(db, conversation_id, user_id)
        if read_ids and manager.is_user_online(other_user_id):
            await manager.send_to_user(other_user_id, {
                "type": "messageRead",
                "data": {"conversationId": conversation_id, "messageIds": read_ids},
            })
    except SQLAlchemyError:
        pass  # read receipts are best-effort
    finally:
        db.close()


# ── Main handler ───────────────────────────────────────────────────────────────

async def chat_websocket_handler(websocket: WebSocket) -> None:
    # ── Step 1: Accept the raw TCP upgrade ───────────────────────────────────
    # Token is NOT in the URL — URLs appear in access logs, proxy logs, and CDN
    # logs in plain text. The client sends it as the first WebSocket message.
    try:
        await websocket.accept()
    except Exception:
        return  # TCP handshake failed — nothing to clean up

    # ── Step 2: Wait for the auth message ────────────────────────────────────
    try:
        first_message = await asyncio.wait_for(
            websocket.receive_json(), timeout=AUTH_TIMEOUT
        )
    except asyncio.TimeoutError:
        await _safe_close(websocket, code=4001, reason="Authentication timeout")
        return
    except Exception:
        await _safe_close(websocket, code=4001, reason="Authentication required")
        return

    if first_message.get("type") != "auth" or not first_message.get("token"):
        await _safe_close(websocket, code=4001, reason="Authentication required")
        return

    # ── Step 3: Validate JWT ──────────────────────────────────────────────────
    user_id = _authenticate(first_message["token"])
    if not user_id:
        await _safe_close(websocket, code=4001, reason="Unauthorized")
        return

    # ── Step 4: Verify user exists and is active ──────────────────────────────
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
        if not user:
            await _safe_close(websocket, code=4001, reason="User not found or inactive")
            return
    except SQLAlchemyError:
        LOGGER.exception("[WS] DB error during auth for user_id=%s", user_id)
        await _safe_close(websocket, code=1011, reason="Internal server error")
        return
    finally:
        db.close()

    # ── Step 5: Register the connection ───────────────────────────────────────
    manager.connect(websocket, user_id)

    # ── Step 6: Start heartbeat ────────────────────────────────────────────────
    state = {"last_pong": time.monotonic()}
    heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket, state))

    # Per-session cache: conversation_id → other_user_id
    conv_cache: Dict[int, int] = {}

    # ── Step 7: Event loop ────────────────────────────────────────────────────
    # "connected" is sent inside the try so that if it fails (client dropped),
    # the finally block still runs and cleans up the connection registration.
    try:
        await websocket.send_json({"type": "connected", "data": {"userId": user_id}})

        while True:
            try:
                event = await websocket.receive_json()
            except ValueError:
                await websocket.send_json({"type": "error", "data": {"message": "Invalid JSON."}})
                continue

            event_type = event.get("type")
            data = event.get("data", {})

            if event_type == "sendMessage":
                await _handle_send_message(websocket, data, user_id, conv_cache)

            elif event_type == "conversationOpen":
                await _handle_conversation_open(websocket, data, user_id, conv_cache)

            elif event_type == "typingStart":
                await _handle_typing(websocket, True, data, user_id, conv_cache)

            elif event_type == "typingStop":
                await _handle_typing(websocket, False, data, user_id, conv_cache)

            elif event_type == "messageRead":
                await _handle_message_read(websocket, data, user_id, conv_cache)

            elif event_type == "pong":
                state["last_pong"] = time.monotonic()

            else:
                await websocket.send_json({"type": "error", "data": {
                    "message": f"Unknown event type: '{event_type}'",
                }})

    except WebSocketDisconnect:
        LOGGER.info(f"[WS] User {user_id} disconnected")

    except Exception as e:
        LOGGER.error(f"[WS] Unexpected error for user {user_id}: {e}", exc_info=True)

    finally:
        heartbeat_task.cancel()
        manager.disconnect(websocket, user_id)
