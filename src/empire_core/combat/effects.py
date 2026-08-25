"""
Flank effect values, ported from the game client's combat maths.

The client feeds an attacker-side and a defender-side effect object into its
auto-fill strategy. Both are plain value holders: the interesting part is how
their inputs are aggregated, which lives in :mod:`empire_core.combat.defence`.
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, ConfigDict

from empire_core.gamedata import UnitStats


class Flank(IntEnum):
    """Attack-screen flanks (``ClientConstCastle.FLANK_*``)."""

    LEFT = 0
    MIDDLE = 1
    RIGHT = 2
    YARD = 3
    REINFORCEMENT = 4


class AttackerFlankEffects(BaseModel):
    """
    The attacker's multipliers for one flank.

    Bonuses are multipliers, so 1.0 means an unbuffed attack. Reductions are
    subtracted from the defender's matching bonus.
    """

    model_config = ConfigDict(extra="forbid")

    melee_bonus: float = 1.0
    range_bonus: float = 1.0
    defender_range_reduction: float = 0.0
    gate_reduction: float = 0.0
    wall_reduction: float = 0.0
    moat_reduction: float = 0.0

    def soldier_stack_attack_value(self, unit: UnitStats, free_items: int, available: int) -> int:
        """
        What a stack of this unit is worth on this flank.

        Mirrors ``AttackerFlankEffectVO.getSoldierStackAttackValue``: the unit's
        attack times the matching bonus, truncated, times however many of it
        actually fit.

        Args:
            unit: The unit being considered
            free_items: Remaining troop capacity of the flank
            available: How many of the unit the player owns

        Returns:
            The stack's attack value, 0 for a unit with no matching role
        """
        if unit.is_melee:
            per_unit = int(unit.melee_attack * self.melee_bonus)
        elif unit.is_ranged:
            per_unit = int(unit.range_attack * self.range_bonus)
        else:
            return 0
        return per_unit * max(0, min(free_items, available))


class DefenderFlankEffects(BaseModel):
    """
    The defender's strength on one flank.

    The four strengths are sums over the defending army, split by the defenders'
    role: melee-role defenders contribute to ``melee_units_*``, ranged-role
    defenders to ``range_units_*``. Bonuses are multipliers starting at 1.0.
    """

    model_config = ConfigDict(extra="forbid")

    melee_units_melee_strength: float = 0.0
    melee_units_range_strength: float = 0.0
    range_units_melee_strength: float = 0.0
    range_units_range_strength: float = 0.0
    melee_bonus: float = 1.0
    range_bonus: float = 1.0
    wall_bonus: float = 0.0
    gate_bonus: float = 0.0
    moat_bonus: float = 0.0

    def melee_defence_value(self, melee_reduction: float = 0.0, range_reduction: float = 0.0) -> float:
        """Defence against a melee attack (``getMeleeDefenceValue``)."""
        return self.melee_units_melee_strength * (self.melee_bonus - melee_reduction) + (
            self.range_units_melee_strength * (self.range_bonus - range_reduction)
        )

    def range_defence_value(self, range_reduction: float = 0.0, melee_reduction: float = 0.0) -> float:
        """Defence against a ranged attack (``getRangeDefenceValue``)."""
        return self.range_units_range_strength * (self.range_bonus - range_reduction) + (
            self.melee_units_range_strength * (self.melee_bonus - melee_reduction)
        )

    def is_empty(self) -> bool:
        """Whether anything defends this flank at all."""
        return not (
            self.melee_units_melee_strength
            or self.melee_units_range_strength
            or self.range_units_melee_strength
            or self.range_units_range_strength
        )


__all__ = ["AttackerFlankEffects", "DefenderFlankEffects", "Flank"]
