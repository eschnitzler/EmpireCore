"""
Attack and spy protocol models.

Commands:
- aci, adi, abi, ali, avi, aii: Attack pre-calculation per kind of target
- coi, cci, cti: Conquest pre-calculation
- cra: Create/send attack
- csm: Send spy mission
- gas: Get attack presets
- sas: Save an attack preset
- msd: Shorten a dungeon's cooldown with a minute skip
- sdc: Skip a dungeon's cooldown
"""

from __future__ import annotations

import json
import logging
from enum import IntEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, ValidationError, field_serializer, field_validator, model_validator

from .base import BasePayload, BaseRequest, BaseResponse
from .commanders import Commander
from .map import MapAreaItem

if TYPE_CHECKING:
    from empire_core.combat import Bonus
    from empire_core.services.spy_army import SpyArmy

logger = logging.getLogger(__name__)

# =============================================================================
# CRA - Create Attack
# =============================================================================


class AttackType(IntEnum):
    """Values for the ATT field (CombatConst.ATTACK_TYPE_*)."""

    ATTACK = 0
    OUTPOST_CONQUER = 1
    VILLAGE_CONQUER = 2
    CAPITAL_CONQUER = 3
    METROPOL_CONQUER = 5
    KINGS_TOWER_CONQUER = 6
    CONQUER = 7
    MONUMENT_CONQUER = 8
    LABORATORY_CONQUER = 9


class WaveFlank(BasePayload):
    """
    One flank of an attack wave.

    Payload: {"T": [[tool_id, count], ...], "U": [[unit_id, count], ...]}
    """

    tools: list[list[int]] = Field(alias="T", default_factory=list)
    units: list[list[int]] = Field(alias="U", default_factory=list)


class AttackWave(BasePayload):
    """
    A single attack wave: left, right and middle flank.

    Payload: {"L": flank, "R": flank, "M": flank}, in the client's key order.

    Client: ``CastleAttackWaveVO.getWaveInfoObject`` (bundle line 99930)
    """

    left: WaveFlank = Field(alias="L", default_factory=WaveFlank)
    right: WaveFlank = Field(alias="R", default_factory=WaveFlank)
    middle: WaveFlank = Field(alias="M", default_factory=WaveFlank)

    def unit_count(self) -> int:
        """Total units across all three flanks; non-pair entries count as zero."""
        return sum(
            entry[1] for flank in (self.left, self.middle, self.right) for entry in flank.units if len(entry) >= 2
        )

    def is_complete(self) -> bool:
        """
        Whether the client would send this wave.

        The game drops any wave without units, tools included.
        """
        return self.unit_count() > 0


class CreateAttackRequest(BaseRequest):
    """
    Send an attack to a target.

    Command: cra
    Payload: {
        "SX": source_x, "SY": source_y,      # absolute map coordinates
        "TX": target_x, "TY": target_y,
        "KID": kingdom_id,
        "LID": commander_id (0 = none),
        "WT": wait_time,
        "HBW": horses_type (-1 when PTT is set),
        "BPC": boost_with_coins,
        "ATT": attack_type (see AttackType),
        "AV": share_battle_view,
        "LP": loot_priority resource id,
        "FC": send_anyway,
        "PTT": feathers,
        "SD": slowdown offset in seconds,
        "ICA": collector_attack,
        "CD": 99,                            # hardcoded by the client
        "A": [wave, ...],                    # see AttackWave
        "BKS": [collector_booster, ...],
        "AST": [support_tool_wod_id, ...],
        "RW": [[unit_id, count], ...],       # yard wave
        "ASCT": auto_skip_cooldown_type
    }

    Fields follow the client's key order: the constructor initialises SX
    through CD before it sets A, BKS, AST, RW and ASCT.

    Client: ``C2SCreateArmyAttackMovementVO`` (bundle line 60851)
    """

    command = "cra"

    source_x: int = Field(alias="SX")
    source_y: int = Field(alias="SY")
    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    kingdom_id: int = Field(alias="KID", default=0)
    commander_id: int = Field(alias="LID", default=0)
    wait_time: int = Field(alias="WT", default=0)
    horses_type: int = Field(alias="HBW", default=-1)
    boost_with_coins: int = Field(alias="BPC", default=0)
    attack_type: int = Field(alias="ATT", default=AttackType.ATTACK)
    share_battle_view: int = Field(alias="AV", default=0)
    loot_priority: int = Field(alias="LP", default=0)
    send_anyway: int = Field(
        alias="FC",
        default=0,
        description="1 to send although one of your attacks is already on its way there (after ATTACK_IN_PROGRESS)",
    )
    feathers: int = Field(alias="PTT", default=0)
    slowdown: int = Field(alias="SD", default=0)
    collector_attack: int = Field(alias="ICA", default=0)
    countdown: int = Field(alias="CD", default=99)
    waves: list[AttackWave] = Field(alias="A", default_factory=list)
    collector_booster: list = Field(alias="BKS", default_factory=list)
    support_tools: list[int] = Field(alias="AST", default_factory=list)
    yard_wave: list[list[int]] = Field(alias="RW", default_factory=list)
    auto_skip_cooldown: int = Field(alias="ASCT", default=0)


class CreateAttackResponse(BaseResponse):
    """
    Response to attack creation.

    Command: cra
    Payload::

        {"AAM": {
            "M":  {movement},                  # the created movement
            "UM": {"L": {gli entry}, ...},     # the commander leading it
            "FA": {"L": [[unit_id, count]], "M": [...], "R": [...], "RW": []},
            "AST": [...], "ATT": 0, "ASCT": 0, "FC": 0,
        }}

    ``UM.L`` is the same shape as a ``gli`` entry, equipment included, so it is
    what confirms which commander ``LID`` selected. ``FA`` is the army the
    server actually accepted, after it dropped empty flanks.

    A success also carries ``gcu`` and ``O``; the state manager applies both
    with the movement. An ``ATTACK_IN_PROGRESS`` (234) reply carries ``TS`` and
    ``AS`` instead, the countdown and army size of the attack already on its
    way, which the client shows before offering to send anyway with ``FC=1``.
    ``send_attack`` raises that reply as ``AttackInProgressError``, with both
    values read off it.

    Client: ``CRACommand.executeCommand`` (bundle line 125954),
    ``CurrencyData.parseGCU`` (bundle line 141191) with ``CollectableItemC1VO.SERVER_KEY`` "C1" (7995)
    and ``CollectableItemC2VO.SERVER_KEY`` "C2" (4876),
    ``CastlePostPostAttackFactionDialogProperties`` (bundle line 40173),
    ``CastlePostPostAttackFactionDialog.onClick`` (bundle line 40155).
    """

    command = "cra"

    attack_movement: dict | None = Field(alias="AAM", default=None, description="The created movement wrapper")
    currencies: dict = Field(
        alias="gcu", default_factory=dict, description="Currency totals after the send, C1 and C2 as the gcu command"
    )
    owners: list = Field(alias="O", default_factory=list, description="Owner records for the movement's areas")
    arrival_seconds: int | float | None = Field(
        alias="TS",
        default=None,
        description="On ATTACK_IN_PROGRESS: seconds until the attack already on its way arrives",
    )
    army_size: int | float | None = Field(
        alias="AS", default=None, description="On ATTACK_IN_PROGRESS: the size of the attack already on its way"
    )

    @property
    def leader(self) -> Commander | None:
        """The commander leading the attack, as the server echoed it back."""
        raw = ((self.attack_movement or {}).get("UM") or {}).get("L")
        if not isinstance(raw, dict):
            return None
        try:
            return Commander.model_validate(raw)
        except ValidationError:
            logger.warning("Could not parse the commander echoed back by cra")
            return None

    @property
    def movement_id(self) -> int | None:
        """The created movement's ID, or None when the server sent no movement."""
        movement = (self.attack_movement or {}).get("M")
        if not isinstance(movement, dict):
            return None
        try:
            return int(movement["MID"])
        except (KeyError, TypeError, ValueError):
            return None


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

    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")
    source_x: int = Field(alias="SX", description="Attacking castle's map x")
    source_y: int = Field(alias="SY", description="Attacking castle's map y")
    kingdom_id: int = Field(alias="KID", default=0, description="Kingdom id of the target")


def _wod_amounts(entries: Any) -> dict[int, int]:
    """
    ``[[wod_id, amount], ...]`` as ``{wod_id: amount}``.

    Repeated ids add up and ids left at zero or less are dropped.

    Client: ``AUnitInventory.fillFromWodAmountArray`` (bundle line 42572) into a
    ``UnitInventoryDictionary``: ``addUnit`` clamps at 0 and ``changeUnitAmount``
    adds (bundle lines 5533-5535), ``setUnit`` deletes a total of 0 or less
    (bundle line 5538).
    """
    if not isinstance(entries, list):
        return {}
    totals: dict[int, int] = {}
    for entry in entries:
        if isinstance(entry, list) and len(entry) >= 2:
            totals[entry[0]] = totals.get(entry[0], 0) + max(0, entry[1])
    return {wod_id: amount for wod_id, amount in totals.items() if amount > 0}


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
    ``CastleFightScreenVO.fillFromParamObject`` for ``AE`` (bundle line 30501),
    ``CastleSpyArmyInfoVO.parseArmyInfo`` (bundle line 30699).
    """

    source_castle_id: int = Field(alias="SCID", default=0, description="Attacking castle's id")
    target_x: int = Field(alias="TX", default=0, description="Target map x")
    target_y: int = Field(alias="TY", default=0, description="Target map y")
    kingdom_id: int = Field(alias="KID", default=0, description="Kingdom id")
    raw_attacker_effects: list = Field(
        alias="AE", default_factory=list, description="Area effects on this attack, already scoped to the target"
    )
    raw_spy_army: list = Field(alias="S", default_factory=list, description="Spied defenders, one entry per position")
    spy_age_seconds: int = Field(
        alias="AS",
        default=-1,
        description="Seconds since the target was spied; -1 when there is no spy report, which is also the value "
        "whenever S is empty",
    )
    raw_defending_castellan: dict | None = Field(
        alias="abe", default=None, description="The castellan defending the target, read in preference to B"
    )
    raw_defending_castellan_fallback: dict | None = Field(
        alias="B", default=None, description="The castellan defending the target when abe is missing"
    )
    defender_legend_skill_ids: list[int] = Field(
        alias="LS",
        default_factory=list,
        description="The defender's legend skill ids, part of the spy report",
    )
    kings_tower_bonus: float = Field(alias="KTB", default=0, description="Kings tower bonus")
    home_workshop_level: int = Field(
        alias="HAWL", default=0, description="Level of the attacking castle's workshop, which unlocks support tools"
    )
    raw_map_area: dict = Field(
        alias="gaa", default_factory=dict, description="AI: the target's map row, OI: owner records"
    )
    raw_inventory: dict = Field(
        alias="gui", default_factory=dict, description="I: the attacker's units and tools, SHI: its stronghold units"
    )
    raw_commanders: dict = Field(alias="gli", default_factory=dict, description="The attacker's commanders, as gli")

    @model_validator(mode="after")
    def _no_spy_report_without_an_army(self) -> "AttackInfoResponse":
        """Client: ``CastleSpyArmyInfoVO.parseArmyInfo`` sets the age and legend skills only when S is not empty."""
        if not self.raw_spy_army:
            self.spy_age_seconds = -1
            self.defender_legend_skill_ids = []
        return self

    def attacker_bonuses(self) -> list["Bonus"]:
        """
        The area effects that apply to this attack, already scoped by the server.

        These are not the commander's - they are the kingdom-wide and event
        effects the attack picks up on top of it, and they include the flank and
        front unit-amount bonuses that decide how many troops a wave holds.
        """
        from empire_core.combat import parse_bonus_entries

        return parse_bonus_entries(self.raw_attacker_effects)

    def spy_army(self) -> "SpyArmy | None":
        """
        The spied defenders, split by the position they hold, or None without a spy report.

        Client: ``CastleSpyArmyInfoVO.parseArmyInfo`` fills the positions only
        when ``S`` is not empty (bundle line 30699).
        """
        from empire_core.services.spy_army import SpyArmy

        if not self.raw_spy_army:
            return None
        return SpyArmy.from_spy_data(self.raw_spy_army)

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
        if not self.raw_spy_army:
            return None
        entry = (
            self.raw_defending_castellan
            if self.raw_defending_castellan is not None
            else self.raw_defending_castellan_fallback
        )
        if not entry:
            return None
        try:
            return Commander.model_validate(entry)
        except ValidationError:
            logger.warning("Could not parse the defending castellan from an attack pre-calculation")
            return None

    def target_row(self) -> list:
        """
        The target's raw map row from ``gaa.AI``, or an empty list.

        Client: ``WorldmapObjectFactory.parseWorldMapArea(t.gaa.AI)`` in
        ``CastleAttackInfoVO.fillFromParamObject`` (bundle line 30620).
        """
        row = self.raw_map_area.get("AI")
        return row if isinstance(row, list) else []

    def owner_records(self) -> list[dict]:
        """
        The raw owner records under ``gaa.OI``.

        Client: ``ACICommand.executeCommand`` (bundle line 122164) and
        ``ABICommand.executeCommand`` (bundle line 122128) pass them to
        ``OtherPlayerData.parseOwnerInfoArray``; the other pre-calculation
        commands do not read them.
        """
        records = self.raw_map_area.get("OI")
        return [record for record in records if isinstance(record, dict)] if isinstance(records, list) else []

    def inventory(self) -> dict[int, int]:
        """
        The attacker's units and tools from ``gui.I``, as ``{wod_id: count}``.

        Client: ``CastleAttackInfoVO.fillFromParamObject`` (bundle line 30620).
        """
        return _wod_amounts(self.raw_inventory.get("I"))

    def stronghold_inventory(self) -> dict[int, int]:
        """
        The attacker's stronghold units from ``gui.SHI``, as ``{wod_id: count}``.

        Client: ``CastleAttackInfoVO.fillFromParamObject`` into a
        ``StrongholdUnitInventory`` (bundle line 30620).
        """
        return _wod_amounts(self.raw_inventory.get("SHI"))


class GetAttackInfoResponse(AttackInfoResponse):
    """
    The attack pre-calculation for a castle, and the base of every attack reply.

    Command: aci

    Client: ``CastleAttackData.parse_ACI`` (bundle line 133821),
    ``CastleAttackInfoVO.fillFromParamObject`` reads ``MB`` (bundle line 30620).
    """

    command = "aci"

    morality: float = Field(alias="MB", default=0, description="Morality bonus of the attack")


# =============================================================================
# ADI / ABI / ALI / AVI / AII - Attack pre-calculation for other targets
# =============================================================================


class GetDungeonAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against an NPC camp.

    Every target whose map object attacks as a dungeon answers this command:
    robber baron camps, event and isle dungeons, invasion and alien camps, the
    wolf king and the alliance raid portal. The server refuses ``aci`` for a
    camp with INVALID_AREA.

    Command: adi
    Payload: {"SX": source_x, "SY": source_y, "TX": target_x, "TY": target_y, "KID": kingdom_id}

    Client: ``C2SGetAttackDungeonInfosVO`` (bundle line 72024), whose key order the fields follow;
    ``CastleStartAttackDialog.attackDungeon`` (bundle line 14834).
    """

    command = "adi"

    source_x: int = Field(alias="SX", description="Attacking castle's map x")
    source_y: int = Field(alias="SY", description="Attacking castle's map y")
    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")
    kingdom_id: int = Field(alias="KID", default=0, description="Kingdom id of the target")


class GetDungeonAttackInfoResponse(GetAttackInfoResponse):
    """
    The attack pre-calculation for an NPC camp.

    Command: adi

    Client: ``ADICommand.executeCommand`` (bundle line 122187), ``CastleAttackData.parse_ADI`` (133830).
    """

    command = "adi"


class GetBossDungeonAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against a boss dungeon.

    Command: abi
    Payload: {"KID": kingdom_id, "SX": source_x, "SY": source_y, "TX": target_x, "TY": target_y}

    Client: ``C2SAttackInfoBossDungeonVO`` (bundle line 71970),
    ``CastleStartAttackDialog.attackBossDungeon`` (bundle line 14837).
    """

    command = "abi"

    kingdom_id: int = Field(alias="KID", default=0, description="Kingdom id of the target")
    source_x: int = Field(alias="SX", description="Attacking castle's map x")
    source_y: int = Field(alias="SY", description="Attacking castle's map y")
    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")


class GetBossDungeonAttackInfoResponse(GetAttackInfoResponse):
    """
    The attack pre-calculation for a boss dungeon.

    Command: abi

    Client: ``ABICommand.executeCommand`` (bundle line 122128), ``CastleAttackData.parse_ABI`` (133827).
    """

    command = "abi"


class GetLandmarkAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against a kings tower, monument or laboratory.

    Command: ali
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y, "SX": source_x, "SY": source_y}

    Client: ``C2SAttackInfoLandmarkVO`` (bundle line 71988),
    ``CastleStartAttackDialog.attackLandmark`` (bundle line 14846).
    """

    command = "ali"

    kingdom_id: int = Field(alias="KID", default=0, description="Kingdom id of the target")
    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")
    source_x: int = Field(alias="SX", description="Attacking castle's map x")
    source_y: int = Field(alias="SY", description="Attacking castle's map y")


class GetLandmarkAttackInfoResponse(GetAttackInfoResponse):
    """
    The attack pre-calculation for a landmark.

    Command: ali

    Client: ``ALICommand.executeCommand`` (bundle line 122227), ``CastleAttackData.parse_ALI`` (133836).
    """

    command = "ali"


class GetVillageAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against a village.

    The client sends no source castle for it.

    Command: avi
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y}

    Client: ``C2SAttackInfoVillageVO`` (bundle line 71997),
    ``CastleStartAttackDialog.attackVillage`` (bundle line 14844).
    """

    command = "avi"

    kingdom_id: int = Field(alias="KID", default=0, description="Kingdom id of the target")
    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")


class GetVillageAttackInfoResponse(GetAttackInfoResponse):
    """
    The attack pre-calculation for a village.

    Command: avi

    Client: ``AVICommand.executeCommand`` (bundle line 122244), ``CastleAttackData.parse_AVI`` (133832).
    """

    command = "avi"


class GetIslandAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against an isle resource.

    An isle dungeon attacks as a dungeon and answers ``adi`` instead.

    Command: aii
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y}

    Client: ``C2SAttackInfoIslandVO`` (bundle line 71979),
    ``CastleStartAttackDialog.attackIsland`` (bundle line 14845).
    """

    command = "aii"

    kingdom_id: int = Field(alias="KID", default=0, description="Kingdom id of the target")
    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")


class GetIslandAttackInfoResponse(GetAttackInfoResponse):
    """
    The attack pre-calculation for an isle resource.

    Command: aii

    Client: ``AIICommand.executeCommand`` (bundle line 122204), ``CastleAttackData.parse_AII`` (133834).
    """

    command = "aii"


# =============================================================================
# COI / CCI / CTI - Conquest pre-calculation
# =============================================================================


class GetOutpostConquerInfoRequest(BaseRequest):
    """
    Ask for the conquest pre-calculation against an outpost.

    Command: coi
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y}

    Client: ``C2SGetConquerOutpostInfosVO`` (bundle line 72060),
    ``CastleStartAttackDialog.conquerOutpost`` (bundle line 14839).
    """

    command = "coi"

    kingdom_id: int = Field(alias="KID", default=0, description="Kingdom id of the target")
    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")


class GetOutpostConquerInfoResponse(AttackInfoResponse):
    """
    The conquest pre-calculation for an outpost, with the barons it can use.

    The client reads ``MB`` twice here: as the morality in the shared parse
    and as the maximum barons in ``parseBarons``. This model keeps the
    conquest meaning only.

    Command: coi

    Client: ``COICommand.executeCommand`` (bundle line 122278), ``CastleAttackData.parse_COI`` (133838),
    ``CastleConquerInfoVO.fillFromParamObject`` / ``parseBarons`` (bundle lines 133904-133907).
    """

    command = "coi"

    available_barons: int = Field(alias="AB", default=0, description="Barons free to lead the conquest")
    max_barons: int = Field(alias="MB", default=0, description="Most barons the player may hold")


class GetCapitalConquerInfoRequest(BaseRequest):
    """
    Ask for the conquest pre-calculation against a capital.

    Command: cci
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y}

    Client: ``C2SGetConquerCapitalInfosVO`` (bundle line 72042),
    ``CastleStartAttackDialog.conquerCapital`` (bundle line 14842).
    """

    command = "cci"

    kingdom_id: int = Field(alias="KID", default=0, description="Kingdom id of the target")
    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")


class GetCapitalConquerInfoResponse(GetAttackInfoResponse):
    """
    The conquest pre-calculation for a capital. The client reads no barons from it.

    Command: cci

    Client: ``CCICommand.executeCommand`` (bundle line 122261), ``CastleAttackData.parse_CCI`` (133840),
    ``CastleConquerInfoVO.fillFromParamObject``
    (bundle line 133904).
    """

    command = "cci"


class GetMetropolConquerInfoRequest(BaseRequest):
    """
    Ask for the conquest pre-calculation against a metropolis.

    Command: cti
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y}

    Client: ``C2SGetConquerMetropolInfosVO`` (bundle line 72051),
    ``CastleStartAttackDialog.conquerMetropol`` (bundle line 14843).
    """

    command = "cti"

    kingdom_id: int = Field(alias="KID", default=0, description="Kingdom id of the target")
    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")


class GetMetropolConquerInfoResponse(GetAttackInfoResponse):
    """
    The conquest pre-calculation for a metropolis. The client reads no barons from it.

    Command: cti

    Client: ``CTICommand.executeCommand`` (bundle line 122295), ``CastleAttackData.parse_CTI`` (133842),
    ``CastleConquerInfoVO.fillFromParamObject``
    (bundle line 133904).
    """

    command = "cti"


# =============================================================================
# CSM - Send Spy Mission
# =============================================================================


class SendSpyRequest(BaseRequest):
    """
    Send a spy mission to a target.

    Command: csm
    Payload: {
        "SID": source_castle_id,
        "TX": target_x,
        "TY": target_y,
        "KID": target_kingdom,
        "SC": spy_count,
        "ST": spy_type,
        "SE": precision,
        "HBW": horses_type,
        "PTT": pay_to_travel,
        "SD": sd
    }
    """

    command = "csm"

    castle_id: int = Field(alias="SID")
    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    target_kingdom: int = Field(alias="KID", default=0)
    spy_count: int = Field(alias="SC", default=1)
    spy_type: int = Field(alias="ST", default=0)
    precision: int = Field(alias="SE", default=100)
    horses_type: int = Field(alias="HBW", default=-1)
    pay_to_travel: int = Field(alias="PTT", default=0)
    sd: int = Field(alias="SD", default=0)


class SendSpyResponse(BaseResponse):
    """
    Response to spy mission.

    Command: csm
    """

    command = "csm"

    movement_id: int = Field(alias="MID", default=0)
    arrival_time: int = Field(alias="AT", default=0)


# =============================================================================
# SSI - Spy Screen Info
# =============================================================================


class SpyScreenInfoRequest(BaseRequest):
    """
    Get spy screen info (guard count, available spies).

    Command: ssi
    Payload: {
        "TX": target_x,
        "TY": target_y,
        "KID": target_kingdom
    }
    """

    command = "ssi"

    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    target_kingdom: int = Field(alias="KID", default=0)


class SpyScreenInfoResponse(BaseResponse):
    """
    Response to spy screen info.

    Command: ssi
    """

    command = "ssi"

    available_spies: int = Field(alias="AS", default=0)
    guard_count: int = Field(alias="GC", default=0)


# =============================================================================
# GAS / SAS - Attack presets
# =============================================================================


class GetPresetsRequest(BaseRequest):
    """
    Get the player's saved attack presets.

    Command: gas
    Payload: {}
    Client: ``C2SGetPreDefinedAttackSetupVO`` (bundle line 141803), sent by
    ``FightPresetData.loadDataFromServer``
    """

    command = "gas"


def _pairs(flat: list[int]) -> list[list[int]]:
    """``[wod, count, wod, count, ...]`` as ``[[wod, count], ...]``, a missing count read as 0."""
    return [[flat[i], flat[i + 1] if i + 1 < len(flat) else 0] for i in range(0, len(flat), 2)]


def _filled(slots: list[list[int]]) -> list[list[int]]:
    """The slots holding something; the client skips a slot whose wod id is -1."""
    return [[slot[0], slot[1]] for slot in slots if len(slot) >= 2 and slot[0] != -1]


def _flat(pairs: list[list[int]]) -> list[int]:
    return [value for wod_id, count in _filled(pairs) for value in (wod_id, count)]


class PresetArmy(BaseModel):
    """
    A preset's army, decoded from its ``A`` string.

    ``A`` is a JSON list of flat ``[wod_id, count, wod_id, count, ...]`` arrays,
    one per container of a wave in ``CastleAttackWaveVO.flanks`` order: middle,
    left and right tools, then middle, left and right units. A seventh array,
    read only when the list has exactly seven entries, holds the support-tool
    wod ids.

    Client: ``FightPresetVO.getUnitWodId`` / ``getUnitCount`` /
    ``getSupportTools`` (bundle lines 141845-141848), ``CastleAttackWaveVO``
    constructor and ``flanks`` getter (bundle lines 99925, 99983)
    """

    middle_tools: list[list[int]] = Field(default_factory=list, description="A[0], as [wod_id, count] pairs")
    left_tools: list[list[int]] = Field(default_factory=list, description="A[1], as [wod_id, count] pairs")
    right_tools: list[list[int]] = Field(default_factory=list, description="A[2], as [wod_id, count] pairs")
    middle_units: list[list[int]] = Field(default_factory=list, description="A[3], as [wod_id, count] pairs")
    left_units: list[list[int]] = Field(default_factory=list, description="A[4], as [wod_id, count] pairs")
    right_units: list[list[int]] = Field(default_factory=list, description="A[5], as [wod_id, count] pairs")
    support_tools: list[int] = Field(
        default_factory=lambda: [-1, -1, -1],
        description="A[6] when A has exactly seven arrays, else [-1, -1, -1]",
    )

    @classmethod
    def from_arrays(cls, arrays: list[list[int]]) -> PresetArmy:
        """Decode the list ``A`` parses to."""

        def part(index: int) -> list[list[int]]:
            return _pairs(arrays[index]) if index < len(arrays) and isinstance(arrays[index], list) else []

        return cls(
            middle_tools=part(0),
            left_tools=part(1),
            right_tools=part(2),
            middle_units=part(3),
            left_units=part(4),
            right_units=part(5),
            support_tools=list(arrays[6]) if len(arrays) == 7 else [-1, -1, -1],
        )

    @classmethod
    def from_wave(cls, wave: AttackWave) -> PresetArmy:
        """
        The preset the client saves from a wave.

        Empty slots are dropped. The client saves no support tools: its
        ``setContentFromWave`` ignores the support tools it is handed and
        writes six arrays.

        Client: ``FightPresetVO.setContentFromWave`` (bundle line 141850),
        called by ``AttackDialogPresets.fillPresetFromWave`` (bundle line 101668)
        """
        return cls(
            middle_tools=_filled(wave.middle.tools),
            left_tools=_filled(wave.left.tools),
            right_tools=_filled(wave.right.tools),
            middle_units=_filled(wave.middle.units),
            left_units=_filled(wave.left.units),
            right_units=_filled(wave.right.units),
        )

    def to_arrays(self) -> list[list[int]]:
        """The six flat arrays the client saves, empty slots dropped."""
        return [
            _flat(self.middle_tools),
            _flat(self.left_tools),
            _flat(self.right_tools),
            _flat(self.middle_units),
            _flat(self.left_units),
            _flat(self.right_units),
        ]

    def to_wave(self) -> AttackWave:
        """The army as a wave, without the support tools."""
        return AttackWave(
            L=WaveFlank(T=self.left_tools, U=self.left_units),
            M=WaveFlank(T=self.middle_tools, U=self.middle_units),
            R=WaveFlank(T=self.right_tools, U=self.right_units),
        )


class AttackPreset(BasePayload):
    """
    One unlocked preset slot from the ``gas`` reply.

    Client: ``FightPresetData.parsePresets`` (bundle line 141770),
    ``FightPresetVO.update`` / ``deserialize`` (bundle lines 141830, 141836)
    """

    index: int = Field(alias="S", description="Preset slot index")
    name: str | None = Field(
        alias="SN",
        default=None,
        description="Preset name; missing or empty means the client's default name",
    )
    raw_army: str | None = Field(alias="A", default=None, description="The army as a JSON string, see PresetArmy")

    def army(self) -> PresetArmy | None:
        """The decoded army, or None when the slot is empty or ``A`` does not parse."""
        if not self.raw_army:
            return None
        try:
            arrays = json.loads(self.raw_army)
        except ValueError:
            return None
        if not isinstance(arrays, list):
            return None
        try:
            return PresetArmy.from_arrays(arrays)
        except (TypeError, ValidationError):
            return None


class GetPresetsResponse(BaseResponse):
    """
    The unlocked preset slots.

    Command: gas
    Payload: {"S": [{"S": index, "SN": name, "A": "<JSON string>"}, ...]}
    Client: ``GASCommand.executeCommand`` (bundle line 122070) into
    ``FightPresetData.parsePresets`` (bundle line 141770), which counts every
    entry present as an unlocked slot
    """

    command = "gas"

    presets: list[AttackPreset] = Field(alias="S", default_factory=list, description="Unlocked preset slots")

    @field_validator("presets", mode="before")
    @classmethod
    def _skip_missing_entries(cls, value: Any) -> Any:
        return [entry for entry in value if entry is not None] if isinstance(value, list) else value


class SavePresetRequest(BaseRequest):
    """
    Save an army into a preset slot.

    Command: sas
    Payload: {"S": index, "A": "<JSON string of PresetArmy.to_arrays()>"}
    Client: ``C2SUpdatePreDefinedAttackSetupVO`` (bundle line 141820), with
    ``A`` from ``FightPresetVO.unitsAsString``, a ``JSON.stringify`` (bundle
    line 141843); sent by ``FightPresetData.savePresetArmy``
    """

    command = "sas"

    index: int = Field(alias="S", description="Preset slot index")
    raw_army: str = Field(alias="A", description="The army as a compact JSON string")

    @classmethod
    def create(cls, index: int, army: PresetArmy) -> SavePresetRequest:
        """Build the request for an army, serialised the way ``JSON.stringify`` does."""
        return cls(S=index, A=json.dumps(army.to_arrays(), separators=(",", ":")))


class SavePresetResponse(BaseResponse):
    """
    Acknowledgement of a saved preset; the client reads nothing from it.

    Command: sas
    Client: ``SASCommand.executeCommand`` (bundle line 122086)
    """

    command = "sas"


# =============================================================================
# MSD / SDC - Dungeon cooldown skips
# =============================================================================


class MinuteSkipDungeonRequest(BaseRequest):
    """
    Shorten a dungeon's cooldown with a minute-skip item.

    A dungeon is an NPC target, treasure-map dungeons included, that has to
    recover before it can be attacked again. Fields follow the client's key
    order: the constructor initialises X, Y, MID, NID before it sets MST and KID.

    Command: msd
    Client: ``C2SMinuteSkipDungeonVO`` (bundle line 72337), built by
    ``SkippableCooldownMinuteSkipProperties.getMinuteSkipCommand`` (bundle line
    72324); ``CastleMinuteSkipDialog.onScrollItemClick`` passes the currency's
    ``jsonKey`` as ``MST`` (bundle line 7722)
    """

    command = "msd"

    x: int = Field(alias="X", description="Dungeon map x")
    y: int = Field(alias="Y", description="Dungeon map y")
    map_id: int = Field(alias="MID", default=-1, description="Treasure-map id, -1 for an ordinary dungeon")
    node_id: int = Field(alias="NID", default=-1, description="Treasure-map node id, -1 for an ordinary dungeon")
    minute_skip: str = Field(
        alias="MST",
        description="JSON key of the minute-skip currency used, MS1 to MS7 in the item data (see SCEItem)",
    )
    kingdom_id: int = Field(alias="KID", description="Kingdom id; sent as a string, as the client's toString() does")

    @field_serializer("kingdom_id")
    def _kingdom_id_as_string(self, value: int) -> str:
        return str(value)


class MinuteSkipDungeonResponse(BaseResponse):
    """
    The dungeon's map row after a minute skip.

    Command: msd
    Client: ``MSDCommand.executeCommand`` (bundle line 125782), which parses
    ``AI`` with ``WorldmapObjectFactory.parseWorldMapArea`` (``DungeonMapobjectVO`` for a camp)
    """

    command = "msd"

    area: MapAreaItem | None = Field(
        alias="AI",
        default=None,
        description="The dungeon's updated map row, with its victories and remaining cooldown",
    )

    @field_validator("area", mode="before")
    @classmethod
    def _parse_row(cls, value: object) -> object:
        return MapAreaItem.from_list(value) if isinstance(value, list) else value


class SkipDungeonCooldownRequest(BaseRequest):
    """
    Skip a dungeon's whole cooldown.

    Command: sdc
    Client: ``C2SSkipDungeonCooldownVO`` (bundle line 46101), built by
    ``SkippableCooldownMinuteSkipProperties.getFullSkipCommand`` (bundle line 72323)
    """

    command = "sdc"

    x: int = Field(alias="X", description="Dungeon map x")
    y: int = Field(alias="Y", description="Dungeon map y")
    kingdom_id: int = Field(alias="KID", description="Kingdom id")
    map_id: int = Field(alias="MID", default=-1, description="Treasure-map id, -1 for an ordinary dungeon")
    node_id: int = Field(alias="NID", default=-1, description="Treasure-map node id, -1 for an ordinary dungeon")


class SkipDungeonCooldownResponse(BaseResponse):
    """
    The dungeon's map row after its cooldown was skipped.

    Command: sdc
    Client: ``SDCCommand.executeCommand`` (bundle line 122333), which parses
    ``AI`` with ``WorldmapObjectFactory.parseWorldMapArea`` (``DungeonMapobjectVO`` for a camp)
    """

    command = "sdc"

    area: MapAreaItem | None = Field(
        alias="AI",
        default=None,
        description="The dungeon's updated map row, with its victories and remaining cooldown",
    )

    @field_validator("area", mode="before")
    @classmethod
    def _parse_row(cls, value: object) -> object:
        return MapAreaItem.from_list(value) if isinstance(value, list) else value


__all__ = [
    # Pre-calculation
    "AttackInfoResponse",
    "GetAttackInfoRequest",
    "GetAttackInfoResponse",
    "GetDungeonAttackInfoRequest",
    "GetDungeonAttackInfoResponse",
    "GetBossDungeonAttackInfoRequest",
    "GetBossDungeonAttackInfoResponse",
    "GetLandmarkAttackInfoRequest",
    "GetLandmarkAttackInfoResponse",
    "GetVillageAttackInfoRequest",
    "GetVillageAttackInfoResponse",
    "GetIslandAttackInfoRequest",
    "GetIslandAttackInfoResponse",
    "GetOutpostConquerInfoRequest",
    "GetOutpostConquerInfoResponse",
    "GetCapitalConquerInfoRequest",
    "GetCapitalConquerInfoResponse",
    "GetMetropolConquerInfoRequest",
    "GetMetropolConquerInfoResponse",
    # CRA - Create Attack
    "CreateAttackRequest",
    "CreateAttackResponse",
    # CSM - Send Spy
    "SendSpyRequest",
    "SendSpyResponse",
    # SSI - Spy Screen Info
    "SpyScreenInfoRequest",
    "SpyScreenInfoResponse",
    # GAS / SAS - Attack presets
    "GetPresetsRequest",
    "GetPresetsResponse",
    "AttackPreset",
    "PresetArmy",
    "SavePresetRequest",
    "SavePresetResponse",
    # MSD / SDC - Dungeon cooldown skips
    "MinuteSkipDungeonRequest",
    "MinuteSkipDungeonResponse",
    "SkipDungeonCooldownRequest",
    "SkipDungeonCooldownResponse",
]
