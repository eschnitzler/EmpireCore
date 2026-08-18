"""
Message and report protocol models.

Commands:
- sne: System notification event
- bsd: Battle/spy data
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .base import BaseRequest, BaseResponse

# =============================================================================
# SNE - System Notification Event
# =============================================================================


class SystemNotificationEvent(BaseResponse):
    """
    System notification event (pushed by server).

    Command: sne
    """

    command = "sne"

    messages: list[list[Any]] = Field(alias="MSG", default_factory=list)


# =============================================================================
# BSD - Battle/Spy Data
# =============================================================================


class BattleSpyDataRequest(BaseRequest):
    """
    Request battle or spy report data.

    Command: bsd
    Payload: {
        "MID": message_id
    }
    """

    command = "bsd"

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


class BattleSpyDataResponse(BaseResponse):
    """
    Response containing battle or spy report data.

    Command: bsd
    """

    command = "bsd"

    message_id: int = Field(alias="MID", default=0)
    battle_data: dict[str, Any] = Field(alias="B", default_factory=dict)
    spy_data: list[Any] = Field(alias="S", default_factory=list)
    target: SpyCastleInfo | None = Field(alias="AI", default=None)


__all__ = [
    "SystemNotificationEvent",
    "BattleSpyDataRequest",
    "BattleSpyDataResponse",
]
