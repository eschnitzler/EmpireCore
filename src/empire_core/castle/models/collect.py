"""Collecting from mines and resource carts.

Commands:
- cmr: Collect a mine
- rcc: Collect a resource cart
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_serializer, field_validator

from empire_core.enums import ResourceCartType
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    CurrencyBlock,
    enum_or_none,
    object_or_none,
    readable_list,
)
from empire_core.protocol.js import js_int

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

    object_id: int = Field(alias="OID", description="The mine's object id, a BuildingRow.object_id")


class MineStatus(BasePayload):
    """
    One mine's state, an entry of the ``gsm`` block's ``M``.

    Client: ``CastleMineData.parse_GSM`` (bundle line 50363) and
    ``triggerInfoFlash`` (bundle line 50371)
    """

    object_id: int = Field(alias="OID", default=-1, description="The mine's object id")
    remaining_collection_amount: int = Field(alias="RC", default=0, description="What is left to collect")
    next_collect_seconds: int = Field(
        alias="NC", default=0, description="Seconds until the mine can be collected again, -1 when it is done"
    )
    coins: int | None = Field(alias="C1", default=None, description="Coins just collected; None for none")
    rubies: int | None = Field(alias="C2", default=None, description="Rubies just collected; None for none")


class MineStatusList(BasePayload):
    """The ``gsm`` block: every mine in the castle."""

    mines: list[MineStatus] = Field(alias="M", default_factory=list, description="Each mine")

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

    mines: MineStatusList | None = Field(alias="gsm", default=None, description="The castle's mines after")
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")

    @field_validator("mines", mode="before")
    @classmethod
    def _block(cls, value: Any) -> Any:
        return object_or_none(value)


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

    cart_type: ResourceCartType = Field(alias="RT", description="The cart's resource")

    @field_serializer("cart_type")
    def _index(self, value: ResourceCartType) -> int:
        return int(value)


class ResourceCart(BasePayload):
    """
    One resource cart, an entry of the ``rci`` block's ``RC``.

    Client: ``ResourceCartData.parseRciItem`` (bundle line 81053)
    """

    cart_type: ResourceCartType | None = Field(
        alias="RT", default=None, description="The cart's resource; None for an unknown index"
    )
    amount: int = Field(alias="A", default=0, description="What the cart carries")
    remaining_seconds: int | float | None = Field(
        alias="RS", default=None, description="Seconds until the cart is ready"
    )

    _type = field_validator("cart_type", mode="before")(_cart_type)
    _amount = field_validator("amount", mode="before")(js_int)


class ResourceCartInfo(BasePayload):
    """The ``rci`` block: the castle's resource carts, wood, stone and food."""

    carts: list[ResourceCart] = Field(alias="RC", default_factory=list, description="Each cart")

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
        alias="RT", default=None, description="The collected cart's resource; None for an unknown index"
    )
    amount: int = Field(alias="A", default=0, description="How much was collected")
    resources: CastleResources | None = Field(alias="grc", default=None, description="The castle's resources after")
    carts: ResourceCartInfo | None = Field(alias="rci", default=None, description="The castle's carts after")

    _type = field_validator("cart_type", mode="before")(_cart_type)
    _amount = field_validator("amount", mode="before")(js_int)

    @field_validator("resources", "carts", mode="before")
    @classmethod
    def _block(cls, value: Any) -> Any:
        return object_or_none(value)


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
