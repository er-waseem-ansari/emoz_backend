from sqlalchemy import Column, Integer, ForeignKey, DateTime, String, Text, Index
from sqlalchemy.sql import func

from app.database import Base


class Message(Base):
    """
    A single chat message inside a conversation.

    status lifecycle:  sent → delivered → read
      - sent      : saved to DB, recipient not yet received it over WebSocket
      - delivered : recipient's WebSocket connection received it
      - read      : recipient explicitly sent a read_receipt event
    """
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    sender_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    content = Column(Text, nullable=False)
    message_type = Column(String(20), default="text", nullable=False)  # text | image | file
    status = Column(String(20), default="sent", nullable=False)        # sent | delivered | read

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Efficient pagination: fetch last N messages in a conversation ordered by time
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
    )
