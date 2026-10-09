"""Sending resources between castles, and the market overview.

Commands:
- crm: Send resources to a castle
- cmi: List your castles' carriages and resources
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, PlainSerializer, field_validator

from empire_core.enums import Kingdom, MarketScope, Resource
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    CurrencyBlock,
    readable_list,
)
from empire_core.protocol.js import ClientInt

from .objects import block_or_none
from .resources import CastleResources

logger = logging.getLogger(__name__)


# =============================================================================
# CRM - Send Resources
# =============================================================================


def _resource_rows(value: Any) -> Any:
    """``[[resource_key, amount], ...]`` as ``{Resource: amount}``, a repeated resource added up."""
    if isinstance(value, Mapping) or not isinstance(value, list | tuple):
        return value
    totals: dict[Any, int] = {}
    for row in value:
        if isinstance(row, list | tuple) and len(row) >= 2:
            totals[row[0]] = totals.get(row[0], 0) + row[1]
    return totals


ResourceAmounts = Annotated[
    dict[Resource, int],
    BeforeValidator(_resource_rows),
    PlainSerializer(lambda amounts: [[resource.value, amount] for resource, amount in amounts.items()]),
]
"""Resources by amount, sent as ``[[resource_key, amount], ...]`` in insertion order.

Client: ``CollectableParserC2SCosts.createCostsListForServer`` (bundle line 62921) adds up a repeated
item (``combineDuplicatedItems``) and then writes ``[itemType.serverKey, amount]`` per item
"""


class CreateMarketMovementRequest(BaseRequest):
    """
    Send resources from one of your castles to a castle on the map, by carriage.

    Command: crm
    Payload: {"KID": kingdom_id, "SID": source_castle_id, "TX": x, "TY": y, "HBW": horse, "PTT": 0 or 1,
              "SD": slowdown, "G": [[resource_key, amount], ...]}

    Keys follow the client's order: the constructor initialises KID to SD and
    sets G after them. ``KID`` is the source castle's kingdom. A horse paid
    with feathers is sent as ``HBW`` -1 with ``PTT`` 1. The client merges
    repeated resources in ``G`` into one entry each.

    Client: ``C2SCreateMarketMovementVO`` (bundle line 68348), sent by
    ``CastlePostSendGoodsDialog.sendGoods`` (bundle line 33377); ``G`` is
    built by ``CollectableParserC2SCosts.createCostsListForServer`` (bundle line 62921)
    """

    command = "crm"

    kingdom_id: Kingdom = Field(
        validation_alias="KID",
        serialization_alias="KID",
        default=Kingdom.GREEN,
        description="The source castle's kingdom",
    )
    source_castle_id: int = Field(
        validation_alias="SID",
        serialization_alias="SID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    target_x: int = Field(validation_alias="TX", serialization_alias="TX", description="Map x of the target castle")
    target_y: int = Field(validation_alias="TY", serialization_alias="TY", description="Map y of the target castle")
    horse_booster_id: int = Field(
        validation_alias="HBW",
        serialization_alias="HBW",
        default=-1,
        description="The horse booster's wod id, -1 for none or when paid with feathers",
    )
    feathers: int = Field(
        validation_alias="PTT",
        serialization_alias="PTT",
        default=0,
        description="1 when the horse is paid with feathers",
    )
    slowdown: int = Field(
        validation_alias="SD", serialization_alias="SD", default=0, description="Seconds the arrival is delayed by"
    )
    goods: ResourceAmounts = Field(
        validation_alias="G",
        serialization_alias="G",
        description="The amount of each resource to send, sent as [key, amount] pairs such as ['W', 1000]",
    )


class CreateMarketMovementResponse(BaseResponse):
    """
    The carriage on its way.

    Command: crm
    Payload: {"gcu": {...}, "grc": {...}, "O": [owner, ...], "A": movement}

    ``O`` (the owners involved) and ``A`` (the new movement) are kept as sent.

    Client: ``CRMCommand.executeCommand`` (bundle line 125981)
    """

    command = "crm"

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
# CMI - Market Info
# =============================================================================


class MarketInfoRequest(BaseRequest):
    """
    List your castles' market carriages and resources.

    Command: cmi
    Payload: {"S": scope, "KID": kingdom_id}

    The client always sends ``{"S": 1, "KID": -1}``: every kingdom.

    Client: ``C2SMarketInfoVO`` (bundle line 27012)
    """

    command = "cmi"

    scope: MarketScope = Field(
        validation_alias="S",
        serialization_alias="S",
        default=MarketScope.ALL_KINGDOMS,
        description="Which castles to list",
    )
    kingdom_id: int = Field(
        validation_alias="KID",
        serialization_alias="KID",
        default=-1,
        description="The kingdom to list, -1 with ALL_KINGDOMS",
    )


class MarketCastle(BasePayload):
    """
    One castle in the market overview.

    ``AE`` (the castle's area effects) is kept as sent.

    Client: ``CastleTradeVO.fillFromParamObject`` (bundle line 140345), which
    reads every number through ``int()``
    """

    kingdom_id: ClientInt = Field(
        validation_alias="KID", serialization_alias="KID", default=0, description="The castle's kingdom"
    )
    castle_id: ClientInt = Field(
        validation_alias="CID", serialization_alias="CID", default=0, description="The castle's object id"
    )
    total_carriages: ClientInt = Field(
        validation_alias="TC", serialization_alias="TC", default=0, description="The castle's market carriages"
    )
    available_carriages: ClientInt = Field(
        validation_alias="AC", serialization_alias="AC", default=0, description="Carriages not on the road"
    )
    wood: ClientInt = Field(validation_alias="W", serialization_alias="W", default=0, description="Wood in stock")
    stone: ClientInt = Field(validation_alias="S", serialization_alias="S", default=0, description="Stone in stock")
    food: ClientInt = Field(validation_alias="F", serialization_alias="F", default=0, description="Food in stock")
    coal: ClientInt = Field(validation_alias="C", serialization_alias="C", default=0, description="Coal in stock")
    oil: ClientInt = Field(validation_alias="O", serialization_alias="O", default=0, description="Oil in stock")
    glass: ClientInt = Field(validation_alias="G", serialization_alias="G", default=0, description="Glass in stock")
    iron: ClientInt = Field(validation_alias="I", serialization_alias="I", default=0, description="Iron in stock")
    honey: ClientInt = Field(
        validation_alias="HONEY", serialization_alias="HONEY", default=0, description="Honey in stock"
    )
    mead: ClientInt = Field(validation_alias="MEAD", serialization_alias="MEAD", default=0, description="Mead in stock")
    beef: ClientInt = Field(validation_alias="BEEF", serialization_alias="BEEF", default=0, description="Beef in stock")


class MarketInfoResponse(BaseResponse):
    """
    Your castles' market carriages and resources.

    Command: cmi
    Payload: {"C": [{"KID": .., "CID": .., "TC": .., "AC": .., "W": .., ...}, ...]}

    Client: ``CMICommand.executeCommand`` (bundle line 128944),
    ``CastleTradeInfoVO.fillCastleList`` (bundle line 140325)
    """

    command = "cmi"

    castles: list[MarketCastle] = Field(
        validation_alias="C", serialization_alias="C", default_factory=list, description="Each of your castles"
    )

    @field_validator("castles", mode="before")
    @classmethod
    def _castles(cls, value: Any) -> list[MarketCastle]:
        return readable_list(
            MarketCastle, value, accept=lambda entry: isinstance(entry, dict), warn=logger, what="cmi castles"
        )


__all__ = [
    "CreateMarketMovementRequest",
    "CreateMarketMovementResponse",
    "MarketCastle",
    "MarketInfoRequest",
    "MarketInfoResponse",
]
