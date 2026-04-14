from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── REST response bodies ───────────────────────────────────────────────────────

class MessageOut(BaseModel):
    id: int
    conversation_id: int    = Field(alias="conversationId")
    sender_id: int          = Field(alias="senderId")
    content: str
    message_type: str       = Field(alias="messageType")
    status: str
    created_at: datetime    = Field(alias="createdAt")
    delivered_at: Optional[datetime] = Field(default=None, alias="deliveredAt")
    read_at: Optional[datetime]      = Field(default=None, alias="readAt")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,   # allow snake_case internally; alias used in JSON
    )


class ConversationOut(BaseModel):
    id: int
    participant1_id: int            = Field(alias="participant1Id")
    participant2_id: int            = Field(alias="participant2Id")
    created_at: datetime            = Field(alias="createdAt")
    last_message_at: Optional[datetime] = Field(default=None, alias="lastMessageAt")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )