"""
Commander protocol models.

Commands:
- gli: Get Lords Info - the server name for the commander/castellan list
- arl: rename a commander or castellan
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Annotated, Any, TypeVar

from pydantic import (
    BeforeValidator,
    Field,
    ValidationError,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

from .base import BasePayload, BaseRequest, BaseResponse, ClientInt, client_int

logger = logging.getLogger(__name__)

NO_GEM_ID = -1

PICTURE_FACTION_CASTELLAN = 5
"""``EquipmentConst.PICK_BARON_FACTION`` (dll line 19249)"""
PICTURE_ISLAND_CASTELLAN = 13
"""``EquipmentConst.PICK_BARON_ISLAND`` (dll line 19249)"""
FACTION_BARON_ID = -16
"""``FactionConst.BARON_ID`` (dll line 19333)"""
ISLAND_KINGDOM_ID = 4
"""``WorldIsland.KINGDOM_ID`` (dll line 20036)"""


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
    """
    Origin of an equipment item.

    Client: ``EquipmentConst.EQUIPMENT_TYPE_ID_*`` (dll line 19249)
    """

    GENERATED = 0
    UNIQUE = 1
    UNIQUE_TEMPORARY = 2
    RELIC = 3


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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


_Row = TypeVar("_Row", bound=BasePayload)


def _parse_rows(model: type[_Row], value: Any) -> list[_Row]:
    if not isinstance(value, list):
        return []
    rows = []
    for entry in value:
        try:
            rows.append(model.model_validate(entry))
        except ValidationError:
            logger.debug(f"Ignoring unreadable {model.__name__} entry: {entry!r}")
    return rows


def _readable_rows(model: type[BasePayload]) -> Any:
    return BeforeValidator(lambda value: _parse_rows(model, value))


class RelicGem(BasePayload):
    """
    The gem set in a relic item: ``[gem_id, relic_type_id, relic_category_id, might, bonuses, enchantment_level]``.

    Client: ``RelicGemVO.parseServerObject`` (bundle line 22222)
    """

    gem_id: int = Field(description="row[0]")
    relic_type_id: int = Field(default=0, description="row[1]")
    relic_category_id: int = Field(default=0, description="row[2]")
    might: int | float = Field(default=0, description="row[3]")
    bonuses: Annotated[list[RelicBonus], _readable_rows(RelicBonus)] = Field(
        default_factory=list, description="row[4]; unreadable entries are skipped"
    )
    enchantment_level: ClientInt = Field(default=0, description="row[5], read through int()")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)) and data:
            keys = ("gem_id", "relic_type_id", "relic_category_id", "might", "bonuses", "enchantment_level")
            return dict(zip(keys, data, strict=False))
        return data


class RelicInfo(BasePayload):
    """
    What a relic item carries at index 12: ``[relic_type_id, relic_category_id, might, gem]``.

    Client: ``RelicEquipmentVO.parseEquipFromArray`` (bundle line 25039)
    """

    relic_type_id: int = Field(default=0, description="row[0]")
    relic_category_id: int = Field(default=0, description="row[1]")
    might: int | float = Field(default=0, description="row[2]")
    gem: RelicGem | None = Field(default=None, description="row[3]; None when no gem is set")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)):
            return dict(zip(("relic_type_id", "relic_category_id", "might", "gem"), data, strict=False))
        return data

    @field_validator("gem", mode="wrap")
    @classmethod
    def _gem_or_none(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> RelicGem | None:
        # The client builds a gem only from a non-empty row
        if not isinstance(value, list) or not value:
            return None
        try:
            return handler(value)
        except ValidationError:
            return None


class Equipment(BasePayload):
    """
    An equipment item worn by a commander or castellan.

    Parsed from a positional EQ entry:
    [id, slot, wearer, rarity, graphic, bonuses, unique_id, set_id,
     enchantment_level, duration_seconds, gem_id, equipment_type]
    Entries are truncated by the server when trailing fields do not apply.

    Index 5 holds the bonuses: a relic item (index 11 is 3) lists them as
    ``relic_bonuses`` (``[relic_effect_id, power, values]``), any other item as
    ``bonuses`` (``[effect_id, values]``). A hero item (slot 6, not a relic)
    also keeps index 11 as ``alien_string``; the type is still read from it
    through ``int()``.

    Client: ``BasicEquipmentVO.parseEquipFromArray`` (bundle line 7115),
    ``CastleEquipmentFactory.createEquipmentVO`` (bundle line 18134),
    ``RelicEquipmentVO.parseEquipFromArray`` (bundle line 25039),
    ``CastleHeroVO.parseEquipFromArray`` (bundle line 40585),
    ``BasicEquipmentVO.hasSetbonus`` (bundle line 7213).
    """

    equipment_id: int = 0
    slot: int = 0
    wearer_type: int = WearerType.ALL
    rarity_id: ClientInt = 0
    graphic: int | str = Field(default=0, description="The client keeps row[4] as its graphic string")
    bonuses: Annotated[list[EquipmentBonus], _readable_rows(EquipmentBonus)] = Field(
        default_factory=list, description="Bonuses of an item that is not a relic; unreadable entries are skipped"
    )
    relic_bonuses: Annotated[list[RelicBonus], _readable_rows(RelicBonus)] = Field(
        default_factory=list, description="Bonuses of a relic item; unreadable entries are skipped"
    )
    unique_id: ClientInt = 0
    set_id: ClientInt = Field(
        default=0,
        description=(
            "Equipment set id, -1 for none. The client leaves it undefined on a row shorter than 8, "
            "then counts it as set 0, which no set uses"
        ),
    )
    enchantment_level: ClientInt = 0
    duration_seconds: int | float = 0
    gem_id: ClientInt = NO_GEM_ID
    equipment_type: ClientInt = Field(
        default=EquipmentType.GENERATED, description="EquipmentType value, read through int() as the client does"
    )
    relic_info: RelicInfo | None = Field(
        default=None, description="A relic item's type, category, might and gem, index 12; None for other items"
    )
    alien_string: Any = Field(
        default=None,
        description=(
            "A hero item's index 11 as sent, which the client matches against an alien hero's "
            "'effect_id&value,...' string; None for other items"
        ),
    )

    @field_validator("relic_info", mode="wrap")
    @classmethod
    def _relic_info_or_none(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> RelicInfo | None:
        if not isinstance(value, list):
            return None
        try:
            return handler(value)
        except ValidationError:
            return None

    @property
    def is_permanent(self) -> bool:
        """True when the item does not expire (the server sends -1)."""
        return self.duration_seconds < 1

    @property
    def has_gem(self) -> bool:
        """True when a gem is slotted."""
        return self.gem_id != NO_GEM_ID

    @property
    def has_set(self) -> bool:
        """True unless ``set_id`` is -1, as the client's ``hasSetbonus`` reads it."""
        return self.set_id != -1

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
            if len(data) >= 13:
                row["relic_info"] = data[12]
        elif len(data) > 1 and _is_number(data[1]) and data[1] == EquipmentSlot.HERO:
            # CastleEquipmentFactory switches on row[1] with ===
            row["alien_string"] = data[11] if len(data) >= 12 else None
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

    @field_validator("source", mode="before")
    @classmethod
    def _source_key(cls, value: Any) -> Any:
        return value if isinstance(value, str) else ""

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

    ``AIE`` (alien) or ``TAE`` (temporary) equipment stands in for ``EQ``: the
    client reads the first of them that is present, and only when ``EQ`` is
    empty. See ``alien_bonuses``.

    Client: ``LordFactory.createLord`` (bundle line 26399), ``LordVO.parseLord`` (bundle line 26451),
    ``LordVO.parseGeneral`` (bundle line 26480) and ``GeneralVO.parseData`` (bundle line 26666) for
    ``ST`` and ``L``.
    """

    commander_id: int = Field(alias="ID", description="DLID for a default commander, else ID")
    wearer_id: ClientInt | None = Field(
        alias="WID", default=None, description="EquipmentConst wearer id: 2 builds a CommanderVO, 1 a BaronVO"
    )
    picture_id: ClientInt = Field(alias="VIS", default=0, description="Portrait id")
    name: str = Field(alias="N", default="")
    wins: ClientInt = Field(alias="W", default=0)
    defeats: ClientInt = Field(alias="D", default=0)
    win_spree: ClientInt = Field(alias="SPR", default=0)
    effects: CommanderEffects = Field(alias="E", default_factory=list, description="The commander's own effects")
    area_effects: CommanderEffects = Field(alias="AE", default_factory=list, description="Area effects")
    equipment: list[Equipment] = Field(
        alias="EQ", default_factory=list, description="Equipped items; entries that do not parse are skipped"
    )
    alien_equipment: list[Any] | None = Field(
        alias="AIE",
        default=None,
        description="Alien equipment: [effect_id, values] rows, or [hero_rows, equipment_rows]; used when EQ is empty",
    )
    temporary_equipment: list[Any] | None = Field(
        alias="TAE",
        default=None,
        description="Temporary equipment, same layout as AIE; used when EQ and AIE are absent",
    )
    alien_gem_ids: list[Any] = Field(
        alias="GEM", default_factory=list, description="Gem ids the client adds to the AIE/TAE equipment"
    )
    general_id: ClientInt | None = Field(alias="GID", default=None)
    star_level: ClientInt = Field(
        alias="ST",
        default=0,
        description="Read by the client only when the entry doubles as its general: GID > 0 on a default commander",
    )
    level: ClientInt = Field(
        alias="L",
        default=0,
        description="Read by the client only when the entry doubles as its general: GID > 0 on a default commander",
    )

    @model_validator(mode="before")
    @classmethod
    def _id_as_the_client_reads_it(cls, data: Any) -> Any:
        # Client: LordFactory.createLord reads int(e.DLID||e.ID); LordVO.parseLord takes N as it comes
        if isinstance(data, dict):
            data = dict(data)
            if data.get("DLID"):
                data["ID"] = data["DLID"]
            if not isinstance(data.get("N", ""), str):
                data.pop("N")
        return data

    @field_validator("alien_equipment", "temporary_equipment", mode="before")
    @classmethod
    def _alien_block(cls, value: Any) -> Any:
        return value if isinstance(value, list) else None

    @field_validator("alien_gem_ids", mode="before")
    @classmethod
    def _gem_list(cls, value: Any) -> Any:
        return value if isinstance(value, list) else []

    def _alien_rows(self) -> tuple[list[Any], list[Any]]:
        block = self.alien_equipment if self.alien_equipment is not None else self.temporary_equipment
        if self.equipment or block is None:
            return [], []
        if len(block) == 2 and all(
            isinstance(part, list) and (not part or isinstance(part[0], list)) for part in block
        ):
            return block[0], block[1]
        return [], block

    @property
    def alien_hero_bonuses(self) -> list[EquipmentBonus]:
        """
        The hero half of ``AIE``/``TAE`` when it is sent as ``[hero_rows, equipment_rows]``.

        Client: ``LordVO.parseLord`` (bundle line 26451), ``AlienLordHeroVO.parseAlienBoniData``
        (bundle line 67502)
        """
        return _parse_rows(EquipmentBonus, self._alien_rows()[0])

    @property
    def alien_bonuses(self) -> list[EquipmentBonus]:
        """
        The equipment bonuses of ``AIE``/``TAE``, empty when ``EQ`` has items.

        Client: ``LordVO.parseLord`` (bundle line 26451), ``AlienLordEquipmentVO.parseAlienBoniData``
        (bundle line 67479)
        """
        return _parse_rows(EquipmentBonus, self._alien_rows()[1])

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
    """
    A castellan - the defensive counterpart of a commander (``BaronVO``).

    Client: ``BaronVO.parseLord`` (bundle line 43534)
    """

    locked_in_castle_id: ClientInt = Field(
        alias="LICID",
        default=0,
        description="Castle the castellan is locked in, -1 for none; read through int(), so a missing key is 0",
    )

    @property
    def is_locked_in_castle(self) -> bool:
        """True when ``locked_in_castle_id`` is 0 or more."""
        return self.locked_in_castle_id >= 0

    def is_available_for_movement(self, kingdom_id: int) -> bool:
        """
        Whether the client offers this castellan for a movement in ``kingdom_id``.

        Not when it is locked in a castle. A faction-portrait castellan (``VIS`` 5) is
        compared with ``FactionConst.BARON_ID`` (-16), not a kingdom id, so it is never
        available in a real kingdom; an island-portrait one (``VIS`` 13) only in the
        storm islands (4). The client also refuses a castellan that already leads one of
        the player's movements, which this model cannot see.

        Client: ``BaronVO.isAvailableForMovement`` (bundle line 43535),
        ``LordVO.isAvailableForMovement`` (bundle line 26607)
        """
        if self.is_locked_in_castle:
            return False
        if self.picture_id == PICTURE_FACTION_CASTELLAN and kingdom_id != FACTION_BARON_ID:
            return False
        return not (self.picture_id == PICTURE_ISLAND_CASTELLAN and kingdom_id != ISLAND_KINGDOM_ID)


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

    @model_validator(mode="before")
    @classmethod
    def _no_block(cls, data: Any) -> Any:
        # parse_GLI does nothing without a block
        return {} if data is None else data

    @field_validator("commanders", "castellans", mode="before")
    @classmethod
    def _readable_entries(cls, value: Any, info: ValidationInfo) -> Any:
        if not isinstance(value, list):
            return []
        model = Commander if info.field_name == "commanders" else Castellan
        entries = []
        for entry in value:
            if entry is None:
                continue
            try:
                entries.append(model.model_validate(entry))
            except ValidationError:
                logger.warning(f"Skipped a gli entry that could not be read: {entry!r}")
        return entries


class GetCommandersResponse(BaseResponse, CommanderRoster):
    """
    Response containing commanders (C) and castellans (B).

    Command: gli
    """

    command = "gli"


class RenameCommanderRequest(BaseRequest):
    """
    Rename a commander or castellan.

    Command: arl
    Payload: {"LID": commander_id, "N": name}

    The game's dialog allows 3 to 15 characters (``EquipmentConst.LORD_NAME_MIN_LENGTH``
    and ``LORD_NAME_MAX_LENGTH``, dll line 19249); the server's own rules were not traced.

    Client: ``C2SRenameLordVO`` (bundle line 65748), sent by ``CastleRenameLordDialog.sendCommand``
    (bundle line 65738)
    """

    command = "arl"

    commander_id: int = Field(alias="LID", description="ID of the commander or castellan")
    name: str = Field(alias="N")


class RenameCommanderResponse(BaseResponse):
    """
    Reply to a rename: the full commander and castellan list.

    Command: arl

    Client: ``ARLCommand.executeCommand`` (bundle line 123657), which passes ``gli`` to
    ``CastleLordData.parse_GLI``
    """

    command = "arl"

    commander_roster: CommanderRoster = Field(
        alias="gli", default_factory=CommanderRoster, description="Commanders and castellans after the rename"
    )
