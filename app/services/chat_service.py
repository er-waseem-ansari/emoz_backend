import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message

LOGGER = logging.getLogger(__name__)

# Maximum characters allowed in a single message
MAX_MESSAGE_LENGTH = 4096


class ChatService:

    @staticmethod
    def get_or_create_conversation(
        db: Session, user1_id: int, user2_id: int
    ) -> tuple[Conversation, bool]:
        """
        Returns the existing 1-to-1 conversation between two users, or creates one.
        participant IDs are always stored as (min, max) for uniqueness.
        Returns (conversation, is_new) — is_new is True only when the row was just created.
        """
        if user1_id == user2_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create a conversation with yourself.",
            )

        p1, p2 = sorted([user1_id, user2_id])

        try:
            conversation = db.query(Conversation).filter(
                Conversation.participant1_id == p1,
                Conversation.participant2_id == p2,
            ).first()

            if not conversation:
                conversation = Conversation(participant1_id=p1, participant2_id=p2)
                db.add(conversation)
                db.commit()
                db.refresh(conversation)
                return conversation, True

            return conversation, False

        except SQLAlchemyError as e:
            db.rollback()
            LOGGER.error(f"DB error in get_or_create_conversation: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error. Please try again.",
            )

    @staticmethod
    def get_conversation(db: Session, conversation_id: int, user_id: int) -> Optional[Conversation]:
        """Fetch a conversation only if the requesting user is a participant."""
        try:
            return db.query(Conversation).filter(
                Conversation.id == conversation_id,
                or_(
                    Conversation.participant1_id == user_id,
                    Conversation.participant2_id == user_id,
                ),
            ).first()
        except SQLAlchemyError as e:
            LOGGER.error(f"DB error in get_conversation: {e}")
            return None

    @staticmethod
    def get_conversations(db: Session, user_id: int) -> List[Conversation]:
        """Return conversations for a user that have at least one message, ordered by most recent."""
        try:
            return db.query(Conversation).filter(
                or_(
                    Conversation.participant1_id == user_id,
                    Conversation.participant2_id == user_id,
                ),
                Conversation.last_message_at.isnot(None),
            ).order_by(Conversation.last_message_at.desc()).all()
        except SQLAlchemyError as e:
            LOGGER.error(f"DB error in get_conversations: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error. Please try again.",
            )

    @staticmethod
    def save_message(
        db: Session,
        conversation_id: int,
        sender_id: int,
        content: str,
        message_type: str = "text",
    ) -> Message:
        """Persist a message and bump the conversation's last_message_at timestamp."""
        content = content.strip()
        if not content:
            raise ValueError("Message content cannot be empty.")
        if len(content) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message exceeds {MAX_MESSAGE_LENGTH} characters.")

        try:
            message = Message(
                conversation_id=conversation_id,
                sender_id=sender_id,
                content=content,
                message_type=message_type,
                status="sent",
            )
            db.add(message)

            db.query(Conversation).filter(Conversation.id == conversation_id).update(
                {"last_message_at": datetime.now(timezone.utc)},
                synchronize_session=False,
            )

            db.commit()
            db.refresh(message)
            return message

        except SQLAlchemyError as e:
            db.rollback()
            LOGGER.error(f"DB error in save_message: {e}")
            raise

    @staticmethod
    def mark_messages_delivered(db: Session, conversation_id: int, recipient_id: int) -> List[int]:
        """
        Mark all 'sent' messages in a conversation (not sent by recipient) as 'delivered'.
        Returns the IDs of messages that were updated so the sender can be notified.
        """
        try:
            messages = db.query(Message).filter(
                Message.conversation_id == conversation_id,
                Message.sender_id != recipient_id,
                Message.status == "sent",
            ).all()

            now = datetime.now(timezone.utc)
            ids = []
            for msg in messages:
                msg.status = "delivered"
                msg.delivered_at = now
                ids.append(msg.id)

            if ids:
                db.commit()

            return ids

        except SQLAlchemyError as e:
            db.rollback()
            LOGGER.error(f"DB error in mark_messages_delivered: {e}")
            return []

    @staticmethod
    def mark_messages_read(db: Session, conversation_id: int, reader_id: int) -> List[int]:
        """
        Mark all unread messages in a conversation (not sent by reader) as 'read'.
        Returns the IDs of messages updated so the sender can be notified.
        """
        try:
            messages = db.query(Message).filter(
                Message.conversation_id == conversation_id,
                Message.sender_id != reader_id,
                Message.status != "read",
            ).all()

            now = datetime.now(timezone.utc)
            ids = []
            for msg in messages:
                msg.status = "read"
                msg.read_at = now
                ids.append(msg.id)

            if ids:
                db.commit()

            return ids

        except SQLAlchemyError as e:
            db.rollback()
            LOGGER.error(f"DB error in mark_messages_read: {e}")
            return []

    @staticmethod
    def get_messages(
        db: Session,
        conversation_id: int,
        limit: int = 50,
        before_id: Optional[int] = None,
    ) -> List[Message]:
        """
        Cursor-based paginated message history (newest first).
        Pass before_id to fetch messages older than that message ID.
        """
        try:
            query = db.query(Message).filter(Message.conversation_id == conversation_id)
            if before_id:
                query = query.filter(Message.id < before_id)
            return query.order_by(Message.id.desc()).limit(min(limit, 100)).all()
        except SQLAlchemyError as e:
            LOGGER.error(f"DB error in get_messages: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error. Please try again.",
            )
