"""Moving units and goods to another kingdom.

Commands:
- kut: Transfer units from a castle to another kingdom
- kgt: Transfer goods from a castle to another kingdom
- msk: Shorten a transfer to another kingdom with a minute skip
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field, field_serializer, field_validator

from empire_core.enums import Kingdom, KingdomTransferType
from empire_core.gamedata import EnumOrStr, WodAmountSlots
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock

from .market import ResourceAmounts
from .objects import block_or_none
from .resources import CastleResources

if TYPE_CHECKING:
    from empire_core.gamedata import Currency

# =============================================================================
# KUT - Kingdom Unit Transfer
# =============================================================================


class KingdomUnitTransferRequest(BaseRequest):
    """
    Send units from one of your castles to another kingdom.

    Command: kut
    Payload: {"SCID": source_castle_id, "SKID": source_kingdom, "TKID": target_kingdom, "CID": target_castle_id,
              "A": [[wod_id, amount], ...]}

    Keys follow the client's order: the constructor initialises SCID, SKID,
    TKID and CID before it sets A. ``CID`` is the picked target castle's
    object id, -1 when none is picked.

    Client: ``C2SKingdomUnitTransferVO`` (bundle line 95305), built by
    ``CastleTransferTroopsToKingdomProperties.getUnitTransferCommand``
    (bundle line 37448) with the units as ``getAsWodAmountArray`` pairs
    """

    command = "kut"

    source_castle_id: int = Field(
        validation_alias="SCID",
        serialization_alias="SCID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    source_kingdom_id: Kingdom = Field(
        validation_alias="SKID",
        serialization_alias="SKID",
        default=Kingdom.GREEN,
        description="The source castle's kingdom",
    )
    target_kingdom_id: Kingdom = Field(
        validation_alias="TKID", serialization_alias="TKID", description="The kingdom to send the units to"
    )
    target_castle_id: int = Field(
        validation_alias="CID",
        serialization_alias="CID",
        default=-1,
        description="Object id of a picked target castle, -1 for none",
    )
    units: WodAmountSlots = Field(
        validation_alias="A", serialization_alias="A", description="The units, one pair per unit"
    )


class KingdomUnitTransferResponse(BaseResponse):
    """
    The transfer's result.

    Command: kut
    Payload: {"gcu": {...}, "gui": {...}, "kpi": {...}}

    ``gui`` (the source castle's units after) is kept as sent; ``kpi`` updates ``client.state.get_kingdoms()``.

    Client: ``KUTCommand.executeCommand`` (bundle line 124732)
    """

    command = "kut"

    currencies: CurrencyBlock = Field(
        validation_alias="gcu", serialization_alias="gcu", default=None, description="Coins and rubies after"
    )


# =============================================================================
# KGT - Kingdom Goods Transfer
# =============================================================================


class KingdomGoodsTransferRequest(BaseRequest):
    """
    Send goods from one of your castles to your castle in another kingdom.

    Command: kgt
    Payload: {"SCID": source_castle_id, "SKID": source_kingdom, "TKID": target_kingdom,
              "G": [[resource_key, amount], ...]}

    Keys follow the client's order: the constructor initialises SCID, SKID and
    TKID before it sets G. ``G`` is built as the market's is, a repeated
    resource merged into one entry.

    Client: ``C2SKingdomGoodsTransferVO`` (bundle line 98402), built by
    ``CastleTransferResToKingdomProperties.getSendResourcesCommand`` (bundle line 55548)
    from ``CastleTransferResourcesDialog.sendResources`` (bundle line 38082), which
    builds ``G`` with ``createCostsListForServer`` (bundle line 38086)
    """

    command = "kgt"

    source_castle_id: int = Field(
        validation_alias="SCID",
        serialization_alias="SCID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    source_kingdom_id: Kingdom = Field(
        validation_alias="SKID",
        serialization_alias="SKID",
        default=Kingdom.GREEN,
        description="The source castle's kingdom",
    )
    target_kingdom_id: Kingdom = Field(
        validation_alias="TKID", serialization_alias="TKID", description="The kingdom to send the goods to"
    )
    goods: ResourceAmounts = Field(
        validation_alias="G",
        serialization_alias="G",
        description="The amount of each resource to send, sent as [key, amount] pairs such as ['W', 1000]",
    )


class KingdomGoodsTransferResponse(BaseResponse):
    """
    The transfer's result.

    Command: kgt
    Payload: {"gcu": {...}, "grc": {...}, "kpi": {...}}

    ``gcu`` and ``kpi`` update ``client.state`` (``client.state.get_kingdoms()`` lists the goods on
    their way); ``grc`` is the joined castle's resources after, kept here.

    Client: ``KGTCommand.executeCommand`` (bundle line 124658)
    """

    command = "kgt"

    currencies: CurrencyBlock = Field(
        validation_alias="gcu", serialization_alias="gcu", default=None, description="Coins and rubies after"
    )
    resources: CastleResources | None = Field(
        validation_alias="grc",
        serialization_alias="grc",
        default=None,
        description="The joined castle's resources after",
    )

    @field_validator("resources", mode="before")
    @classmethod
    def _block(cls, value: Any) -> CastleResources | None:
        return block_or_none(CastleResources, value)


# =============================================================================
# MSK - Minute Skip Kingdom transfer
# =============================================================================


class MinuteSkipKingdomTransferRequest(BaseRequest):
    """
    Shorten the units or goods on their way to a kingdom with a minute skip.

    Command: msk
    Payload: {"MST": minute_skip, "KID": "kingdom_id", "TT": "transfer_type"}

    Keys follow the client's order. ``KID`` is the kingdom the transfer goes
    to; the client sends ``KID`` and ``TT`` through ``toString()``.

    Client: ``C2SMinuteSkipKingdomTransferVO`` (bundle line 54609), built by
    ``KingdomUnitsTravelMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 37497)
    and ``KingdomGoodsTravelMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 55567);
    ``CastleMinuteSkipDialog.onScrollItemClick`` passes the currency's ``jsonKey`` (bundle line 7722)
    """

    command = "msk"

    minute_skip: EnumOrStr["Currency"] = Field(
        validation_alias="MST",
        serialization_alias="MST",
        description="The minute skip used, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``; sent as its key",
    )
    kingdom_id: Kingdom = Field(
        validation_alias="KID", serialization_alias="KID", description="The kingdom the transfer goes to"
    )
    transfer_type: KingdomTransferType = Field(
        validation_alias="TT", serialization_alias="TT", description="Whether the transfer carries units or goods"
    )

    @field_serializer("kingdom_id", "transfer_type")
    def _as_string(self, value: int) -> str:
        return str(int(value))


class MinuteSkipKingdomTransferResponse(BaseResponse):
    """
    The transfers after a minute skip.

    Command: msk
    Payload: {"kpi": {...}}

    ``kpi`` updates ``client.state.get_kingdoms()``.

    Client: ``MSKCommand.executeCommand`` (bundle line 125799)
    """

    command = "msk"


__all__ = [
    "KingdomGoodsTransferRequest",
    "KingdomGoodsTransferResponse",
    "KingdomUnitTransferRequest",
    "KingdomUnitTransferResponse",
    "MinuteSkipKingdomTransferRequest",
    "MinuteSkipKingdomTransferResponse",
]
