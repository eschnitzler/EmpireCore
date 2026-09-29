"""
Alliance chat protocol models.

Commands:
- acm: Send/receive alliance chat messages
- acl: Get alliance chat log/history
"""

from __future__ import annotations

from pydantic import Field

from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse
from empire_core.protocol.text import decode_json_text, encode_json_text

# =============================================================================
# ACM - Alliance Chat Message
# =============================================================================


class AllianceChatMessageRequest(BaseRequest):
    """
    Request to send an alliance chat message.

    Command: acm
    Payload: {"M": "encoded_message_text"}

    The message text must be encoded; :meth:`create` does it.

    Client: ``C2SAllianceChatVO`` (bundle line 66771)
    """

    command = "acm"

    message: str = Field(alias="M")

    @classmethod
    def create(cls, text: str) -> "AllianceChatMessageRequest":
        """A chat message request, the text encoded as ``C2SAllianceChatVO`` does after dropping carriage returns."""
        return cls(M=encode_json_text(text.replace("\r", "")))


class ChatMessageData(BasePayload):
    """
    The CM (Chat Message) data within an alliance chat response.

    Contains the actual message content and sender info.
    """

    player_name: str = Field(alias="PN")
    message_text: str = Field(alias="MT")
    player_id: int = Field(alias="PID")

    @property
    def decoded_text(self) -> str:
        """The message text decoded as ``ChatMessageVO.parseObj`` (bundle line 111316) decodes it."""
        return decode_json_text(self.message_text)


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

    chat_message: ChatMessageData | None = Field(alias="CM", default=None)

    @property
    def player_name(self) -> str:
        """Get the sender's player name."""
        return self.chat_message.player_name if self.chat_message else ""

    @property
    def message_text(self) -> str:
        """Get the raw message text (may contain encoded characters)."""
        return self.chat_message.message_text if self.chat_message else ""

    @property
    def decoded_text(self) -> str:
        """Get the message text with special characters decoded."""
        return self.chat_message.decoded_text if self.chat_message else ""

    @property
    def player_id(self) -> int:
        """Get the sender's player ID."""
        return self.chat_message.player_id if self.chat_message else 0


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


class ChatLogEntry(BasePayload):
    """A single entry in the chat log history."""

    player_name: str = Field(alias="PN")
    message_text: str = Field(alias="MT")
    player_id: int = Field(alias="PID")
    timestamp: int | None = Field(alias="T", default=None)

    @property
    def decoded_text(self) -> str:
        """The message text decoded as ``ChatMessageVO.parseObj`` (bundle line 111316) decodes it."""
        return decode_json_text(self.message_text)


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
