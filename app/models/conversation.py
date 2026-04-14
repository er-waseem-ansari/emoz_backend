from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class Conversation(Base):
    """
    Represents a 1-to-1 chat between two users.

    participant1_id is always the smaller user ID and participant2_id the larger —
    this enforces uniqueness without needing a composite check in code.
    """
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)

    # Always stored as (min_id, max_id) so there is exactly one row per pair
    participant1_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    participant2_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Updated every time a new message is saved — used to sort conversation list
    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("participant1_id", "participant2_id", name="uq_conversation_participants"),
    )
