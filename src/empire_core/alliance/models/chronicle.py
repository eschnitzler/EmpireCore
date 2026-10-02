"""Alliance chronicle and subscriber count.

Commands:
- all: Your alliance's chronicle, the log on the alliance overview
- asc: How many of your alliance's members have a subscription
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_validator

from empire_core.enums import AllianceChronicleAction
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, enum_or_none, readable_list
from empire_core.protocol.js import ClientInt

logger = logging.getLogger(__name__)


# =============================================================================
# ALL - Chronicle
# =============================================================================


class AllianceChronicleRequest(BaseRequest):
    """
    Ask for your alliance's chronicle.

    Command: all
    Payload: {}

    Client: ``C2SAllianceActionListVO`` (bundle line 70469)
    """

    command = "all"


class AllianceChronicleEntry(BasePayload):
    """
    One entry of your alliance's chronicle.

    Client: ``AllianceActionListItemVO.parseActionListItem`` (bundle line 66338)
    """

    player_id: ClientInt = Field(alias="PID", default=0, description="The player the entry is about")
    player_name: str | None = Field(alias="PN", default=None, description="The player's name")
    seconds_ago: ClientInt = Field(alias="MA", default=0, description="Seconds since the action")
    action: ClientInt = Field(alias="A", default=0, description="What happened, an AllianceChronicleAction value")
    action_values: list[Any] = Field(
        alias="AV", default_factory=list, description="The action's details; their meaning depends on the action"
    )

    @field_validator("player_name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> Any:
        return value if isinstance(value, str) else None

    @field_validator("action_values", mode="before")
    @classmethod
    def _values(cls, value: Any) -> Any:
        return value if isinstance(value, list) else []

    @property
    def action_type(self) -> AllianceChronicleAction | None:
        """``action`` as an :class:`AllianceChronicleAction`, None for an action the client does not define."""
        return enum_or_none(AllianceChronicleAction, self.action)


class AllianceChronicleResponse(BaseResponse):
    """
    Your alliance's chronicle.

    Command: all

    Client: ``ALLCommand.executeCommand`` (bundle line 121528) into
    ``CastleAllianceData.parse_ALL`` (bundle line 11565), which reads ``AL``
    with ``AllianceInfoVO.parseActionList`` (bundle line 25962) and reverses it
    """

    command = "all"

    alliance_id: ClientInt = Field(alias="AID", default=0, description="Your alliance's id")
    entries: list[AllianceChronicleEntry] = Field(
        alias="AL", default_factory=list, description="The entries, newest first"
    )

    @field_validator("entries", mode="before")
    @classmethod
    def _entries(cls, value: Any) -> Any:
        rows = readable_list(
            AllianceChronicleEntry, value, accept=lambda e: isinstance(e, dict), warn=logger, what="chronicle entries"
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
    ``SubscriptionData.parseASC`` (bundle line 120005); the treasury's
    subscriptions tab shows it against the member limit
    (``CastleAllianceDialogTreasurySubscriptions.updateSubscriberCount``, bundle line 70697)
    """

    command = "asc"

    subscriber_count: ClientInt = Field(
        alias="ASC", default=0, description="Members of your alliance with a subscription"
    )


__all__ = [
    "AllianceChronicleRequest",
    "AllianceChronicleEntry",
    "AllianceChronicleResponse",
    "AllianceSubscriberCountRequest",
    "AllianceSubscriberCountResponse",
]
