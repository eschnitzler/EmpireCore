"""
Alliance chat protocol models.

Commands:
- acm: Send/receive alliance chat messages
- acl: Get alliance chat log/history
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_validator

from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, js_number_or_none
from empire_core.protocol.text import decode_json_text, encode_json_text

logger = logging.getLogger(__name__)

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
        return cls(message=encode_json_text(text.replace("\r", "")))


class ChatMessageData(BasePayload):
    """
    One alliance chat message: an acm push's ``CM`` block, or one entry of an acl reply's ``CM`` list.

    Client: ``ChatMessageVO.parseObj`` (bundle line 111316), reached through
    ``CastleChatData.getParsedMessage`` (bundle line 111301).
    """

    player_id: ClientInt = Field(alias="PID", default=0, description="The sender's player id")
    player_name: str = Field(alias="PN", default="", description="The sender's name")
    message_text: str = Field(alias="MT", default="", description="The message text as sent, still encoded")
    age_seconds: int | float | None = Field(
        alias="MA",
        default=None,
        description="Seconds since the message was sent; None when the reply has no number for it",
    )

    @field_validator("player_name", "message_text", mode="before")
    @classmethod
    def _missing_text_is_empty(cls, value: Any) -> Any:
        return "" if value is None else value

    @field_validator("age_seconds", mode="before")
    @classmethod
    def _age_as_number(cls, value: Any) -> Any:
        # parseObj dates the message MA * 1000 ms before now; a JSON null multiplies as 0
        return 0 if value is None else js_number_or_none(value)

    @property
    def decoded_text(self) -> str:
        """The message text decoded as ``ChatMessageVO.parseObj`` (bundle line 111316) decodes it."""
        return decode_json_text(self.message_text)


class AllianceChatMessageResponse(BaseResponse):
    """
    Response containing an alliance chat message.

    Command: acm
    Payload: {"CM": {"PID": player_id, "PN": "player_name", "MT": "message_text", "MA": age_seconds}}

    This is received when:
    1. Another player sends a message to alliance chat
    2. Confirmation of our own sent message

    Client: ``ACMCommand.executeCommand`` (bundle line 121316) passes ``CM`` to
    ``CastleChatData.parseSingleMessage`` (bundle line 111288).
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

    The client never sends acl: it has no C2S VO for it, and the only
    ``C2S_ALLIANCE_CHAT_LOG`` is an unused constant in ggs.dll (line 18958).
    It only reads the acl the server sends, so this payload is not taken
    from the client. A live server answers it with the ``CM`` list, and
    also pushes one acl at login.
    """

    command = "acl"


class AllianceChatLogResponse(BaseResponse):
    """
    Response containing alliance chat history.

    Command: acl
    Payload: {"CM": [{"PID": player_id, "PN": "player_name", "MT": "message_text", "MA": age_seconds}, ...]}

    Client: ``ACLCommand.executeCommand`` (bundle line 121301) passes the reply to
    ``CastleChatData.parseHistory`` (bundle line 111294), which reads each
    entry of ``CM`` as a ``ChatMessageVO``.
    """

    command = "acl"

    chat_log: list[ChatMessageData] = Field(
        alias="CM", default_factory=list, description="The messages, in the order the reply lists them"
    )

    @field_validator("chat_log", mode="before")
    @classmethod
    def _messages(cls, value: Any) -> Any:
        return readable_list(
            ChatMessageData,
            value,
            accept=lambda entry: isinstance(entry, dict),
            warn=logger,
            what="alliance chat messages",
        )


__all__ = [
    # ACM - Chat Message
    "AllianceChatMessageRequest",
    "AllianceChatMessageResponse",
    "ChatMessageData",
    # ACL - Chat Log
    "AllianceChatLogRequest",
    "AllianceChatLogResponse",
]
