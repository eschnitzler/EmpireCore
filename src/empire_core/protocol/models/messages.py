"""
Message and report protocol models.

Commands:
- sne: System notification event
- bsd: Spy report (the client's S2C_SPY_LOG_DETAIL)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .base import BasePayload, BaseRequest, BaseResponse
from .commanders import Castellan

# =============================================================================
# SNE - System Notification Event
# =============================================================================


_MESSAGE_ROW = (
    "message_id",
    "message_type",
    "header",
    "sender_name",
    "sender_id",
    "seconds_since_sent",
    "is_read",
    "is_archived",
    "is_forwarded",
)


class MessageInfo(BasePayload):
    """One mailbox message: an entry of ``sne``'s ``MSG``.

    Client: ``AMessageVO.loadFromParamArray`` (bundle line 3808), reached through
    ``CastleMessageData.parse_SNE`` and ``CastleMessageFactory.parseMessage`` (bundle line 135102).
    """

    message_id: int = Field(description="Message id, row[0]")
    message_type: int = Field(description="MessageConst.MESSAGE_TYPE_* value, row[1]")
    header: str = Field(
        default="",
        description="row[2]; its layout depends on message_type, each message class parses it in parseMessageHeader",
    )
    sender_name: str = Field(default="", description="row[3]")
    sender_id: int = Field(default=-1, description="Sender's player id, row[4]")
    seconds_since_sent: int = Field(default=0, description="row[5]")
    is_read: bool = Field(default=False, description="1 == row[6]")
    is_archived: bool = Field(default=False, description="1 == row[7]")
    is_forwarded: bool = Field(default=False, description="1 == row[8]")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list) and len(data) >= 2:
            return dict(zip(_MESSAGE_ROW, data, strict=False))
        return data

    @field_validator("header", "sender_name", mode="before")
    @classmethod
    def _no_text(cls, value: Any) -> Any:
        return "" if value is None else value

    @field_validator("is_read", "is_archived", "is_forwarded", mode="before")
    @classmethod
    def _one_flag(cls, value: Any) -> bool:
        try:
            return int(value) == 1
        except (TypeError, ValueError):
            return False


class SystemNotificationEvent(BaseResponse):
    """
    New mailbox messages, pushed by the server.

    Command: sne

    Client: ``SNECommand.exec`` (bundle line 125499), ``CastleMessageData.parse_SNE`` (bundle line 134961).
    """

    command = "sne"

    messages: list[MessageInfo] = Field(alias="MSG", default_factory=list, description="The new messages")


# =============================================================================
# BSD - Spy Log Detail
# =============================================================================


class BattleSpyDataRequest(BaseRequest):
    """
    Request a spy report.

    Command: bsd
    Payload: {
        "MID": message_id
    }
    """

    command = "bsd"

    message_id: int = Field(alias="MID")


class ForwardSpyLogRequest(BaseRequest):
    """
    Forward a spy report to other players.

    Command: mfs
    Payload: {"PID": [player_id, ...], "MID": message_id}
    """

    command = "mfs"

    player_ids: list[int] = Field(alias="PID")
    message_id: int = Field(alias="MID")


class SpyCastleInfo(BaseModel):
    """The spied castle, from the report's ``AI`` block.

    The coordinates are the only way to tell whose report this is: ``sne``
    carries no correlation id, so a mission has to check that the report it
    fetched describes the castle it asked about.
    """

    castle_name: str = Field(alias="N", default="")
    x: int = Field(alias="X", default=-1)
    y: int = Field(alias="Y", default=-1)
    kingdom: int = Field(alias="K", default=-1)
    area_type: int = Field(alias="AT", default=-1)

    # Fortifications, read by parseAreaInfoBattleLog in the client. -1 marks a
    # level the report did not carry, which is not the same as level 0.
    keep_level: int = Field(alias="KL", default=-1)
    wall_level: int = Field(alias="WL", default=-1)
    gate_level: int = Field(alias="GL", default=-1)
    tower_level: int = Field(alias="TL", default=-1)
    moat_level: int = Field(alias="ML", default=-1)


class BattleSpyDataResponse(BaseResponse):
    """
    A spy report.

    Command: bsd

    Client: ``BSDCommand.executeCommand`` (bundle line 125223), ``CastleSpyLogVO.parseSpyLog``
    (bundle line 60579), ``CastleSpyArmyInfoVO.parseArmyInfo`` (bundle line 30699).
    """

    command = "bsd"

    message_id: int = Field(alias="MID", default=0)
    defending_castellan: Castellan | None = Field(
        alias="B",
        default=None,
        description="The castellan defending the spied castle; the client reads it without its equipment. "
        "None when missing or unreadable",
    )
    spy_data: list[list[list[int]]] = Field(
        alias="S",
        default_factory=list,
        description="Spied defenders as [wod_id, amount] pairs per position: left, middle, right, keep, "
        "stronghold, support, then an optional reserve",
    )
    target: SpyCastleInfo | None = Field(alias="AI", default=None)

    @field_validator("defending_castellan", mode="before")
    @classmethod
    def _readable_castellan(cls, value: Any) -> Any:
        if not value:
            return None
        try:
            return Castellan.model_validate(value)
        except ValidationError:
            return None

    @field_validator("spy_data", mode="before")
    @classmethod
    def _wod_amount_pairs(cls, value: Any) -> Any:
        """Client: ``AUnitInventory.fillFromWodAmountArray`` (bundle line 42572) skips entries that are not arrays."""
        if not isinstance(value, list):
            return value
        return [
            [pair for pair in position if isinstance(pair, list)] if isinstance(position, list) else []
            for position in value
        ]


__all__ = [
    "ForwardSpyLogRequest",
    "MessageInfo",
    "SystemNotificationEvent",
    "BattleSpyDataRequest",
    "BattleSpyDataResponse",
]
