"""Moving units and goods to a season's treasure map.

Commands:
- tgt: Send goods from a castle to a treasure map
- tut: Send units from a castle to a treasure map
- tkt: Finish a transfer to a treasure map at once, for rubies
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from empire_core.enums import Kingdom, KingdomTransferType
from empire_core.gamedata import EnumOrInt, WodAmountSlots
from empire_core.gamedata.ids.events import Event
from empire_core.map.models.treasure_maps import TreasureMapsBlock
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock

from .market import ResourceAmounts

if TYPE_CHECKING:
    from empire_core.gamedata import TreasureMapId


class TreasureMapGoodsTransferRequest(BaseRequest):
    """
    Send goods from one of your castles to a season's treasure map.

    Command: tgt
    Payload: {"MID": map_id, "SCID": source_castle_id, "KID": source_kingdom, "G": [[resource_key, amount], ...]}

    Keys follow the client's order: the constructor initialises MID, SCID and KID before it sets G.
    ``G`` is built as the market's is, a repeated resource merged into one entry.

    Client: ``C2STreasuremapGoodsTransferVO`` (bundle line 99601), built by
    ``CastleTransferResToSeasonProperties.getSendResourcesCommand`` (bundle line 99586) from
    ``CastleTransferResourcesDialog.sendResources`` (bundle line 38094), which sends the picked
    castle's ``objectId`` and ``kingdomID`` and builds ``G`` with ``createCostsListForServer``
    (bundle line 38096)
    """

    command = "tgt"

    map_id: EnumOrInt["TreasureMapId"] = Field(validation_alias="MID", description="The season's treasure map")
    source_castle_id: int = Field(
        validation_alias="SCID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    source_kingdom_id: Kingdom = Field(
        validation_alias="KID", default=Kingdom.GREEN, description="The source castle's kingdom"
    )
    goods: ResourceAmounts = Field(
        validation_alias="G",
        description="The amount of each resource to send",
    )


class TreasureMapGoodsTransferResponse(BaseResponse):
    """
    Your treasure maps after the goods left.

    Command: tgt
    Payload: {"tmp": {...}}

    Client: ``TGTCommand.executeCommand`` (bundle line 129068), which shows ``NOT_ENOUGH_RESOURCES``
    as a dialog of its own
    """

    command = "tgt"

    treasure_maps: TreasureMapsBlock = Field(validation_alias="tmp", default=None, description="Your maps after")


class TreasureMapUnitTransferRequest(BaseRequest):
    """
    Send units from one of your castles to a season's treasure map.

    Command: tut
    Payload: {"MID": map_id, "SCID": source_castle_id, "KID": source_kingdom, "I": [[wod_id, amount], ...]}

    Keys follow the client's order: the constructor initialises MID, SCID and KID before it sets I.

    Client: ``C2STreasuremapUnitTransferVO`` (bundle line 97853), built by
    ``CastleTransferTroopsToSeasonProperties.getUnitTransferCommand`` (bundle line 55379) from
    ``CastleTransferTroopsDialog.sendUnitsCommand`` (bundle line 24429) with the units as
    ``getAsWodAmountArray`` pairs
    """

    command = "tut"

    map_id: EnumOrInt["TreasureMapId"] = Field(validation_alias="MID", description="The season's treasure map")
    source_castle_id: int = Field(
        validation_alias="SCID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    source_kingdom_id: Kingdom = Field(
        validation_alias="KID", default=Kingdom.GREEN, description="The source castle's kingdom"
    )
    units: WodAmountSlots = Field(validation_alias="I", description="The units, one pair per unit")


class TreasureMapUnitTransferResponse(BaseResponse):
    """
    Your treasure maps after the units left.

    Command: tut
    Payload: {"tmp": {...}}

    Client: ``TUTCommand.executeCommand`` (bundle line 129118)
    """

    command = "tut"

    treasure_maps: TreasureMapsBlock = Field(validation_alias="tmp", default=None, description="Your maps after")


class TreasureMapTransferSkipRequest(BaseRequest):
    """
    Let the units or goods on their way to a season's treasure map arrive at once, for rubies.

    Command: tkt
    Payload: {"EID": event_id, "MID": map_id, "TT": transfer_type}

    Client: ``C2STreasuremapSkipTransferVO`` (bundle line 38304), sent by the full skip buttons of
    ``CastleStartSeasonEventDialogSupport.onMouseUp`` (bundle lines 99541, 99543) and by
    ``SeasonTravelGoodsMinuteSkipProperties.getFullSkipCommand`` and
    ``SeasonTravelUnitsMinuteSkipProperties.getFullSkipCommand`` (bundle lines 99613, 99645)
    with the season event's ``eventId``
    """

    command = "tkt"

    event_id: EnumOrInt[Event] = Field(validation_alias="EID", description="The season event the map belongs to")
    map_id: EnumOrInt["TreasureMapId"] = Field(validation_alias="MID", description="The season's treasure map")
    transfer_type: KingdomTransferType = Field(
        validation_alias="TT", description="Whether the transfer carries units or goods"
    )


class TreasureMapTransferSkipResponse(BaseResponse):
    """
    Your treasure maps and currencies after the skip.

    Command: tkt
    Payload: {"tmp": {...}, "gcu": {...}}

    Client: ``TKTCommand.executeCommand`` (bundle line 129088)
    """

    command = "tkt"

    treasure_maps: TreasureMapsBlock = Field(validation_alias="tmp", default=None, description="Your maps after")
    currencies: CurrencyBlock = Field(validation_alias="gcu", default=None, description="Coins and rubies after")


__all__ = [
    "TreasureMapGoodsTransferRequest",
    "TreasureMapGoodsTransferResponse",
    "TreasureMapTransferSkipRequest",
    "TreasureMapTransferSkipResponse",
    "TreasureMapUnitTransferRequest",
    "TreasureMapUnitTransferResponse",
]
