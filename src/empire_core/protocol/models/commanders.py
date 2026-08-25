"""
Commander protocol models.

Commands:
- gli: Get Lords Info - the server name for the commander/castellan list
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import Field

from .base import BasePayload, BaseRequest, BaseResponse

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

    @classmethod
    def from_list(cls, data: list) -> "Equipment":
        """Parse from an EQ array entry, tolerating short entries."""
        size = len(data)
        return cls(
            equipment_id=data[0] if size > 0 else 0,
            slot=data[1] if size > 1 else 0,
            wearer_type=data[2] if size > 2 else WearerType.ALL,
            rarity_id=data[3] if size > 3 else 0,
            graphic=data[4] if size > 4 else 0,
            bonuses=data[5] if size > 5 else [],
            unique_id=data[6] if size > 6 else 0,
            set_id=data[7] if size > 7 else 0,
            enchantment_level=data[8] if size > 8 else 0,
            duration_seconds=data[9] if size > 9 else 0,
            gem_id=data[10] if size > 10 else NO_GEM_ID,
            equipment_type=data[11] if size > 11 else EquipmentType.GENERATED,
        )


class LeaderBase(BasePayload):
    """
    Fields shared by every gli entry.

    The wire protocol calls both kinds "lords" (command ``gli``, field ``LID``
    on movement commands); the game UI says commander and castellan.
    """

    commander_id: int = Field(alias="ID")
    name: str = Field(alias="N", default="")
    wins: int = Field(alias="W", default=0)
    defeats: int = Field(alias="D", default=0)
    win_spree: int = Field(alias="SPR", default=0)
    effects: list = Field(alias="E", default_factory=list)
    area_effects: list = Field(alias="AE", default_factory=list)
    raw_equipment: list = Field(alias="EQ", default_factory=list)

    def equipment(self) -> list[Equipment]:
        """Parse the EQ entries into Equipment objects."""
        return [Equipment.from_list(entry) for entry in self.raw_equipment]


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
