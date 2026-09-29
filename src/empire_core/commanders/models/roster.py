"""
Commander protocol models.

Commands:
- gli: Get Lords Info - the server name for the commander/castellan list
- arl: rename a commander or castellan
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Annotated, Any

from pydantic import (
    BeforeValidator,
    Field,
    PrivateAttr,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)
from pydantic.functional_validators import ModelWrapValidatorHandler

from empire_core.enums import EquipmentSlot, EquipmentType, Kingdom, Rareness, WearerType
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    enum_or_none,
    list_or_empty,
    read_or_none,
    readable_list,
)
from empire_core.protocol.js import ClientInt, js_int

logger = logging.getLogger(__name__)

NO_GEM_ID = -1

PICTURE_FACTION_CASTELLAN = 5
"""``EquipmentConst.PICK_BARON_FACTION`` (dll line 19249)"""
PICTURE_ISLAND_CASTELLAN = 13
"""``EquipmentConst.PICK_BARON_ISLAND`` (dll line 19249)"""
FACTION_BARON_ID = -16
"""``FactionConst.BARON_ID`` (dll line 19333)"""


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

    effect_id: int = Field(description="Equipment effect id")
    values: list[Any] = Field(
        default_factory=list,
        description="Value array; its layout depends on the effect type",
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

    relic_effect_id: int = Field(description="Relic effect id")
    power: float = Field(default=0, description="Power")
    values: list[Any] = Field(default_factory=list, description="Value array")

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


class RelicGem(BasePayload):
    """
    The gem set in a relic item: ``[gem_id, relic_type_id, relic_category_id, might, bonuses, enchantment_level]``.

    Client: ``RelicGemVO.parseServerObject`` (bundle line 22222)
    """

    gem_id: int = Field(description="Gem id")
    relic_type_id: int = Field(default=0, description="Relic type id")
    relic_category_id: int = Field(default=0, description="Relic category id")
    might: int | float = Field(default=0, description="Might")
    bonuses: Annotated[list[RelicBonus], BeforeValidator(partial(readable_list, RelicBonus))] = Field(
        default_factory=list, description="The gem's relic bonuses"
    )
    enchantment_level: ClientInt = Field(default=0, description="Enchantment level")

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

    relic_type_id: int = Field(default=0, description="Relic type id")
    relic_category_id: int = Field(default=0, description="Relic category id")
    might: int | float = Field(default=0, description="Might")
    gem: RelicGem | None = Field(default=None, description="The gem set in the relic; None when there is none")

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
        return read_or_none(handler, value)


_SLOT_ORDER = (
    EquipmentSlot.HELMET,
    EquipmentSlot.ARMOR,
    EquipmentSlot.WEAPON,
    EquipmentSlot.ARTIFACT,
    EquipmentSlot.SKIN,
    EquipmentSlot.HERO,
)


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

    equipment_id: int = Field(default=0, description="Item id")
    slot: int = Field(default=0, description="Slot type id")
    wearer_type: int = Field(default=WearerType.UNDEFINED, description="Who can wear it (WearerType)")
    rarity_id: ClientInt = Field(default=0, description="Rarity id")
    graphic: int | str = Field(default=0, description="The item's graphic")
    bonuses: Annotated[list[EquipmentBonus], BeforeValidator(partial(readable_list, EquipmentBonus))] = Field(
        default_factory=list, description="Bonuses of an item that is not a relic"
    )
    relic_bonuses: Annotated[list[RelicBonus], BeforeValidator(partial(readable_list, RelicBonus))] = Field(
        default_factory=list, description="Bonuses of a relic item"
    )
    unique_id: ClientInt = Field(default=0, description="Unique item id")
    set_id: ClientInt = Field(
        default=0,
        description="Equipment set id, -1 for none; 0, which no set uses, when the row has none",
    )
    enchantment_level: ClientInt = Field(default=0, description="Enchantment level")
    duration_seconds: int | float = Field(
        default=0, description="Seconds until the item expires; below 1 it is permanent"
    )
    gem_id: ClientInt = Field(default=NO_GEM_ID, description="Slotted gem id; -1 for none")
    equipment_type: ClientInt = Field(default=EquipmentType.GENERATED, description="EquipmentType value")
    relic_info: RelicInfo | None = Field(
        default=None, description="A relic item's type, category, might and gem; None for other items"
    )
    alien_string: Any = Field(
        default=None,
        description="A hero item's alien string; None for other items",
    )

    @field_validator("relic_info", mode="wrap")
    @classmethod
    def _relic_info_or_none(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> RelicInfo | None:
        if not isinstance(value, list):
            return None
        return read_or_none(handler, value)

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

    @property
    def rarity_enum(self) -> Rareness | None:
        """``rarity_id`` as a :class:`Rareness`, None for a value the client does not define."""
        return enum_or_none(Rareness, self.rarity_id)

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, (list, tuple)):
            return data
        row = dict(zip(_EQUIPMENT_ROW, data, strict=False))
        if len(data) >= 12 and js_int(data[11]) == EquipmentType.RELIC:
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

    effect_id: int = Field(description="Effect id")
    values: list[Any] = Field(
        default_factory=list,
        description="Value array; its layout depends on the effect type",
    )
    source: str = Field(default="", description="The key of the effect's source")

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


CommanderEffects = Annotated[list[CommanderEffect], BeforeValidator(partial(readable_list, CommanderEffect))]
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

    commander_id: int = Field(alias="ID", description="Commander id; for a default commander, its default-commander id")
    wearer_id: ClientInt | None = Field(alias="WID", default=None, description="2 for a commander, 1 for a castellan")
    picture_id: ClientInt = Field(alias="VIS", default=0, description="Portrait id")
    name: str = Field(alias="N", default="", description="Name")
    wins: ClientInt = Field(alias="W", default=0, description="Battles won")
    defeats: ClientInt = Field(alias="D", default=0, description="Battles lost")
    win_spree: ClientInt = Field(alias="SPR", default=0, description="Current winning streak")
    effects: CommanderEffects = Field(alias="E", default_factory=list, description="The commander's own effects")
    area_effects: CommanderEffects = Field(alias="AE", default_factory=list, description="Area effects")
    equipment: list[Equipment] = Field(alias="EQ", default_factory=list, description="Equipped items")
    alien_equipment: list[Any] | None = Field(
        alias="AIE",
        default=None,
        description=(
            "Alien equipment: [effect_id, values] rows, or [hero_rows, equipment_rows]; applies when equipment is empty"
        ),
    )
    temporary_equipment: list[Any] | None = Field(
        alias="TAE",
        default=None,
        description=(
            "Temporary equipment, same layout as alien_equipment; applies when equipment and alien_equipment are absent"
        ),
    )
    alien_gem_ids: list[Any] = Field(
        alias="GEM", default_factory=list, description="Gem ids added to the alien or temporary equipment"
    )
    general_id: ClientInt | None = Field(
        alias="GID", default=None, description="The assigned general's id; -1 or None for none"
    )
    star_level: ClientInt = Field(
        alias="ST",
        default=0,
        description=(
            "The general's star level when the entry doubles as its general: a default commander with"
            " a general_id above 0"
        ),
    )
    level: ClientInt = Field(
        alias="L",
        default=0,
        description=(
            "The general's level when the entry doubles as its general: a default commander with a general_id above 0"
        ),
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
        return list_or_empty(value)

    _equipment_sent: bool = PrivateAttr(default=False)

    @model_validator(mode="wrap")
    @classmethod
    def _note_raw_equipment(cls, data: Any, handler: ModelWrapValidatorHandler[LeaderBase]) -> LeaderBase:
        # parseLord takes AIE/TAE only when !(e.EQ && e.EQ.length > 0), counting rows that do not parse
        model = handler(data)
        if isinstance(data, dict):
            model._equipment_sent = isinstance(data.get("EQ"), list) and len(data["EQ"]) > 0
        else:
            model._equipment_sent = bool(model.equipment)
        return model

    @property
    def uses_alien_equipment(self) -> bool:
        """Whether ``AIE``/``TAE`` stand in for an empty ``EQ``, as ``LordVO.parseLord`` decides."""
        block = self.alien_equipment if self.alien_equipment is not None else self.temporary_equipment
        return block is not None and not self._equipment_sent

    def worn_items(self) -> list[Equipment]:
        """
        The items the client puts in the commander's slots, in slot order.

        ``LordVO.parseLord`` (bundle line 26451) creates the helmet, armor, weapon,
        artifact, skin and hero slots in that order and puts each ``EQ`` item in
        its slot by ``row[1]``, so a later item replaces an earlier one and an item
        for any other slot is not worn.
        """
        by_slot = {item.slot: item for item in self.equipment if item.slot in _SLOT_ORDER}
        return [by_slot[slot] for slot in _SLOT_ORDER if slot in by_slot]

    def _alien_rows(self) -> tuple[list[Any], list[Any]]:
        block = self.alien_equipment if self.alien_equipment is not None else self.temporary_equipment
        if not self.uses_alien_equipment or block is None:
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
        return readable_list(EquipmentBonus, self._alien_rows()[0])

    @property
    def alien_bonuses(self) -> list[EquipmentBonus]:
        """
        The equipment bonuses of ``AIE``/``TAE``, empty when ``EQ`` has items.

        Client: ``LordVO.parseLord`` (bundle line 26451), ``AlienLordEquipmentVO.parseAlienBoniData``
        (bundle line 67479)
        """
        return readable_list(EquipmentBonus, self._alien_rows()[1])

    @field_validator("equipment", mode="before")
    @classmethod
    def _readable_equipment(cls, value: Any, info: ValidationInfo) -> Any:
        """Client: ``LordVO.parseLord`` (bundle line 26451) builds an item from every EQ entry."""
        return readable_list(
            Equipment,
            value,
            accept=lambda entry: isinstance(entry, (list, tuple)),
            parse=lambda entry: Equipment.from_list(list(entry)),
            warn=logger,
            what=f"EQ entries for commander {info.data.get('commander_id')}",
        )


class Commander(LeaderBase):
    """
    A commander - the leader assigned to an attack or support movement.

    Client: ``CommanderVO``, built by ``LordFactory.createLord`` (bundle line 26399)
    """


class Castellan(LeaderBase):
    """
    A castellan - the defensive counterpart of a commander (``BaronVO``).

    Client: ``BaronVO.parseLord`` (bundle line 43534)
    """

    locked_in_castle_id: ClientInt = Field(
        alias="LICID",
        default=0,
        description="Castle the castellan is locked in, -1 for none; 0 when the entry has none",
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
        return not (self.picture_id == PICTURE_ISLAND_CASTELLAN and kingdom_id != Kingdom.STORM)


class GetCommandersRequest(BaseRequest):
    """
    Request the commander and castellan list.

    Command: gli
    Payload: {}

    Client: ``C2SGetLordsInfoVO`` (bundle line 32779, no fields)
    """

    command = "gli"


class CommanderRoster(BasePayload):
    """
    A player's commanders and castellans, the ``gli`` block.

    Client: ``CastleLordData.parse_GLI`` (bundle line 38553)
    """

    commanders: list[Commander] = Field(alias="C", default_factory=list, description="Commanders")
    castellans: list[Castellan] = Field(alias="B", default_factory=list, description="Castellans")

    @model_validator(mode="before")
    @classmethod
    def _no_block(cls, data: Any) -> Any:
        # parse_GLI does nothing without a block
        return {} if data is None else data

    @field_validator("commanders", "castellans", mode="before")
    @classmethod
    def _readable_entries(cls, value: Any, info: ValidationInfo) -> Any:
        model = Commander if info.field_name == "commanders" else Castellan
        return readable_list(model, value, warn=logger, what="gli entries")


class GetCommandersResponse(BaseResponse, CommanderRoster):
    """
    Response containing commanders (C) and castellans (B).

    Command: gli

    Client: ``GLICommand.executeCommand`` (bundle line 123976) hands it to
    ``CastleLordData.parse_GLI``
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

    commander_id: int = Field(
        alias="LID",
        description="The commander_id of a Commander or Castellan from client.commanders.get_all()",
    )
    name: str = Field(alias="N", description="The new name; the game allows 3 to 15 characters")


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
