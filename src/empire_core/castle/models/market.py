"""Sending resources between castles, and the market overview.

Commands:
- crm: Send resources to a castle
- cmi: List your castles' carriages and resources
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_validator

from empire_core.enums import Kingdom, MarketScope
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    CurrencyBlock,
    object_or_none,
    readable_list,
)
from empire_core.protocol.js import js_int

from .resources import CastleResources

logger = logging.getLogger(__name__)


# =============================================================================
# CRM - Send Resources
# =============================================================================


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

    kingdom_id: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The source castle's kingdom")
    source_castle_id: int = Field(
        alias="SID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    target_x: int = Field(alias="TX", description="Map x of the target castle")
    target_y: int = Field(alias="TY", description="Map y of the target castle")
    horses_type: int = Field(alias="HBW", default=-1, description="The horse's wod id, -1 for none or for feathers")
    feathers: int = Field(alias="PTT", default=0, description="1 when the horse is paid with feathers")
    slowdown: int = Field(alias="SD", default=0, description="Seconds the arrival is delayed by")
    goods: list[list[Any]] = Field(
        alias="G", description="The resources to send, as [resource key, amount] pairs such as ['W', 1000]"
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

    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")
    resources: CastleResources | None = Field(
        alias="grc", default=None, description="The joined castle's resources after"
    )

    @field_validator("resources", mode="before")
    @classmethod
    def _block(cls, value: Any) -> Any:
        return object_or_none(value)


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

    scope: MarketScope = Field(alias="S", default=MarketScope.ALL_KINGDOMS, description="Which castles to list")
    kingdom_id: int = Field(alias="KID", default=-1, description="The kingdom to list, -1 with ALL_KINGDOMS")


class MarketCastle(BasePayload):
    """
    One castle in the market overview.

    ``AE`` (the castle's area effects) is kept as sent.

    Client: ``CastleTradeVO.fillFromParamObject`` (bundle line 140345), which
    reads every number through ``int()``
    """

    kingdom_id: int = Field(alias="KID", default=0, description="The castle's kingdom")
    castle_id: int = Field(alias="CID", default=0, description="The castle's object id")
    total_carriages: int = Field(alias="TC", default=0, description="The castle's market carriages")
    available_carriages: int = Field(alias="AC", default=0, description="Carriages not on the road")
    wood: int = Field(alias="W", default=0, description="Wood in stock")
    stone: int = Field(alias="S", default=0, description="Stone in stock")
    food: int = Field(alias="F", default=0, description="Food in stock")
    coal: int = Field(alias="C", default=0, description="Coal in stock")
    oil: int = Field(alias="O", default=0, description="Oil in stock")
    glass: int = Field(alias="G", default=0, description="Glass in stock")
    iron: int = Field(alias="I", default=0, description="Iron in stock")
    honey: int = Field(alias="HONEY", default=0, description="Honey in stock")
    mead: int = Field(alias="MEAD", default=0, description="Mead in stock")
    beef: int = Field(alias="BEEF", default=0, description="Beef in stock")

    @field_validator("*", mode="before")
    @classmethod
    def _int(cls, value: Any) -> int:
        return js_int(value)


class MarketInfoResponse(BaseResponse):
    """
    Your castles' market carriages and resources.

    Command: cmi
    Payload: {"C": [{"KID": .., "CID": .., "TC": .., "AC": .., "W": .., ...}, ...]}

    Client: ``CMICommand.executeCommand`` (bundle line 128944),
    ``CastleTradeInfoVO.fillCastleList`` (bundle line 140325)
    """

    command = "cmi"

    castles: list[MarketCastle] = Field(alias="C", default_factory=list, description="Each of your castles")

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
