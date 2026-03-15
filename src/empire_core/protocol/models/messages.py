"""
Message and report protocol models.

Commands:
- sne: System notification event
- bsd: Battle/spy data
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

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


class BattleSpyDataResponse(BaseResponse):
    """
    Response containing battle or spy report data.

    Command: bsd
    """

    command = "bsd"

    message_id: int = Field(alias="MID", default=0)
    battle_data: dict[str, Any] = Field(alias="B", default_factory=dict)
    spy_data: list[Any] = Field(alias="S", default_factory=list)
    error_code: int = Field(alias="E", default=0)


__all__ = [
    "SystemNotificationEvent",
    "BattleSpyDataRequest",
    "BattleSpyDataResponse",
]
