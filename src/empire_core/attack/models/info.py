"""Attack pre-calculation for a castle.

Commands:
- aci: Attack pre-calculation
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import Field, PrivateAttr, ValidatorFunctionWrapHandler, field_validator, model_validator
from pydantic.functional_validators import ModelWrapValidatorHandler

from empire_core.army.models.units import UnitInventory
from empire_core.army.spy_army import SpyArmyBlock
from empire_core.commanders.models.roster import Commander, CommanderRoster
from empire_core.enums import Kingdom
from empire_core.gamedata import EnumOrInt
from empire_core.map.models.areas import MapObject
from empire_core.map.models.items import TargetRow
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    CommanderEffects,
    int_entries,
    read_or_none,
    readable_list,
)

if TYPE_CHECKING:
    from empire_core.combat import Bonus
    from empire_core.gamedata import LegendSkill


logger = logging.getLogger(__name__)


# =============================================================================
# ACI - Attack Pre-calculation
# =============================================================================


class GetAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against a castle.

    Command: aci
    Payload: {"TX": target_x, "TY": target_y, "SX": source_x, "SY": source_y, "KID": kingdom_id}

    Client: ``C2SGetAttackCastleInfosVO`` (bundle line 72015),
    ``ClientConstSF.C2S_GET_ATTACK_CASTLE_INFOS`` (bundle line 71).
    """

    command = "aci"

    target_x: int = Field(validation_alias="TX", serialization_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", serialization_alias="TY", description="Target map y")
    source_x: int = Field(validation_alias="SX", serialization_alias="SX", description="Attacking castle's map x")
    source_y: int = Field(validation_alias="SY", serialization_alias="SY", description="Attacking castle's map y")
    kingdom_id: Kingdom = Field(
        validation_alias="KID", serialization_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target"
    )


class AttackTargetArea(BasePayload):
    """
    The target's map row and owner records, the ``gaa`` block of a pre-calculation reply.

    Client: ``CastleAttackInfoVO.fillFromParamObject`` (bundle line 30620) parses
    ``AI`` with ``WorldmapObjectFactory.parseWorldMapArea``; ``ACICommand`` and
    ``ABICommand`` pass ``OI`` to ``OtherPlayerData.parseOwnerInfoArray``
    """

    area: TargetRow = Field(
        validation_alias="AI", serialization_alias="AI", default=None, description="The target's map row"
    )
    owners: list[MapObject] = Field(
        validation_alias="OI", serialization_alias="OI", default_factory=list, description="Owner records"
    )

    @field_validator("owners", mode="before")
    @classmethod
    def _readable_records(cls, value: object) -> list[MapObject]:
        return readable_list(
            MapObject,
            value,
            accept=lambda record: isinstance(record, dict),
            warn=logger,
            what="owner records of an attack pre-calculation",
        )


class AttackInfoResponse(BaseResponse):
    """
    What every attack pre-calculation reply carries, whatever the target.

    Payload::

        {"SCID": source_castle_id, "KID": ..,
         "AE": [[effect_id, [value], source_tag], ...],
         "S": [left, middle, right, keep, stronghold, support, reserve],
         "AS": spy_age_seconds, "abe": {castellan}, "B": {castellan}, "LS": [...],
         "KTB": kings_tower_bonus, "HAWL": home_workshop_level,
         "gaa": {"AI": [target map row], "OI": [owner records]},
         "gui": {"I": [[wod_id, count], ...], "SHI": [[wod_id, count], ...]},
         "gli": {"C": [...], "B": [...]}}

    ``MB`` is left to the subclasses: it is the morality in an attack reply
    and the maximum barons in an outpost conquest reply.

    ``AE`` is already scoped by the server to this target. ``S``, ``AS``, the
    castellan and ``LS`` form the spy report; the client reads them only when
    ``S`` is not empty, and otherwise treats the target as never spied.

    Client: ``CastleAttackInfoVO.fillFromParamObject`` (bundle lines 30620-30633),
    ``CastleFightScreenVO.fillFromParamObject`` for ``AE`` (bundle line 30501), which hands it to
    ``SimpleEffectSource.parseEffects`` (bundle line 38429),
    ``CastleSpyArmyInfoVO.parseArmyInfo`` (bundle line 30699).
    """

    source_castle_id: int = Field(
        validation_alias="SCID", serialization_alias="SCID", default=0, description="Attacking castle's id"
    )
    target_x: int = Field(validation_alias="TX", serialization_alias="TX", default=0, description="Target map x")
    target_y: int = Field(validation_alias="TY", serialization_alias="TY", default=0, description="Target map y")
    kingdom_id: Kingdom = Field(
        validation_alias="KID",
        serialization_alias="KID",
        default=Kingdom.GREEN,
        description="The attacking castle's kingdom",
    )
    attacker_effects: CommanderEffects = Field(
        validation_alias="AE",
        serialization_alias="AE",
        default_factory=list,
        description="Area effects on this attack, already scoped to the target",
    )
    spy_army: SpyArmyBlock = Field(
        validation_alias="S",
        serialization_alias="S",
        default=None,
        description="The spied defenders by the position they hold; None without a spy report",
    )
    spy_age_seconds: int = Field(
        validation_alias="AS",
        serialization_alias="AS",
        default=-1,
        description="Seconds since the target was spied; -1 when there is no spy report",
    )
    spied_castellan: Commander | None = Field(
        validation_alias="abe",
        serialization_alias="abe",
        default=None,
        description="The castellan defending the target, preferred over spied_castellan_fallback",
    )
    spied_castellan_fallback: Commander | None = Field(
        validation_alias="B",
        serialization_alias="B",
        default=None,
        description="The castellan defending the target when spied_castellan is missing",
    )
    defender_legend_skill_ids: tuple[EnumOrInt["LegendSkill"], ...] = Field(
        validation_alias="LS",
        serialization_alias="LS",
        default=(),
        description="The defender's legend skills, part of the spy report",
    )
    kings_tower_bonus: float = Field(
        validation_alias="KTB", serialization_alias="KTB", default=0, description="Kings tower bonus"
    )
    home_workshop_level: int = Field(
        validation_alias="HAWL",
        serialization_alias="HAWL",
        default=0,
        description="Level of the attacking castle's workshop, which unlocks support tools",
    )
    target_area: AttackTargetArea = Field(
        validation_alias="gaa",
        serialization_alias="gaa",
        default_factory=lambda: AttackTargetArea(),
        description="The target's map row and owner records",
    )
    unit_inventory: UnitInventory = Field(
        validation_alias="gui",
        serialization_alias="gui",
        default_factory=UnitInventory,
        description="The attacker's units and tools, and its stronghold units",
    )
    commander_roster: CommanderRoster = Field(
        validation_alias="gli",
        serialization_alias="gli",
        default_factory=CommanderRoster,
        description="The attacker's commanders and castellans",
    )

    _castellan_from_abe: bool = PrivateAttr(default=False)

    @model_validator(mode="wrap")
    @classmethod
    def _note_castellan_source(
        cls, data: object, handler: ModelWrapValidatorHandler["AttackInfoResponse"]
    ) -> "AttackInfoResponse":
        # Client: t.abe||t.B, so B is read only when abe is falsy in JavaScript
        model = handler(data)
        if isinstance(data, dict):
            abe = data.get("abe", data.get("spied_castellan"))
            model._castellan_from_abe = abe is not None and abe is not False and abe != 0 and abe != ""
        return model

    @field_validator("spied_castellan", "spied_castellan_fallback", mode="wrap")
    @classmethod
    def _castellan_or_none(cls, value: object, handler: ValidatorFunctionWrapHandler) -> Commander | None:
        # The client builds no castellan from an empty entry
        if not value:
            return None
        return read_or_none(handler, value, warn=logger, what="the defending castellan of an attack pre-calculation")

    @field_validator("defender_legend_skill_ids", mode="before")
    @classmethod
    def _legend_skills(cls, value: object) -> list[int]:
        # Client: parseArmyInfo(t.S, t.AS, a, t.LS) (bundle line 30633), each looked up as sent by getSkillByID
        return int_entries(value, warn=logger, what="legend skills of an attack pre-calculation")

    @model_validator(mode="after")
    def _no_spy_report_without_an_army(self) -> "AttackInfoResponse":
        """Client: ``CastleSpyArmyInfoVO.parseArmyInfo`` sets the age and legend skills only when S is not empty."""
        if self.spy_army is None:
            self.spy_age_seconds = -1
            self.defender_legend_skill_ids = ()
        return self

    def attacker_bonuses(self) -> list["Bonus"]:
        """
        The area effects that apply to this attack, already scoped by the server.

        These are not the commander's - they are the kingdom-wide and event
        effects the attack picks up on top of it, and they include the flank and
        front unit-amount bonuses that decide how many troops a wave holds.
        """
        from empire_core.combat import effect_bonuses

        return effect_bonuses(self.attacker_effects)

    def defending_castellan(self) -> Commander | None:
        """
        The castellan holding the target, from ``abe`` or else ``B``.

        None without a spy report, since the client builds the defending
        castellan only when ``S`` is not empty. The client does not handle an
        empty entry, so that is None as well.

        Client: ``CastleAttackInfoVO.fillFromParamObject`` (``t.abe||t.B``,
        bundle line 30632), ``CastleSpyArmyInfoVO.parseArmyInfo`` (bundle line
        30699), ``LordFactory.createLord`` (bundle line 26399).
        """
        if self.spy_army is None:
            return None
        return self.spied_castellan if self._castellan_from_abe else self.spied_castellan_fallback

    def target_row(self) -> list[Any]:
        """
        The target's raw map row from ``gaa.AI``, or an empty list.

        Client: ``WorldmapObjectFactory.parseWorldMapArea(t.gaa.AI)`` in
        ``CastleAttackInfoVO.fillFromParamObject`` (bundle line 30620).
        """
        return list(self.target_area.area.raw_data) if self.target_area.area else []

    def owner_records(self) -> list[MapObject]:
        """
        The owner records under ``gaa.OI``.

        Client: ``ACICommand.executeCommand`` (bundle line 122164) and
        ``ABICommand.executeCommand`` (bundle line 122128) pass them to
        ``OtherPlayerData.parseOwnerInfoArray``; the other pre-calculation
        commands do not read them.
        """
        return list(self.target_area.owners)

    def inventory(self) -> dict[int, int]:
        """
        The attacker's units and tools from ``gui.I``, as ``{wod_id: count}``.

        Client: ``CastleAttackInfoVO.fillFromParamObject`` (bundle line 30620).
        """
        return dict(self.unit_inventory.units)

    def stronghold_inventory(self) -> dict[int, int]:
        """
        The attacker's stronghold units from ``gui.SHI``, as ``{wod_id: count}``.

        Client: ``CastleAttackInfoVO.fillFromParamObject`` into a
        ``StrongholdUnitInventory`` (bundle line 30620).
        """
        return dict(self.unit_inventory.stronghold)


class GetAttackInfoResponse(AttackInfoResponse):
    """
    The attack pre-calculation for a castle, and the base of every attack reply.

    Command: aci

    Client: ``CastleAttackData.parse_ACI`` (bundle line 133821),
    ``CastleAttackInfoVO.fillFromParamObject`` reads ``MB`` (bundle line 30620).
    """

    command = "aci"

    morality: float = Field(
        validation_alias="MB", serialization_alias="MB", default=0, description="Morality bonus of the attack"
    )


__all__ = [
    "AttackTargetArea",
    "AttackInfoResponse",
    "GetAttackInfoRequest",
    "GetAttackInfoResponse",
]
