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

from pydantic import ConfigDict, Field

from .base import BaseRequest, BaseResponse, UnitCount

# =============================================================================
# CRA - Create Attack
# =============================================================================


class CreateAttackRequest(BaseRequest):
    """
    Send an attack to a target.

    Command: cra
    Payload: {
        "CID": source_castle_id,
        "TX": target_x,
        "TY": target_y,
        "TK": target_kingdom,
        "U": [{"UID": unit_id, "C": count}, ...],
        "T": [{"TID": tool_id, "C": count}, ...],  # optional
        "AT": attack_type,  # 1=attack, 2=support, etc.
    }
    """

    command = "cra"

    castle_id: int = Field(alias="CID")
    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    target_kingdom: int = Field(alias="TK", default=0)
    units: list[UnitCount] = Field(alias="U", default_factory=list)
    tools: list[UnitCount] = Field(alias="T", default_factory=list)
    attack_type: int = Field(alias="AT", default=1)  # 1=attack


class CreateAttackResponse(BaseResponse):
    """
    Response to attack creation.

    Command: cra
    """

    command = "cra"

    movement_id: int = Field(alias="MID", default=0)
    arrival_time: int = Field(alias="AT", default=0)  # Unix timestamp
    error_code: int = Field(alias="E", default=0)
    error_message: str | None = Field(alias="EM", default=None)


# =============================================================================
# CSM - Send Spy Mission
# =============================================================================


class SendSpyRequest(BaseRequest):
    """
    Send a spy mission to a target.

    Command: csm
    Payload: {
        "CID": source_castle_id,
        "TX": target_x,
        "TY": target_y,
        "TK": target_kingdom,
        "SC": spy_count,
    }
    """

    command = "csm"

    castle_id: int = Field(alias="CID")
    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    target_kingdom: int = Field(alias="TK", default=0)
    spy_count: int = Field(alias="SC", default=1)


class SendSpyResponse(BaseResponse):
    """
    Response to spy mission.

    Command: csm
    """

    command = "csm"

    movement_id: int = Field(alias="MID", default=0)
    arrival_time: int = Field(alias="AT", default=0)
    error_code: int = Field(alias="E", default=0)


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


class AttackPreset(BaseResponse):
    """A saved attack preset."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

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

    success: bool = Field(default=True)
    rubies_spent: int = Field(alias="RS", default=0)
    error_code: int = Field(alias="E", default=0)


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

    success: bool = Field(default=True)
    rubies_spent: int = Field(alias="RS", default=0)
    error_code: int = Field(alias="E", default=0)


__all__ = [
    # CRA - Create Attack
    "CreateAttackRequest",
    "CreateAttackResponse",
    # CSM - Send Spy
    "SendSpyRequest",
    "SendSpyResponse",
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
