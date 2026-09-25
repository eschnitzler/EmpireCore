"""
Commander protocol models.

Commands:
- gli: Get Lords Info - the server name for the commander/castellan list
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Any

from pydantic import Field, ValidationError, model_validator

from .base import BasePayload, BaseRequest, BaseResponse

logger = logging.getLogger(__name__)

NO_GEM_ID = -1


class EquipmentSlot(IntEnum):
    """Slot an equipment item occupies."""

    ARMOR = 1
    WEAPON = 2
    HELMET = 3
    ARTIFACT = 4
    SKIN = 5
    HERO = 6


class WearerType(IntEnum):
    """Who may wear an equipment item."""

    ALL = 0
    CASTELLAN = 1  # EquipmentConst.BARON_WEARER_ID
    COMMANDER = 2


class EquipmentType(IntEnum):
    """Origin of an equipment item."""

    GENERATED = 0
    UNIQUE = 1
    RELIC = 3


class Equipment(BasePayload):
    """
    An equipment item worn by a commander or castellan.

    Parsed from a positional EQ entry:
    [id, slot, wearer, rarity, graphic, bonuses, unique_id, set_id,
     enchantment_level, duration_seconds, gem_id, equipment_type]
    Entries are truncated by the server when trailing fields do not apply.

    Client: ``BasicEquipmentVO.parseEquipFromArray`` (bundle line 7115).
    """

    equipment_id: int = 0
    slot: int = 0
    wearer_type: int = WearerType.ALL
    rarity_id: int = 0
    graphic: int = 0
    bonuses: list = Field(default_factory=list)
    unique_id: int = 0
    set_id: int = 0
    enchantment_level: int = 0
    duration_seconds: int = 0
    gem_id: int = NO_GEM_ID
    equipment_type: int = EquipmentType.GENERATED

    @property
    def is_permanent(self) -> bool:
        """True when the item does not expire (the server sends -1)."""
        return self.duration_seconds < 1

    @property
    def has_gem(self) -> bool:
        """True when a gem is slotted."""
        return self.gem_id != NO_GEM_ID

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, (list, tuple)):
            return data
        return dict(zip(_EQUIPMENT_ROW, data, strict=False))

    @classmethod
    def from_list(cls, data: list) -> "Equipment":
        """Parse from an EQ array entry, tolerating short entries."""
        return cls.model_validate(data)


_EQUIPMENT_ROW = (
    "equipment_id",
    "slot",
    "wearer_type",
    "rarity_id",
    "graphic",
    "bonuses",
    "unique_id",
    "set_id",
    "enchantment_level",
    "duration_seconds",
    "gem_id",
    "equipment_type",
)


class CommanderEffect(BasePayload):
    """One entry of a commander's ``E`` or ``AE``: ``[effect_id, values, source]``.

    Client: ``LordVO.parseRawEffects`` (bundle line 26483), ``BonusVO.parseFromValueArray``
    (bundle line 5707).
    """

    effect_id: int = Field(description="Effect id, row[0]")
    values: list[Any] = Field(
        default_factory=list,
        description="Value array, row[1]; its layout depends on the effect type's EffectValue class",
    )
    source: str = Field(default="", description="EffectSourceEnum server key, row[2]")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)) and data:
            row = {"effect_id": data[0]}
            if len(data) > 1:
                row["values"] = data[1]
            if len(data) > 2 and data[2] is not None:
                row["source"] = data[2]
            return row
        return data


class LeaderBase(BasePayload):
    """
    Fields shared by every gli entry.

    The wire protocol calls both kinds "lords" (command ``gli``, field ``LID``
    on movement commands); the game UI says commander and castellan.

    Client: ``LordFactory.createLord`` (bundle line 26399), ``LordVO.parseLord`` (bundle line 26451),
    ``LordVO.parseGeneral`` (bundle line 26480) and ``GeneralVO.parseData`` (bundle line 26666) for
    ``ST`` and ``L``.
    """

    commander_id: int = Field(alias="ID")
    wearer_id: int | None = Field(
        alias="WID", default=None, description="EquipmentConst wearer id: 2 builds a CommanderVO, 1 a BaronVO"
    )
    picture_id: int = Field(alias="VIS", default=0, description="Portrait id")
    name: str = Field(alias="N", default="")
    wins: int = Field(alias="W", default=0)
    defeats: int = Field(alias="D", default=0)
    win_spree: int = Field(alias="SPR", default=0)
    effects: list = Field(alias="E", default_factory=list)
    area_effects: list = Field(alias="AE", default_factory=list)
    raw_equipment: list = Field(alias="EQ", default_factory=list)
    general_id: int | None = Field(alias="GID", default=None)
    star_level: int = Field(alias="ST", default=0)
    level: int = Field(alias="L", default=0)

    def equipment(self) -> list[Equipment]:
        """Parse the EQ entries into Equipment objects, skipping drifted ones."""
        items: list[Equipment] = []
        for entry in self.raw_equipment:
            if not isinstance(entry, (list, tuple)):
                continue
            try:
                items.append(Equipment.from_list(list(entry)))
            except ValidationError:
                continue
        if skipped := len(self.raw_equipment) - len(items):
            logger.warning(
                f"Skipped {skipped}/{len(self.raw_equipment)} unparseable EQ entries for commander {self.commander_id}"
            )
        return items


class Commander(LeaderBase):
    """A commander - the leader assigned to an attack or support movement."""


class Castellan(LeaderBase):
    """A castellan - the defensive counterpart of a commander (``BaronVO``)."""


class GetCommandersRequest(BaseRequest):
    """
    Request the commander and castellan list.

    Command: gli
    Payload: {}
    """

    command = "gli"


class GetCommandersResponse(BaseResponse):
    """
    Response containing commanders (C) and castellans (B).

    Command: gli
    """

    command = "gli"

    commanders: list[Commander] = Field(alias="C", default_factory=list)
    castellans: list[Castellan] = Field(alias="B", default_factory=list)
