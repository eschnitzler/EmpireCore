"""Equipment models and equipment inventory commands.

Commands:
- gei: Get Equipment Inventory - the items no commander or castellan wears
- eeq: Equip Equipment - put an item on a commander or castellan, or take it off
"""

from __future__ import annotations

import logging
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BeforeValidator, Field, ValidatorFunctionWrapHandler, field_validator, model_validator

from empire_core.enums import EquipmentSlot, EquipmentType, Rareness, WearerType
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, enum_or_none, read_or_none, readable_list
from empire_core.protocol.js import ClientInt, js_int, js_string

if TYPE_CHECKING:
    from empire_core.gamedata import Gem

logger = logging.getLogger(__name__)


NO_GEM_ID = -1


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
    also keeps index 11 as ``alien_string``, which the client matches against the
    unique heroes (``CastleEquipmentData.getUniqueHerosByAlienString``, bundle
    line 143843); the type is still read from it through ``int()``.

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
    gem_id: EnumOrInt["Gem"] | None = Field(default=None, description="The slotted gem; None for none")
    equipment_type: ClientInt = Field(default=EquipmentType.GENERATED, description="EquipmentType value")
    relic_info: RelicInfo | None = Field(
        default=None, description="A relic item's type, category, might and gem; None for other items"
    )
    alien_string: str | None = Field(
        default=None,
        description=(
            'A hero item\'s alien string, "effect_id&value" pairs joined by ","; None for other items.'
            " A number the server sends there is kept as its text"
        ),
    )

    @field_validator("relic_info", mode="wrap")
    @classmethod
    def _relic_info_or_none(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> RelicInfo | None:
        if not isinstance(value, list):
            return None
        return read_or_none(handler, value)

    @field_validator("gem_id", mode="before")
    @classmethod
    def _gem(cls, value: Any) -> Any:
        # Client: int(e[10]), a gem unless NO_GEM_ID (BasicEquipmentVO.parseEquipFromArray, bundle lines 7116-7117)
        gem_id = js_int(value)
        return None if gem_id == NO_GEM_ID else gem_id

    @field_validator("alien_string", mode="before")
    @classmethod
    def _alien_text(cls, value: Any) -> Any:
        # getUniqueHerosByAlienString compares it with == to the text it builds (bundle lines 67506, 143847)
        return None if value is None else js_string(value)

    @property
    def is_permanent(self) -> bool:
        """True when the item does not expire (the server sends -1)."""
        return self.duration_seconds < 1

    @property
    def has_gem(self) -> bool:
        """True when a gem is slotted."""
        return self.gem_id is not None

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
    def from_list(cls, data: list[Any]) -> "Equipment":
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


class GetEquipmentInventoryRequest(BaseRequest):
    """
    Request the player's equipment inventory.

    Command: gei
    Payload: {}
    Client: ``C2SGetEquipmentInventory`` (bundle line 19854)
    """

    command = "gei"


class GetEquipmentInventoryResponse(BaseResponse):
    """
    The player's equipment inventory.

    Command: gei
    Payload: {"I": [EQ entry, ...]}, each entry laid out as a ``gli`` ``EQ`` entry.

    Client: ``CastleEquipmentData.parse_GEI`` (bundle line 143731), which builds every
    entry with ``CastleEquipmentFactory.createEquipmentVO`` (bundle line 18134).
    """

    command = "gei"

    items: list[Equipment] = Field(
        validation_alias="I",
        serialization_alias="I",
        default_factory=list,
        description="Inventory items",
    )

    @field_validator("items", mode="before")
    @classmethod
    def _readable_items(cls, value: Any) -> Any:
        return readable_list(
            Equipment,
            value,
            accept=lambda entry: isinstance(entry, (list, tuple)),
            parse=lambda entry: Equipment.from_list(list(entry)),
            warn=logger,
            what="gei entries",
        )


class EquipEquipmentRequest(BaseRequest):
    """
    Put an item on a commander or castellan (``equip=1``), or take it off (``equip=0``).

    Moving an item between two leaders takes two requests: the client takes it
    off the first, then puts it on the second. The reply has no body.

    Command: eeq
    Payload: {"EID": equipment_id, "LID": commander_id, "E": 0 or 1}
    Client: ``C2SEquipEquipmentVO`` (bundle line 143914) sends ``E`` as ``int(n?1:0)``;
    ``CastleEquipmentData.startDrag`` (bundle line 143801) sends 0 when an item is
    lifted off a leader's slot, ``stopDrag`` (bundle line 143807) sends 1 when it is
    dropped on one, and ``EquipmentEquipmentClickHandler.init`` (bundle line 65626)
    handles the 0 reply as an unequip.
    """

    command = "eeq"

    equipment_id: int = Field(
        validation_alias="EID",
        serialization_alias="EID",
        description=(
            "Equipment.equipment_id: of an inventory item from client.equipment.get_inventory() to "
            "equip, of a worn one from client.commanders.get_all() to take off"
        ),
    )
    commander_id: int = Field(
        validation_alias="LID",
        serialization_alias="LID",
        description="The commander_id of a Commander or Castellan from client.commanders.get_all()",
    )
    equip: int = Field(
        validation_alias="E", serialization_alias="E", description="1 puts the item on the leader, 0 takes it off"
    )

    @field_validator("equip", mode="before")
    @classmethod
    def _as_flag(cls, value: Any) -> int:
        return 1 if value else 0
