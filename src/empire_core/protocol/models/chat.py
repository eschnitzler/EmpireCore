"""
Alliance chat protocol models.

Commands:
- acm: Send/receive alliance chat messages
- acl: Get alliance chat log/history
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseRequest, BaseResponse, decode_chat_text, encode_chat_text

# =============================================================================
# ACM - Alliance Chat Message
# =============================================================================


class AllianceChatMessageRequest(BaseRequest):
    """
    Request to send an alliance chat message.

    Command: acm
    Payload: {"M": "encoded_message_text"}

    The message text must be encoded using encode_chat_text() before sending.
    """

    command = "acm"

    message: str = Field(alias="M")

    @classmethod
    def create(cls, text: str) -> "AllianceChatMessageRequest":
        """Create a chat message request with properly encoded text."""
        return cls(M=encode_chat_text(text))


class ChatMessageData(BaseModel):
    """
    The CM (Chat Message) data within an alliance chat response.

    Contains the actual message content and sender info.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    player_name: str = Field(alias="PN")
    message_text: str = Field(alias="MT")
    player_id: int = Field(alias="PID")

    @property
    def decoded_text(self) -> str:
        """Get the message text with special characters decoded."""
        return decode_chat_text(self.message_text)


class AllianceChatMessageResponse(BaseResponse):
    """
    Response containing an alliance chat message.

    Command: acm
    Payload: {"CM": {"PN": "player_name", "MT": "message_text", "PID": player_id}}

    This is received when:
    1. Another player sends a message to alliance chat
    2. Confirmation of our own sent message
    """

    command = "acm"

    chat_message: ChatMessageData = Field(alias="CM")

    @property
    def player_name(self) -> str:
        """Get the sender's player name."""
        return self.chat_message.player_name

    @property
    def message_text(self) -> str:
        """Get the raw message text (may contain encoded characters)."""
        return self.chat_message.message_text

    @property
    def decoded_text(self) -> str:
        """Get the message text with special characters decoded."""
        return self.chat_message.decoded_text

    @property
    def player_id(self) -> int:
        """Get the sender's player ID."""
        return self.chat_message.player_id


# =============================================================================
# ACL - Alliance Chat Log
# =============================================================================


class AllianceChatLogRequest(BaseRequest):
    """
    Request to get alliance chat history.

    Command: acl
    Payload: {} (empty)
    """

    command = "acl"


class ChatLogEntry(BaseModel):
    """A single entry in the chat log history."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    player_name: str = Field(alias="PN")
    message_text: str = Field(alias="MT")
    player_id: int = Field(alias="PID")
    timestamp: int | None = Field(alias="T", default=None)

    @property
    def decoded_text(self) -> str:
        """Get the message text with special characters decoded."""
        return decode_chat_text(self.message_text)


class AllianceChatLogResponse(BaseResponse):
    """
    Response containing alliance chat history.

    Command: acl
    Payload: {"CL": [{"PN": "name", "MT": "text", "PID": id, "T": timestamp}, ...]}
    """

    command = "acl"

    chat_log: list[ChatLogEntry] = Field(alias="CL", default_factory=list)


__all__ = [
    # ACM - Chat Message
    "AllianceChatMessageRequest",
    "AllianceChatMessageResponse",
    "ChatMessageData",
    # ACL - Chat Log
    "AllianceChatLogRequest",
    "AllianceChatLogResponse",
    "ChatLogEntry",
]
