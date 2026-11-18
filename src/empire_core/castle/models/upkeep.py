"""
Pushes that keep the castle screen current: construction item expiry and the resource citizen.

Commands:
- nec: when the next construction item expires, a login section of ``gbd``, a push and a reply
- irc: the resource the citizen in your castle carries, a push and the reply to collecting it
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_validator

from empire_core.castle.models.objects import BuildingConstructionItems
from empire_core.gamedata import CollectableRows
from empire_core.protocol.base import BaseRequest, BaseResponse, TimedResponse, readable_list
from empire_core.protocol.js import ClientNumber, js_truthy

logger = logging.getLogger(__name__)


class GetConstructionItemExpiryRequest(BaseRequest):
    """
    Ask when the next of your construction items expires.

    Command: nec
    Payload: {}

    Client: ``C2SGetNextExpiringConstructionItemVO`` (bundle line 77698), sent by
    ``ConstructionItemData.onCIExpiration`` (bundle line 22993)
    """

    command = "nec"


class ConstructionItemExpiryResponse(TimedResponse):
    """
    When the next of your construction items expires and when one last expired, and the construction
    items on the joined castle's buildings when a push lists them.

    Command: nec, as a login section of ``gbd`` and a push.

    Client: ``NECCommand.executeCommand`` (split.js line 629754), which hands a truthy ``CI`` to the joined
    area's ``parseConstructionItems``; ``ConstructionItemData.parse_NEC`` (split.js line 120941) and
    ``hasNewExpiredItems`` (bundle line 22992)
    """

    command = "nec"

    next_expiry_seconds: ClientNumber = Field(
        validation_alias="NCRS",
        default=-1,
        description="Seconds until the next construction item expires when the values were read, -1 for none",
    )
    last_expired_at: ClientNumber = Field(
        validation_alias="LECT",
        default=-1,
        description="When a construction item last expired, the server's timestamp; -1 none",
    )
    placed_items: tuple[BuildingConstructionItems, ...] | None = Field(
        validation_alias="CI",
        default=None,
        description="The construction items on each of the joined castle's buildings; None when not sent",
    )

    @field_validator("placed_items", mode="before")
    @classmethod
    def _placed(cls, value: Any) -> Any:
        if not js_truthy(value) or not isinstance(value, list):
            return None
        return tuple(readable_list(BuildingConstructionItems, value, warn=logger, what="placed construction items"))

    def remaining_seconds(self, now: float | None = None) -> float | None:
        """Seconds until the next construction item expires, 0 at least; None when none will."""
        if self.next_expiry_seconds <= -1:
            return None
        return max(0.0, self.next_expiry_seconds - self._elapsed(now))


class CollectResourceCitizenRequest(BaseRequest):
    """
    Collect what the citizen walking in the joined castle carries.

    Command: irc
    Payload: {}

    Client: ``C2SIsoResourceCitizenVO`` (bundle line 63836), sent by
    ``IsoServerCommands.collectResourcePool`` (bundle line 63801)
    """

    command = "irc"


class ResourcePoolResponse(BaseResponse):
    """
    The resource the citizen walking in your castle carries, to collect by clicking it.

    Command: irc, a push and the reply to collecting the goods.

    Client: ``IRCCommand`` (bundle line 123090), ``CastleResourcePoolData.parseIRC`` (bundle line 139623), which
    keeps the first collectable of ``G`` and sets its amount to 1000 when ``EG`` is set. The client drops it
    when you join a castle (``JAACommand``, bundle line 130194), as ``client.state`` does, and also when the
    citizen carrying it is collected or leaves (``registerNewMovementAsOwner``, bundle line 139626), which
    the state does not follow, so it can outlast the citizen until the next ``irc``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "irc"

    goods: CollectableRows = Field(validation_alias="G", default=(), description="The goods the citizen carries")
    has_extra_goods: bool = Field(
        validation_alias="EG",
        default=False,
        description="Whether the client counts the goods as 1000, whatever G says",
    )

    @field_validator("has_extra_goods", mode="before")
    @classmethod
    def _extra(cls, value: Any) -> bool:
        return js_truthy(value)


__all__ = [
    "CollectResourceCitizenRequest",
    "ConstructionItemExpiryResponse",
    "GetConstructionItemExpiryRequest",
    "ResourcePoolResponse",
]
