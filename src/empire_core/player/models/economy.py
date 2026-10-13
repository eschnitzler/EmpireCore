"""
Loot boxes, as the login data and their pushes send them.

Commands:
- gls: your loot boxes and key progress, a push before and a section of ``gbd``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ConfigDict, Field, field_validator

from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import (
    BasePayload,
    BaseResponse,
    readable_list,
)
from empire_core.protocol.js import ClientNumber

if TYPE_CHECKING:
    from empire_core.gamedata import LootBox, LootBoxType


def _is_object(entry: Any) -> bool:
    return isinstance(entry, dict)


class LootBoxAmount(BasePayload):
    """
    One kind of loot box you hold: ``{"ID": loot box, "AMT": amount}``.

    Client: ``CastleLootboxData.parse_GLS`` (bundle line 112332) reads each as an ``ACollectableItemLootBoxVO``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    loot_box_id: EnumOrInt["LootBox"] = Field(validation_alias="ID", default=0, description="The loot box")
    amount: ClientNumber = Field(validation_alias="AMT", default=0, description="How many you hold")


class LootBoxKeys(BasePayload):
    """
    The keys collected towards one loot box type: ``{"ID": loot box type, "AMT": keys}``.

    Client: ``CastleLootboxData.parse_GLS`` and ``setKeyProgress`` (bundle lines 112332, 112343)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    loot_box_type_id: EnumOrInt["LootBoxType"] = Field(
        validation_alias="ID", default=0, description="The loot box type"
    )
    keys: ClientNumber = Field(validation_alias="AMT", default=0, description="The keys collected")


class LootBoxesResponse(BaseResponse):
    """
    Your loot boxes, and the keys collected towards each loot box type.

    A ``gls`` lists the loot boxes whole, but key progress only for some types; the client keeps the
    others as they were, and ``client.state.get_loot_boxes()`` does the same.

    Command: gls, a push the server sends before ``gbd`` and again when they change.

    Client: ``GLSCommand`` (bundle line 124800), ``CastleLootboxData.parse_GLS`` (bundle line 112332)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gls"

    loot_boxes: tuple[LootBoxAmount, ...] = Field(
        validation_alias="ALL", default=(), description="The loot boxes you hold"
    )
    key_progress: tuple[LootBoxKeys, ...] = Field(
        validation_alias="KEY",
        default=(),
        description="Keys collected per loot box type this packet lists",
    )

    @field_validator("loot_boxes", mode="before")
    @classmethod
    def _amounts(cls, value: Any) -> Any:
        return tuple(readable_list(LootBoxAmount, value, accept=_is_object))

    @field_validator("key_progress", mode="before")
    @classmethod
    def _keys(cls, value: Any) -> Any:
        return tuple(readable_list(LootBoxKeys, value, accept=_is_object))

    def amount(self, loot_box_id: LootBox | int) -> int | float:
        """How many of a loot box you hold."""
        return sum(entry.amount for entry in self.loot_boxes if entry.loot_box_id == loot_box_id)

    def keys(self, loot_box_type_id: LootBoxType | int) -> int | float:
        """The keys collected towards a loot box type, 0 when none is known."""
        return next((entry.keys for entry in self.key_progress if entry.loot_box_type_id == loot_box_type_id), 0)


__all__ = [
    "LootBoxAmount",
    "LootBoxKeys",
    "LootBoxesResponse",
]
