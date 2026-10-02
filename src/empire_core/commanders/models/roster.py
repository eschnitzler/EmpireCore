"""Commander protocol models.

Commands:
- gli: Get Lords Info - the server name for the commander/castellan list
- arl: rename a commander or castellan
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, PrivateAttr, ValidationInfo, field_validator, model_validator
from pydantic.functional_validators import ModelWrapValidatorHandler

from empire_core.enums import EquipmentSlot, Kingdom
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, list_or_empty, readable_list
from empire_core.protocol.js import ClientInt, js_loose_equals, js_truthy

from .equipment import Equipment, EquipmentBonus

logger = logging.getLogger(__name__)


PICTURE_FACTION_CASTELLAN = 5
"""``EquipmentConst.PICK_BARON_FACTION`` (dll line 19249)"""


PICTURE_ISLAND_CASTELLAN = 13
"""``EquipmentConst.PICK_BARON_ISLAND`` (dll line 19249)"""


FACTION_BARON_ID = -16
"""``FactionConst.BARON_ID`` (dll line 19333)"""


CASTELLAN_PICTURE_ORDER = (0, 6, 7, 8, 1, 13, 2, 3, 4, 10, 11, 12, 9, 5)
"""``BaronVO.PIC_ID_ORDER`` (bundle line 43551): castellans are listed in this portrait order"""


_SLOT_ORDER = (
    EquipmentSlot.HELMET,
    EquipmentSlot.ARMOR,
    EquipmentSlot.WEAPON,
    EquipmentSlot.ARTIFACT,
    EquipmentSlot.SKIN,
    EquipmentSlot.HERO,
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
    ``ST``, ``L`` and the general's ``XP``, ``OXP``, ``IN``, ``LU``, ``SIDS`` and ``GASAIDS``. The
    client reads those six only when the entry names a general above 0 and is a default commander
    or was created with ``LordFactory.createLord(e, true)``, as a battle log's are. An entry cannot
    tell the second case, so they are None unless sent, or filled with the client's defaults for a
    default commander with a general; elsewhere the client ignores them.
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
    general_xp: ClientInt | None = Field(
        alias="XP", default=None, description="The general's experience; None when the entry does not carry it"
    )
    general_old_xp: ClientInt | None = Field(
        alias="OXP",
        default=None,
        description="The general's experience before the battle; None when the entry does not carry it",
    )
    general_is_new: bool | None = Field(
        alias="IN", default=None, description="The general is newly unlocked; None when the entry does not say"
    )
    general_has_level_up: bool | None = Field(
        alias="LU", default=None, description="The general gained a level; None when the entry does not say"
    )
    general_skill_ids: list[Any] | None = Field(
        alias="SIDS", default=None, description="The general's unlocked skill ids; None when the entry has none"
    )
    general_ability_ids: list[Any] | None = Field(
        alias="GASAIDS",
        default=None,
        description="The general's selected slot and ability ids, as sent; None when the entry has none",
    )

    @field_validator("general_xp", "general_old_xp", mode="before")
    @classmethod
    def _xp_or_zero(cls, value: Any) -> Any:
        # GeneralVO.parseData: e.XP||0, e.OXP||0
        return value if js_truthy(value) else 0

    @field_validator("general_is_new", "general_has_level_up", mode="before")
    @classmethod
    def _one_flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @field_validator("general_skill_ids", "general_ability_ids", mode="before")
    @classmethod
    def _id_list(cls, value: Any) -> Any:
        return list_or_empty(value)

    @model_validator(mode="after")
    def _default_commander_general(self) -> LeaderBase:
        # A default commander with a general always goes through GeneralVO.parseData
        if self.commander_id < 0 and (self.general_id or 0) > 0:
            for name, default in (
                ("general_xp", 0),
                ("general_old_xp", 0),
                ("general_is_new", False),
                ("general_has_level_up", False),
                ("general_skill_ids", []),
                ("general_ability_ids", []),
            ):
                if getattr(self, name) is None:
                    setattr(self, name, default)
        return self

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

    The lists are in the client's order: commanders by ``commander_id``, castellans
    by their portrait's place in :data:`CASTELLAN_PICTURE_ORDER`, an unlisted portrait first.

    Client: ``CastleLordData.parse_GLI`` (bundle line 38553), ``onSortLord`` and ``onSortBaron``
    (bundle lines 38572-38573), ``BaronVO.parseLord`` (bundle line 43534)
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

    @model_validator(mode="after")
    def _client_order(self) -> CommanderRoster:
        self.commanders.sort(key=lambda commander: commander.commander_id)
        self.castellans.sort(key=lambda castellan: _castellan_place(castellan.picture_id))
        return self


def _castellan_place(picture_id: int) -> int:
    return CASTELLAN_PICTURE_ORDER.index(picture_id) if picture_id in CASTELLAN_PICTURE_ORDER else -1


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
