"""
Commander protocol models.

Commands:
- gli: Get Lords Info - the server name for the commander/castellan list
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, ValidationError, ValidationInfo, field_validator, model_validator

from .base import BasePayload, BaseRequest, BaseResponse, ClientInt, client_int

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


def _wrapped(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


class EquipmentBonus(BasePayload):
    """
    One bonus of an item that is not a relic: ``[effect_id, values]``.

    Client: ``BasicEquipmentVO.parseBonuses`` (bundle line 7135), which wraps a
    value that is not an array into one.
    """

    effect_id: int = Field(description="Equipment effect id, row[0]")
    values: list[Any] = Field(
        default_factory=list,
        description="Value array, row[1]; its layout depends on the effect type's EffectValue class",
    )

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)) and data:
            return {"effect_id": data[0], "values": _wrapped(data[1] if len(data) > 1 else None)}
        return data


class RelicBonus(BasePayload):
    """
    One bonus of a relic item: ``[relic_effect_id, power, values]``.

    Client: ``RelicItemInfoVO.parseRelicBoni`` (bundle line 33743),
    ``RelicBonusVO.parseRelicFromValueArray`` (bundle line 45132), which looks the
    id up in the relic effect table and parses ``row[2].toString()``, so a value
    and a one-value array read the same.
    """

    relic_effect_id: int = Field(description="Relic effect id, row[0]")
    power: float = Field(default=0, description="row[1]")
    values: list[Any] = Field(default_factory=list, description="Value array, row[2]")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)) and data:
            row: dict[str, Any] = {"relic_effect_id": data[0]}
            if len(data) > 1:
                row["power"] = data[1]
            if len(data) > 2:
                row["values"] = _wrapped(data[2])
            return row
        return data


def _readable_rows(model: type[BasePayload]) -> Any:
    def parse(value: Any) -> Any:
        if not isinstance(value, list):
            return []
        rows = []
        for entry in value:
            try:
                rows.append(model.model_validate(entry))
            except ValidationError:
                logger.debug(f"Ignoring unreadable {model.__name__} entry: {entry!r}")
        return rows

    return BeforeValidator(parse)


class Equipment(BasePayload):
    """
    An equipment item worn by a commander or castellan.

    Parsed from a positional EQ entry:
    [id, slot, wearer, rarity, graphic, bonuses, unique_id, set_id,
     enchantment_level, duration_seconds, gem_id, equipment_type]
    Entries are truncated by the server when trailing fields do not apply.

    Index 5 holds the bonuses: a relic item (index 11 is 3) lists them as
    ``relic_bonuses``, any other item as ``bonuses``. A hero item's
    ``CastleHeroVO`` also keeps index 11 as its ``alienString``; the type is
    still read from it through ``int()``.

    Client: ``BasicEquipmentVO.parseEquipFromArray`` (bundle line 7115),
    ``CastleEquipmentFactory.createEquipmentVO`` (bundle line 18134),
    ``RelicEquipmentVO.parseEquipFromArray`` (bundle line 25039),
    ``CastleHeroVO.parseEquipFromArray`` (bundle line 40585).
    """

    equipment_id: int = 0
    slot: int = 0
    wearer_type: int = WearerType.ALL
    rarity_id: int = 0
    graphic: int = 0
    bonuses: Annotated[list[EquipmentBonus], _readable_rows(EquipmentBonus)] = Field(
        default_factory=list, description="Bonuses of an item that is not a relic; unreadable entries are skipped"
    )
    relic_bonuses: Annotated[list[RelicBonus], _readable_rows(RelicBonus)] = Field(
        default_factory=list, description="Bonuses of a relic item; unreadable entries are skipped"
    )
    unique_id: ClientInt = 0
    set_id: int = 0
    enchantment_level: ClientInt = 0
    duration_seconds: int = 0
    gem_id: ClientInt = NO_GEM_ID
    equipment_type: ClientInt = Field(
        default=EquipmentType.GENERATED, description="EquipmentType value, read through int() as the client does"
    )

    @property
    def is_permanent(self) -> bool:
        """True when the item does not expire (the server sends -1)."""
        return self.duration_seconds < 1

    @property
    def has_gem(self) -> bool:
        """True when a gem is slotted."""
        return self.gem_id != NO_GEM_ID

    @property
    def is_relic(self) -> bool:
        """True for a relic item, whose bonuses index the relic effect table."""
        return self.equipment_type == EquipmentType.RELIC

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, (list, tuple)):
            return data
        row = dict(zip(_EQUIPMENT_ROW, data, strict=False))
        if len(data) >= 12 and client_int(data[11]) == EquipmentType.RELIC:
            row["relic_bonuses"] = row.pop("bonuses", [])
        return row

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


CommanderEffects = Annotated[list[CommanderEffect], _readable_rows(CommanderEffect)]
"""``[effect_id, values, source]`` rows; unreadable entries are skipped, as the client skips
effects it cannot resolve (``LordVO.parseRawEffects``, bundle line 26483)."""


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
    effects: CommanderEffects = Field(alias="E", default_factory=list, description="The commander's own effects")
    area_effects: CommanderEffects = Field(alias="AE", default_factory=list, description="Area effects")
    equipment: list[Equipment] = Field(
        alias="EQ", default_factory=list, description="Equipped items; entries that do not parse are skipped"
    )
    general_id: int | None = Field(alias="GID", default=None)
    star_level: int = Field(alias="ST", default=0)
    level: int = Field(alias="L", default=0)

    @field_validator("equipment", mode="before")
    @classmethod
    def _readable_equipment(cls, value: Any, info: ValidationInfo) -> Any:
        """Client: ``LordVO.parseLord`` (bundle line 26451) builds an item from every EQ entry."""
        if not isinstance(value, list):
            return []
        items: list[Equipment] = []
        for entry in value:
            if isinstance(entry, Equipment):
                items.append(entry)
                continue
            if not isinstance(entry, (list, tuple)):
                continue
            try:
                items.append(Equipment.from_list(list(entry)))
            except ValidationError:
                continue
        if skipped := len(value) - len(items):
            logger.warning(
                f"Skipped {skipped}/{len(value)} unparseable EQ entries for commander {info.data.get('commander_id')}"
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


class CommanderRoster(BasePayload):
    """
    A player's commanders and castellans, the ``gli`` block.

    Client: ``CastleLordData.parse_GLI`` (bundle line 38553)
    """

    commanders: list[Commander] = Field(alias="C", default_factory=list, description="Commanders, as CommanderVO")
    castellans: list[Castellan] = Field(alias="B", default_factory=list, description="Castellans, as BaronVO")


class GetCommandersResponse(BaseResponse, CommanderRoster):
    """
    Response containing commanders (C) and castellans (B).

    Command: gli
    """

    command = "gli"
