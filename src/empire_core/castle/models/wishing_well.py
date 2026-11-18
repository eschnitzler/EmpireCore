"""
The ruby wishing well.

Commands:
- rww: start, finish, collect, upgrade or read the wishing well; its level and time, a login section of ``gbd``
  and the reply
"""

from __future__ import annotations

from pydantic import Field, field_serializer

from empire_core.enums import WishingWellOption
from empire_core.protocol.base import BaseRequest, TimedResponse
from empire_core.protocol.js import ClientInt, ClientNumber, js_int, js_int32

_MAX_SKIP_RUBIES = 1999


def wishing_well_skip_rubies(seconds: int) -> int:
    """
    The rubies finishing the running wishing well costs with ``seconds`` left: half a ruby a whole minute,
    1999 at most.

    Client: ``WishingWellConst.calculateWishingWellSkipCost`` (ggs.dll.js line 237), shown by
    ``RubyWishingWellDialog.updateArrow`` (split.js line 266252)
    """
    return js_int(max(0.0, min(0.5 * js_int32(seconds / 60), _MAX_SKIP_RUBIES)))


class WishingWellRequest(BaseRequest):
    """
    Act on the ruby wishing well in your main castle.

    Command: rww
    Payload: {"PWR": 0 or 1, "_PO": -1, "WOP": option}

    Keys follow the client's order: the constructor sets PWR and _PO before WOP.

    Client: ``C2SWishingWellCommandVO`` (split.js line 110368)
    """

    command = "rww"

    pay_with_rubies: bool = Field(
        validation_alias="PWR", default=False, description="Whether the resources an upgrade lacks are paid in rubies"
    )
    private_offer_id: int = Field(
        validation_alias="_PO", default=-1, description="The private offer the payment uses, -1 for none"
    )
    option: WishingWellOption = Field(validation_alias="WOP", description="What to do")

    @field_serializer("pay_with_rubies")
    def _flag(self, value: bool) -> int:
        return 1 if value else 0


class WishingWellResponse(TimedResponse):
    """
    The ruby wishing well: its level and whether it can be started, runs, or waits to be collected.

    Command: rww, as a login section of ``gbd`` and a successful reply; a reply refused for lack of
    resources is not read.

    Client: ``RWWCommand`` (split.js line 641960), ``CastleRubyWishingWellData.parse_RWW`` (split.js line 110466),
    ``isReadyToStart``, ``isReadyToCollect``, ``isRunning`` and ``getRemainingSecondsCalculated``
    (split.js lines 110440-110504)
    """

    command = "rww"

    level: ClientInt = Field(validation_alias="L", default=-1, description="The wishing well's level, -1 for none")
    seconds: ClientNumber = Field(
        validation_alias="RT",
        default=-1,
        description="Seconds left when the values were read: -1 ready to start, 0 ready to collect",
    )

    @property
    def is_ready_to_start(self) -> bool:
        """Whether the wishing well can be started, as last read."""
        return self.seconds == -1

    @property
    def is_ready_to_collect(self) -> bool:
        """Whether the wishing well waits to be collected, as last read."""
        return self.seconds == 0

    @property
    def is_running(self) -> bool:
        """Whether the wishing well runs, as last read."""
        return not (self.is_ready_to_start or self.is_ready_to_collect)

    def remaining_seconds(self, now: float | None = None) -> int:
        """Whole seconds until it is done, 0 at least."""
        return int(max(0.0, self.seconds - self._elapsed(now)))


__all__ = ["WishingWellRequest", "WishingWellResponse", "wishing_well_skip_rubies"]
