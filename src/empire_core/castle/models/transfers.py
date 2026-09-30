"""Moving units to another kingdom.

Commands:
- kut: Transfer units from a castle to another kingdom
"""

from __future__ import annotations

from pydantic import Field

from empire_core.enums import Kingdom
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock

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
        alias="SCID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    source_kingdom_id: Kingdom = Field(alias="SKID", default=Kingdom.GREEN, description="The source castle's kingdom")
    target_kingdom_id: Kingdom = Field(alias="TKID", description="The kingdom to send the units to")
    target_castle_id: int = Field(
        alias="CID", default=-1, description="Object id of a picked target castle, -1 for none"
    )
    units: list[list[int]] = Field(alias="A", description="The units, as [wod id, amount] pairs")


class KingdomUnitTransferResponse(BaseResponse):
    """
    The transfer's result.

    Command: kut
    Payload: {"gcu": {...}, "gui": {...}, "kpi": {...}}

    ``gui`` (the source castle's units after) and ``kpi`` are kept as sent.

    Client: ``KUTCommand.executeCommand`` (bundle line 124732)
    """

    command = "kut"

    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")


__all__ = [
    "KingdomUnitTransferRequest",
    "KingdomUnitTransferResponse",
]
