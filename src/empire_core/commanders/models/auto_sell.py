"""
The auto-sell rules: which new equipment and gems the server sells as they drop.

Commands:
- asg: the rules
- aes: set the equipment rules
- ags: set the gem rules
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ConfigDict, Field, field_serializer, field_validator

from empire_core.enums import EquipmentSlot, Rareness
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse
from empire_core.protocol.js import js_int, js_parse_int

if TYPE_CHECKING:
    from empire_core.gamedata import GemColor

AUTO_SELL_SLOTS = (
    EquipmentSlot.HERO,
    EquipmentSlot.HELMET,
    EquipmentSlot.ARMOR,
    EquipmentSlot.WEAPON,
    EquipmentSlot.ARTIFACT,
)
"""The slots the auto-sell dialog offers: ``AutoSellEquipmentsVO.SLOT_ORDER`` (bundle line 46722)."""

AUTO_SELL_RARENESSES = (Rareness.COMMON, Rareness.RARE, Rareness.EPIC, Rareness.LEGENDARY)
"""The rarities it offers in each, the hero's too: ``AutoSellEquipmentsVO.RARITY_ORDER`` (bundle line 46722)."""

MAX_GEM_LEVEL = 13
"""The highest gem level a gem rule takes: ``GemConst.MAX_GEM_LEVEL`` (dll line 19382)."""


class AutoSellEquipment(BasePayload):
    """
    One kind of equipment the server sells as it drops: a slot and a rarity.

    The rarity is the base one for every slot; on the wire a hero item's is in the hero range,
    ``Rareness.HERO_COMMON - 1`` above it.

    Client: ``C2SSetAutoSellEquipmentConditionsEventVO`` (bundle line 73734) and
    ``AutoSellEquipmentsVO.parseASG`` (bundle line 46681)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    slot: EnumOrInt[EquipmentSlot] = Field(description="The slot, one of AUTO_SELL_SLOTS")
    rareness: EnumOrInt[Rareness] = Field(description="The rarity, one of AUTO_SELL_RARENESSES")

    @classmethod
    def from_wire(cls, row: Any) -> AutoSellEquipment | None:
        """An ``ECS`` row ``[slot, rarity]``; None for one the dialog has no box for, which the client ignores."""
        if not isinstance(row, list) or len(row) < 2:
            return None
        slot, rareness = js_int(row[0]), js_int(row[1])
        if slot == EquipmentSlot.HERO:
            rareness = rareness - Rareness.HERO_COMMON + 1
        if slot not in AUTO_SELL_SLOTS or rareness not in AUTO_SELL_RARENESSES:
            return None
        return cls(slot=slot, rareness=rareness)

    def to_wire(self) -> list[int]:
        """The ``ECS`` row ``[slot, rarity]``."""
        hero = self.slot == EquipmentSlot.HERO
        return [int(self.slot), Rareness.HERO_COMMON - 1 + self.rareness if hero else int(self.rareness)]


class AutoSellRules(BasePayload):
    """
    Which new equipment and gems the server sells as they drop.

    ``gems`` holds, per gem colour, the level up to which its gems are sold; 0 sells none.

    Client: ``AutoSellVO`` (bundle line 120130), ``AutoSellGemsVO`` (bundle line 120147), whose slider runs
    from 0 to ``GemConst.MAX_GEM_LEVEL`` (``AutoSellDialogGemsItem.init``, bundle line 73837)
    """

    equipment: tuple[AutoSellEquipment, ...] = Field(
        validation_alias="ECS", default=(), description="The kinds of equipment sold"
    )
    gems: dict[EnumOrInt["GemColor"], int] = Field(
        validation_alias="GCS", default_factory=dict, description="Per gem colour, the highest level sold; 0 for none"
    )

    @field_validator("equipment", mode="before")
    @classmethod
    def _equipment(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value if isinstance(value, tuple) else ()
        return tuple(rule for row in value if (rule := AutoSellEquipment.from_wire(row)) is not None)

    @field_validator("gems", mode="before")
    @classmethod
    def _gems(cls, value: Any) -> Any:
        # parseASG sets each [level, colour] row as colour -> level (bundle line 120149)
        if isinstance(value, dict):
            return value
        if not isinstance(value, list):
            return {}
        rows = (row for row in value if isinstance(row, list) and len(row) >= 2)
        return {color: js_int(row[0]) for row in rows if (color := js_parse_int(row[1])) is not None}


class GetAutoSellRequest(BaseRequest):
    """
    Request the auto-sell rules.

    Command: asg
    Payload: {}

    The client asks only while the auto-sell subscription effect runs.

    Client: ``C2SGetAutoSellConditionsEventVO`` (bundle line 120114), ``SubscriptionData.parseSIE``
    (bundle lines 119994, 120002)
    """

    command = "asg"


class GetAutoSellResponse(BaseResponse, AutoSellRules):
    """
    The auto-sell rules.

    Command: asg
    Payload: {"ECS": [[slot, rarity], ..], "GCS": [[level, gem colour], ..]}

    Client: ``ASGCommand`` (bundle line 128666), ``AutoSellVO.parseASG`` (bundle line 120131)
    """

    command = "asg"


class SetAutoSellEquipmentRequest(BaseRequest):
    """
    Set the equipment the server sells as it drops.

    Command: aes
    Payload: {"ECS": [[slot, rarity], ..]}

    The server replies with no body.

    Client: ``C2SSetAutoSellEquipmentConditionsEventVO`` (bundle line 73725), ``AESCommand`` (bundle line 128625)
    """

    command = "aes"

    equipment: tuple[AutoSellEquipment, ...] = Field(
        validation_alias="ECS", description="The kinds of equipment sold; sent as [slot, rarity] rows"
    )

    @field_serializer("equipment")
    def _rows(self, value: tuple[AutoSellEquipment, ...]) -> list[list[int]]:
        return [rule.to_wire() for rule in value]


class SetAutoSellGemsRequest(BaseRequest):
    """
    Set, per gem colour, the level up to which the server sells gems as they drop.

    Command: ags
    Payload: {"GCS": [[level, gem colour], ..]}

    The client sends every gem colour. The server replies with no body.

    Client: ``C2SSetAutoSellGemConditionsEventVO`` (bundle line 120180), ``AGSCommand`` (bundle line 128638)
    """

    command = "ags"

    gems: dict[EnumOrInt["GemColor"], int] = Field(
        validation_alias="GCS", description="Per gem colour, the highest level sold; sent as [level, colour] rows"
    )

    @field_serializer("gems")
    def _rows(self, value: dict[int, int]) -> list[list[int]]:
        return [[level, int(color)] for color, level in value.items()]


__all__ = [
    "AUTO_SELL_RARENESSES",
    "AUTO_SELL_SLOTS",
    "MAX_GEM_LEVEL",
    "AutoSellEquipment",
    "AutoSellRules",
    "GetAutoSellRequest",
    "GetAutoSellResponse",
    "SetAutoSellEquipmentRequest",
    "SetAutoSellGemsRequest",
]
