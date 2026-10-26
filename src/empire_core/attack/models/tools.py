"""Buying tools for rubies from the attack and defence screens.

Commands:
- ibt: Instantly buy tools into a castle
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field, field_validator

from empire_core.enums import Kingdom
from empire_core.gamedata import EnumOrInt, PackageId
from empire_core.map.models.treasure_maps import NO_TREASURE_MAP, TreasureMapOrNone
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, CurrencyBlock, object_or_none
from empire_core.protocol.js import ClientInt

if TYPE_CHECKING:
    from empire_core.gamedata import Tool

NO_PACKAGE = PackageId(-1)
"""No event package: tools bought at their own price."""


class BuyToolsRequest(BaseRequest):
    """
    Buy tools into a castle for rubies.

    Fields follow the client's key order, the order its constructor first sets them in.

    Command: ibt
    Payload: {"W": tool, "A": amount, "CX": x, "CY": y, "MID": map, "KID": kingdom, "PID": package}
    Client: ``C2SDefenceInstantBuyToolVO`` (bundle line 66682), built by ``ToolUnitVO.requestInstantBuy``
    (bundle line 6547) from ``CastleDefenceBuyUnitsDialog.onClick`` (bundle line 22500): the area the
    tools go to, the treasure map of an event camp the attack starts from (bundle line 101665), and
    the event package the price comes from
    """

    command = "ibt"

    tool: EnumOrInt["Tool"] = Field(validation_alias="W", description="The tool to buy")
    amount: int = Field(validation_alias="A", description="How many to buy")
    x: int = Field(validation_alias="CX", description="Map x of the castle the tools go to")
    y: int = Field(validation_alias="CY", description="Map y of the castle the tools go to")
    map_id: TreasureMapOrNone = Field(
        validation_alias="MID", default=NO_TREASURE_MAP, description="The treasure map of an event camp, else -1"
    )
    kingdom: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    package_id: PackageId = Field(
        validation_alias="PID", default=NO_PACKAGE, description="The event package whose price applies, else -1"
    )


class BoughtTools(BasePayload):
    """
    The tools bought: an ``ibt`` reply's ``O``.

    Client: the ``NEW_TOOL_BOUGHT`` handlers, e.g. ``CastleFightDialog.onNewToolBought`` (bundle line 14010)
    """

    tool: EnumOrInt["Tool"] = Field(validation_alias="W", description="The tool bought")
    amount: ClientInt = Field(validation_alias="A", default=0, description="How many were bought")


class BuyToolsResponse(BaseResponse):
    """
    The tools bought and your coins and rubies after.

    Command: ibt
    Client: ``IBTCommand.executeCommand`` (bundle line 123574): ``NEW_TOOL_BOUGHT`` with ``O``, then ``parseGCU(gcu)``
    """

    command = "ibt"

    bought: BoughtTools | None = Field(validation_alias="O", default=None, description="The tools bought")
    currencies: CurrencyBlock = Field(validation_alias="gcu", default=None, description="Coins and rubies after")

    @field_validator("bought", mode="before")
    @classmethod
    def _bought_needs_an_object(cls, value: Any) -> Any:
        return object_or_none(value)


__all__ = ["NO_PACKAGE", "BoughtTools", "BuyToolsRequest", "BuyToolsResponse"]
