"""
Pushes that keep the castle screen current: construction item expiry and the resource citizen.

Commands:
- nec: when the next construction item expires, a login section of ``gbd`` and a push
- irc: the resource the citizen in your castle carries, a push
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, field_validator

from empire_core.gamedata import CollectableRows
from empire_core.protocol.base import BaseResponse, TimedResponse
from empire_core.protocol.js import ClientNumber, js_truthy


class ConstructionItemExpiryResponse(TimedResponse):
    """
    When the next of your construction items expires, and when one last expired.

    The push's ``CI`` (the joined castle's construction items) is not read here.

    Command: nec, as a login section of ``gbd`` and a push.

    Client: ``NECCommand`` (bundle line 123294), ``ConstructionItemData.parse_NEC`` and
    ``hasNewExpiredItems`` (bundle lines 22976, 22992)
    """

    command = "nec"

    next_expiry_seconds: ClientNumber = Field(
        alias="NCRS",
        default=-1,
        description="Seconds until the next construction item expires when the values were read, -1 for none",
    )
    last_expired_at: ClientNumber = Field(
        alias="LECT", default=-1, description="When a construction item last expired, the server's timestamp; -1 none"
    )

    def remaining_seconds(self, now: float | None = None) -> float | None:
        """Seconds until the next construction item expires, 0 at least; None when none will."""
        if self.next_expiry_seconds <= -1:
            return None
        return max(0.0, self.next_expiry_seconds - self._elapsed(now))


class ResourcePoolResponse(BaseResponse):
    """
    The resource the citizen walking in your castle carries, to collect by clicking it.

    Command: irc, a push.

    Client: ``IRCCommand`` (bundle line 123090), ``CastleResourcePoolData.parseIRC`` (bundle line 139623), which
    keeps the first collectable of ``G`` and sets its amount to 1000 when ``EG`` is set. The client drops it
    when you join a castle (``JAACommand``, bundle line 130194), as ``client.state`` does, and also when the
    citizen carrying it is collected or leaves (``registerNewMovementAsOwner``, bundle line 139626), which
    the state does not follow, so it can outlast the citizen until the next ``irc``.
    """

    model_config = ConfigDict(frozen=True)

    command = "irc"

    goods: CollectableRows = Field(alias="G", default=(), description="The goods the citizen carries")
    has_extra_goods: bool = Field(
        alias="EG", default=False, description="Whether the client counts the goods as 1000, whatever G says"
    )

    @field_validator("has_extra_goods", mode="before")
    @classmethod
    def _extra(cls, value: Any) -> bool:
        return js_truthy(value)


__all__ = ["ConstructionItemExpiryResponse", "ResourcePoolResponse"]
