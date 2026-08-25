"""
Attack and spy protocol models.

Commands:
- cra: Create/send attack
- csm: Send spy mission
- gas: Get attack presets
- msd: Skip attack cooldown
- sdc: Skip defense cooldown
"""

from __future__ import annotations

import logging
from enum import IntEnum

from pydantic import Field, ValidationError

from .base import BasePayload, BaseRequest, BaseResponse, UnitCount
from .commanders import Commander

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
