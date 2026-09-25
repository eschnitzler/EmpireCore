"""
Attack and spy protocol models.

Commands:
- aci: Attack pre-calculation for a castle
- cra: Create/send attack
- csm: Send spy mission
- gas: Get attack presets
- msd: Skip attack cooldown
- sdc: Skip defense cooldown
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import TYPE_CHECKING, Any

from pydantic import Field, ValidationError, model_validator

from .base import BasePayload, BaseRequest, BaseResponse, UnitCount
from .commanders import Commander

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
    A single attack wave: left, middle and right flank.

    Payload: {"L": flank, "M": flank, "R": flank}
    """

    left: WaveFlank = Field(alias="L", default_factory=WaveFlank)
    middle: WaveFlank = Field(alias="M", default_factory=WaveFlank)
    right: WaveFlank = Field(alias="R", default_factory=WaveFlank)

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
        "A": [wave, ...],                    # see AttackWave
        "KID": kingdom_id,
        "LID": commander_id (0 = none),
        "WT": wait_time,
        "HBW": horses_type (-1 when PTT is set),
        "BPC": boost_with_coins,
        "ATT": attack_type (see AttackType),
        "AV": share_battle_view,
        "LP": loot_priority resource id,
        "FC": fast_cast,
        "PTT": feathers,
        "SD": slowdown offset in seconds,
        "ICA": collector_attack,
        "BKS": [collector_booster, ...],
        "AST": [support_tool_wod_id, ...],
        "CD": 99,                            # hardcoded by the client
        "RW": [[unit_id, count], ...],       # yard wave
        "ASCT": auto_skip_cooldown_type
    }
    """

    command = "cra"

    source_x: int = Field(alias="SX")
    source_y: int = Field(alias="SY")
    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    waves: list[AttackWave] = Field(alias="A", default_factory=list)
    kingdom_id: int = Field(alias="KID", default=0)
    commander_id: int = Field(alias="LID", default=0)
    wait_time: int = Field(alias="WT", default=0)
    horses_type: int = Field(alias="HBW", default=-1)
    boost_with_coins: int = Field(alias="BPC", default=0)
    attack_type: int = Field(alias="ATT", default=AttackType.ATTACK)
    share_battle_view: int = Field(alias="AV", default=0)
    loot_priority: int = Field(alias="LP", default=0)
    fast_cast: int = Field(alias="FC", default=0)
    feathers: int = Field(alias="PTT", default=0)
    slowdown: int = Field(alias="SD", default=0)
    collector_attack: int = Field(alias="ICA", default=0)
    collector_booster: list = Field(alias="BKS", default_factory=list)
    support_tools: list[int] = Field(alias="AST", default_factory=list)
    countdown: int = Field(alias="CD", default=99)
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
    """

    command = "cra"

    attack_movement: dict | None = Field(alias="AAM", default=None)

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


class GetAttackInfoResponse(BaseResponse):
    """
    Everything the attack dialog needs for one target.

    Command: aci
    Payload::

        {"SCID": source_castle_id, "KID": ..,
         "AE": [[effect_id, [value], source_tag], ...],
         "S": [left, middle, right, keep, stronghold, support, reserve],
         "AS": spy_age_seconds, "abe": {castellan}, "B": {castellan}, "LS": [...],
         "MB": morality, "KTB": kings_tower_bonus, "HAWL": home_workshop_level,
         "gaa": {"AI": [target map row], "OI": [owner records]},
         "gui": {"I": [[wod_id, count], ...], "SHI": [[wod_id, count], ...]},
         "gli": {"C": [...], "B": [...]}}

    ``AE`` is already scoped by the server to this target. ``S``, ``AS``, the
    castellan and ``LS`` form the spy report; the client reads them only when
    ``S`` is not empty, and otherwise treats the target as never spied.

    Client: ``CastleAttackInfoVO.fillFromParamObject`` (bundle lines 30620-30633),
    ``CastleFightScreenVO.fillFromParamObject`` for ``AE`` (bundle line 30501),
    ``CastleSpyArmyInfoVO.parseArmyInfo`` (bundle line 30699),
    ``ACICommand.executeCommand`` for ``gaa.OI`` (bundle line 122164).
    """

    command = "aci"

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
    morality: float = Field(alias="MB", default=0, description="Morality bonus of the attack")
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
    def _no_spy_report_without_an_army(self) -> "GetAttackInfoResponse":
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

        Client: ``ACICommand.executeCommand`` passes them to
        ``OtherPlayerData.parseOwnerInfoArray`` (bundle line 122164).
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
# GAS - Get Attack Presets
# =============================================================================


class GetPresetsRequest(BaseRequest):
    """
    Get saved attack presets.

    Command: gas
    Payload: {"CID": castle_id} or {} (empty for all)
    """

    command = "gas"

    castle_id: int | None = Field(alias="CID", default=None)


class AttackPreset(BasePayload):
    """A saved attack preset."""

    preset_id: int = Field(alias="PID")
    name: str = Field(alias="N")
    units: list[UnitCount] = Field(alias="U", default_factory=list)
    tools: list[UnitCount] = Field(alias="T", default_factory=list)


class GetPresetsResponse(BaseResponse):
    """
    Response containing attack presets.

    Command: gas
    """

    command = "gas"

    presets: list[AttackPreset] = Field(alias="P", default_factory=list)


# =============================================================================
# MSD - Skip Attack Cooldown
# =============================================================================


class SkipAttackCooldownRequest(BaseRequest):
    """
    Skip attack cooldown using rubies.

    Command: msd
    Payload: {"CID": castle_id}
    """

    command = "msd"

    castle_id: int = Field(alias="CID")


class SkipAttackCooldownResponse(BaseResponse):
    """
    Response to skipping attack cooldown.

    Command: msd
    """

    command = "msd"

    rubies_spent: int = Field(alias="RS", default=0)


# =============================================================================
# SDC - Skip Defense Cooldown
# =============================================================================


class SkipDefenseCooldownRequest(BaseRequest):
    """
    Skip defense cooldown using rubies.

    Command: sdc
    Payload: {"CID": castle_id}
    """

    command = "sdc"

    castle_id: int = Field(alias="CID")


class SkipDefenseCooldownResponse(BaseResponse):
    """
    Response to skipping defense cooldown.

    Command: sdc
    """

    command = "sdc"

    rubies_spent: int = Field(alias="RS", default=0)


__all__ = [
    # CRA - Create Attack
    "CreateAttackRequest",
    "CreateAttackResponse",
    # CSM - Send Spy
    "SendSpyRequest",
    "SendSpyResponse",
    # SSI - Spy Screen Info
    "SpyScreenInfoRequest",
    "SpyScreenInfoResponse",
    # GAS - Get Presets
    "GetPresetsRequest",
    "GetPresetsResponse",
    "AttackPreset",
    # MSD - Skip Attack Cooldown
    "SkipAttackCooldownRequest",
    "SkipAttackCooldownResponse",
    # SDC - Skip Defense Cooldown
    "SkipDefenseCooldownRequest",
    "SkipDefenseCooldownResponse",
]
