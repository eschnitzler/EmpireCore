"""Alliance action list and subscriber count.

Commands:
- all: Your alliance's action list (the log on the alliance overview)
- asc: How many of your alliance's members have a subscription
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_validator

from empire_core.enums import AllianceActionType
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, enum_or_none, readable_list
from empire_core.protocol.js import ClientInt

logger = logging.getLogger(__name__)


# =============================================================================
# ALL - Action list
# =============================================================================


class AllianceActionListRequest(BaseRequest):
    """
    Ask for your alliance's action list.

    Command: all
    Payload: {}

    Client: ``C2SAllianceActionListVO`` (bundle line 70469)
    """

    command = "all"


class AllianceActionListItem(BasePayload):
    """
    One entry of your alliance's action list.

    Client: ``AllianceActionListItemVO.parseActionListItem`` (bundle line 66338)
    """

    player_id: ClientInt = Field(alias="PID", default=0, description="The player the entry is about")
    player_name: str = Field(alias="PN", default="", description="The player's name")
    seconds_ago: ClientInt = Field(alias="MA", default=0, description="Seconds since the action")
    action: ClientInt = Field(alias="A", default=0, description="What happened, an AllianceActionType value")
    action_values: list[Any] = Field(
        alias="AV", default_factory=list, description="The action's details; their meaning depends on the action"
    )

    @field_validator("player_name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> Any:
        return value if isinstance(value, str) else ""

    @field_validator("action_values", mode="before")
    @classmethod
    def _values(cls, value: Any) -> Any:
        return value if isinstance(value, list) else []

    @property
    def action_type(self) -> AllianceActionType | None:
        """``action`` as an :class:`AllianceActionType`, None for an action the client does not define."""
        return enum_or_none(AllianceActionType, self.action)


class AllianceActionListResponse(BaseResponse):
    """
    Your alliance's action list.

    Command: all

    Client: ``ALLCommand.executeCommand`` (bundle line 121528) into
    ``CastleAllianceData.parse_ALL`` (bundle line 11565), which reads ``AL``
    with ``AllianceInfoVO.parseActionList`` (bundle line 25962) and reverses it
    """

    command = "all"

    alliance_id: ClientInt = Field(alias="AID", default=0, description="Your alliance's id")
    actions: list[AllianceActionListItem] = Field(
        alias="AL", default_factory=list, description="The entries, newest first"
    )

    @field_validator("actions", mode="before")
    @classmethod
    def _actions(cls, value: Any) -> Any:
        rows = readable_list(
            AllianceActionListItem, value, accept=lambda e: isinstance(e, dict), warn=logger, what="action list entries"
        )
        return rows[::-1]


# =============================================================================
# ASC - Subscriber count
# =============================================================================


class AllianceSubscriberCountRequest(BaseRequest):
    """
    Ask how many of your alliance's members have a subscription.

    Command: asc
    Payload: {}

    Client: ``C2SGetAllianceSubscriberCountEventVO`` (bundle line 120106)
    """

    command = "asc"


class AllianceSubscriberCountResponse(BaseResponse):
    """
    How many of your alliance's members have a subscription.

    Command: asc

    Client: ``ASCCommand.executeCommand`` (bundle line 128655) into
    ``SubscriptionData.parseASC`` (bundle line 120005)
    """

    command = "asc"

    subscriber_count: ClientInt = Field(
        alias="ASC", default=0, description="Members of your alliance with a subscription"
    )


__all__ = [
    "AllianceActionListRequest",
    "AllianceActionListItem",
    "AllianceActionListResponse",
    "AllianceSubscriberCountRequest",
    "AllianceSubscriberCountResponse",
]
