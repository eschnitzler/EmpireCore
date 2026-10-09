"""Mines and resource carts, and collecting from them.

Commands:
- cmr: Collect a mine
- gsm: The joined castle's mines (pushed)
- rcc: Collect a resource cart
- rci: The joined castle's resource carts (pushed)
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_serializer, field_validator

from empire_core.enums import ResourceCartType
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    CurrencyBlock,
    enum_or_none,
    readable_list,
)
from empire_core.protocol.js import js_int

from .objects import block_or_none
from .resources import CastleResources

logger = logging.getLogger(__name__)


def _cart_type(value: Any) -> ResourceCartType | None:
    # getEnumItemFromIndex: any other index is no resource
    if isinstance(value, int) and not isinstance(value, bool):
        return enum_or_none(ResourceCartType, value)
    return None


# =============================================================================
# CMR - Collect a Mine
# =============================================================================


class CollectMineResourcesRequest(BaseRequest):
    """
    Collect what a mine in the joined castle has produced.

    Command: cmr
    Payload: {"OID": object_id}

    Client: ``C2SCollectMineResources`` (bundle line 84598), sent by
    ``AMineBuildingVE.onMouseClick`` (bundle line 51410)
    """

    command = "cmr"

    object_id: int = Field(
        validation_alias="OID", serialization_alias="OID", description="The mine's object id, a BuildingRow.object_id"
    )


class MineStatus(BasePayload):
    """
    One mine's state, an entry of the ``gsm`` block's ``M``.

    Client: ``CastleMineData.parse_GSM`` (bundle line 50363) and
    ``triggerInfoFlash`` (bundle line 50371)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    object_id: int = Field(
        validation_alias="OID", serialization_alias="OID", default=-1, description="The mine's object id"
    )
    remaining_collection_amount: int = Field(
        validation_alias="RC", serialization_alias="RC", default=0, description="What is left to collect"
    )
    next_collect_seconds: int = Field(
        validation_alias="NC",
        serialization_alias="NC",
        default=0,
        description="Seconds until the mine can be collected again, -1 when it is done",
    )
    coins: int | None = Field(
        validation_alias="C1", serialization_alias="C1", default=None, description="Coins just collected; None for none"
    )
    rubies: int | None = Field(
        validation_alias="C2",
        serialization_alias="C2",
        default=None,
        description="Rubies just collected; None for none",
    )


class MineStatusList(BaseResponse):
    """
    The joined castle's mines: the ``gsm`` push, and the block of that name in
    the ``cmr`` and ``jaa`` replies.

    Command: gsm
    Payload: {"M": [{"OID": .., "RC": .., "NC": ..}, ...]}

    Client: ``GSMCommand.executeCommand`` (bundle line 125752),
    ``CastleMineData.parse_GSM`` (bundle line 50363)
    """

    command = "gsm"

    mines: list[MineStatus] = Field(
        validation_alias="M", serialization_alias="M", default_factory=list, description="Each mine"
    )

    @field_validator("mines", mode="before")
    @classmethod
    def _mines(cls, value: Any) -> list[MineStatus]:
        return readable_list(MineStatus, value, accept=lambda entry: isinstance(entry, dict), warn=logger, what="mines")


class CollectMineResourcesResponse(BaseResponse):
    """
    The mines after collecting.

    Command: cmr
    Payload: {"gsm": {"M": [{"OID": .., "RC": .., "NC": .., "C1": ..}, ...]}, "gcu": {...}}

    Client: ``CMRCommand.executeCommand`` (bundle line 125737)
    """

    command = "cmr"

    mines: MineStatusList | None = Field(
        validation_alias="gsm", serialization_alias="gsm", default=None, description="The castle's mines after"
    )
    currencies: CurrencyBlock = Field(
        validation_alias="gcu", serialization_alias="gcu", default=None, description="Coins and rubies after"
    )

    @field_validator("mines", mode="before")
    @classmethod
    def _block(cls, value: Any) -> MineStatusList | None:
        return block_or_none(MineStatusList, value)


# =============================================================================
# RCC - Collect a Resource Cart
# =============================================================================


class CollectResourceCartRequest(BaseRequest):
    """
    Collect the joined castle's resource cart of one resource.

    Command: rcc
    Payload: {"RT": cart_type}

    Client: ``C2SIsoResourceCartCollectVO`` (bundle line 87566), sent by
    ``ResourceCartSurroundingsVE.onMouseClick`` (bundle line 87542)
    """

    command = "rcc"

    cart_type: ResourceCartType = Field(
        validation_alias="RT", serialization_alias="RT", description="The cart's resource"
    )

    @field_serializer("cart_type")
    def _index(self, value: ResourceCartType) -> int:
        return int(value)


class ResourceCart(BasePayload):
    """
    One resource cart, an entry of the ``rci`` block's ``RC``.

    Client: ``ResourceCartData.parseRciItem`` (bundle line 81053)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    cart_type: ResourceCartType | None = Field(
        validation_alias="RT",
        serialization_alias="RT",
        default=None,
        description="The cart's resource; None for an unknown index",
    )
    amount: int = Field(validation_alias="A", serialization_alias="A", default=0, description="What the cart carries")
    remaining_seconds: int | float | None = Field(
        validation_alias="RS", serialization_alias="RS", default=None, description="Seconds until the cart is ready"
    )

    _type = field_validator("cart_type", mode="before")(_cart_type)
    _amount = field_validator("amount", mode="before")(js_int)


class ResourceCartInfo(BaseResponse):
    """
    The joined castle's resource carts, wood, stone and food: the ``rci`` push,
    and the block of that name in the ``rcc`` and ``jaa`` replies.

    Command: rci
    Payload: {"RC": [{"RT": .., "A": .., "RS": ..}, ...]}

    The client reads the first three entries, one cart each.

    Client: ``RCICommand.executeCommand`` (bundle line 123196),
    ``CastleResourceCartsData.parse_RCI`` (bundle line 28798)
    """

    command = "rci"

    carts: list[ResourceCart] = Field(
        validation_alias="RC", serialization_alias="RC", default_factory=list, description="Each cart"
    )

    @field_validator("carts", mode="before")
    @classmethod
    def _carts(cls, value: Any) -> list[ResourceCart]:
        return readable_list(
            ResourceCart, value, accept=lambda entry: isinstance(entry, dict), warn=logger, what="carts"
        )


class CollectResourceCartResponse(BaseResponse):
    """
    The collected cart.

    Command: rcc
    Payload: {"RT": cart_type, "A": amount, "grc": {...}, "rci": {"RC": [...]}}

    Client: ``RCCCommand.executeCommand`` (bundle line 123181),
    ``CastleResourceCartsData.parse_RCC`` (bundle line 28796)
    """

    command = "rcc"

    cart_type: ResourceCartType | None = Field(
        validation_alias="RT",
        serialization_alias="RT",
        default=None,
        description="The collected cart's resource; None for an unknown index",
    )
    amount: int = Field(validation_alias="A", serialization_alias="A", default=0, description="How much was collected")
    resources: CastleResources | None = Field(
        validation_alias="grc", serialization_alias="grc", default=None, description="The castle's resources after"
    )
    carts: ResourceCartInfo | None = Field(
        validation_alias="rci", serialization_alias="rci", default=None, description="The castle's carts after"
    )

    _type = field_validator("cart_type", mode="before")(_cart_type)
    _amount = field_validator("amount", mode="before")(js_int)

    @field_validator("resources", mode="before")
    @classmethod
    def _resources(cls, value: Any) -> CastleResources | None:
        return block_or_none(CastleResources, value)

    @field_validator("carts", mode="before")
    @classmethod
    def _carts(cls, value: Any) -> ResourceCartInfo | None:
        return block_or_none(ResourceCartInfo, value)


__all__ = [
    "CollectMineResourcesRequest",
    "CollectMineResourcesResponse",
    "CollectResourceCartRequest",
    "CollectResourceCartResponse",
    "MineStatus",
    "MineStatusList",
    "ResourceCart",
    "ResourceCartInfo",
]
