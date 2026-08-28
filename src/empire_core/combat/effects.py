"""
Flank effect values, ported from the game client's combat maths.

The client feeds an attacker-side and a defender-side effect object into its
auto-fill strategy. Both are plain value holders: the interesting part is how
their inputs are aggregated, which lives in :mod:`empire_core.combat.defense`.
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
    # The client never populates this on the auto-fill path, so it stays 0
    # unless a caller sets it.
    defender_melee_reduction: float = 0.0
    gate_reduction: float = 0.0
    wall_reduction: float = 0.0
    moat_reduction: float = 0.0

    def apply_tool(
        self,
        tool,
        count: int,
        *,
        range_malus: float = 0.0,
        melee_malus: float = 0.0,
    ) -> "AttackerFlankEffects":
        """
        Fold a placed tool's contribution into these effects.

        ``AttackerFlankEffectVO.updateEffectsWithNewTool``: each tool adds its
        fortification and defense reductions times the number placed, which is
        why the client places tools before soldiers - the soldiers are then
        picked against a defense the tools have already dented.

        A tool's own ``effects`` may add range or melee defense maluses on top of
        its columns. Resolving those needs the game data and the target's area
        type, which this layer does not have, so the caller resolves them and
        passes them in - the same terms the strategy scored the tool on.

        Args:
            tool: The tool that was placed
            count: How many of it
            range_malus: Range-defense malus from the tool's effects, type 217
            melee_malus: Melee-defense malus from the tool's effects, type 215

        Returns:
            A new effects object; the original is unchanged
        """
        return self.model_copy(
            update={
                "wall_reduction": self.wall_reduction + tool.wall_bonus * count,
                "gate_reduction": self.gate_reduction + tool.gate_bonus * count,
                "moat_reduction": self.moat_reduction + tool.moat_bonus * count,
                "defender_range_reduction": (
                    self.defender_range_reduction + (tool.def_range_bonus + range_malus) * count
                ),
                "defender_melee_reduction": (
                    self.defender_melee_reduction + (tool.def_melee_bonus + melee_malus) * count
                ),
            }
        )

    def soldier_stack_attack_value(
        self,
        unit: UnitStats,
        free_items: int,
        available: int,
        attack_bonus: float = 0.0,
    ) -> int:
        """
        What a stack of this unit is worth on this flank.

        Mirrors ``AttackerFlankEffectVO.getSoldierStackAttackValue``: the unit's
        attack times the matching bonus, truncated, times however many of it
        actually fit. Which of the two attack columns is read follows the unit's
        role, not which column happens to be filled in.

        Args:
            unit: The unit being considered
            free_items: Remaining troop capacity of the flank
            available: How many of the unit the player owns
            attack_bonus: A flat addition to this unit's attack from an active
                global effect, added before the multiplier as the client does

        Returns:
            The stack's attack value, 0 for a unit with no matching role
        """
        buff = int(attack_bonus)
        if unit.is_melee:
            per_unit = int(_buffed(unit.melee_attack, buff) * self.melee_bonus)
        elif unit.is_ranged:
            per_unit = int(_buffed(unit.range_attack, buff) * self.range_bonus)
        else:
            return 0
        return per_unit * max(0, min(free_items, available))


def _buffed(attack: float, bonus: int) -> float:
    """
    ``SoldierUnitVO.buffedMeleeAttack``, and its ranged twin.

    A unit with nothing in the column it is being read on stays at zero: the
    guard is on the raw column, so the buff never lifts a unit off the floor.
    """
    return attack + bonus if attack > 0 else 0.0


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

    def melee_defense_value(self, melee_reduction: float = 0.0, range_reduction: float = 0.0) -> float:
        """Defense against a melee attack (``getMeleeDefenceValue``)."""
        return self.melee_units_melee_strength * (self.melee_bonus - melee_reduction) + (
            self.range_units_melee_strength * (self.range_bonus - range_reduction)
        )

    def range_defense_value(self, range_reduction: float = 0.0, melee_reduction: float = 0.0) -> float:
        """Defense against a ranged attack (``getRangeDefenceValue``)."""
        return self.range_units_range_strength * (self.range_bonus - range_reduction) + (
            self.melee_units_range_strength * (self.melee_bonus - melee_reduction)
        )

    @property
    def has_melee_defenders(self) -> bool:
        """Whether any melee-role defender holds this flank."""
        return bool(self.melee_units_melee_strength or self.melee_units_range_strength)

    @property
    def has_range_defenders(self) -> bool:
        """Whether any ranged-role defender holds this flank."""
        return bool(self.range_units_melee_strength or self.range_units_range_strength)

    def is_empty(self) -> bool:
        """Whether anything defends this flank at all."""
        return not (
            self.melee_units_melee_strength
            or self.melee_units_range_strength
            or self.range_units_melee_strength
            or self.range_units_range_strength
        )


__all__ = ["AttackerFlankEffects", "DefenderFlankEffects", "Flank"]
