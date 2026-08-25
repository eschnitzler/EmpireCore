"""
How big a wave may be, ported from the client's ``CombatConst``.

A wave's capacity is a function of one effective level: the attacker's own
level, or the target's minimum defence level when that is higher. The client
derives every number below from it, so a caller does not have to guess how many
troops a flank holds.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict

from .effects import Flank

# Attackers per wave stops growing past level 69.
MAX_ATTACKERS_ABOVE_69 = 320
WAVE_UNLOCK_LEVELS = (0, 13, 26, 51)
CONQUER_ADDITIONAL_WAVES = 2

# Per-slot unlock levels. A flank has as many slots as its list has entries,
# and a slot exists once the effective level reaches its entry.
UNIT_SLOT_LEVELS_FLANK = (0, 13)
UNIT_SLOT_LEVELS_MIDDLE = (0, 0, 13, 13, 26, 26)
TOOL_SLOT_LEVELS_FLANK = (0, 37)
TOOL_SLOT_LEVELS_MIDDLE = (0, 11, 37)

# The slot type a tool must fit to go in these slots (ClientConstCombat).
TOOL_SLOT_TYPE_MIDDLE = 1
TOOL_SLOT_TYPE_FLANK = 2


def max_attackers(level: int) -> int:
    """Total units a wave holds (``CombatConst.getMaxAttackers``)."""
    if level <= 69:
        return min(260, 5 * level + 8)
    return MAX_ATTACKERS_ABOVE_69


def flank_soldier_capacity(level: int, bonus_percent: float = 0.0) -> int:
    """
    Units one side flank holds (``getAmountSoldiersFlank``).

    ``bonus_percent`` is the client's "units on the flank" bonus, which comes
    from the selected commander's equipment for the target's area type.
    """
    return int(math.ceil(0.2 * max_attackers(level) * (1 + bonus_percent / 100)))


def middle_soldier_capacity(level: int, bonus_percent: float = 0.0) -> int:
    """
    Units the middle holds (``getAmountSoldiersMiddle``).

    The middle takes whatever the two side flanks leave, so their unbonused
    size is what is subtracted. ``bonus_percent`` is the client's "units on the
    front" bonus, which is a different effect from the flank bonus - the two
    scale the middle and the sides independently.
    """
    without_bonus = int(math.ceil(0.2 * max_attackers(level)))
    return int(math.ceil((max_attackers(level) - 2 * without_bonus) * (1 + bonus_percent / 100)))


def flank_tool_capacity(level: int, bonus: float = 0.0) -> int:
    """Tools one side flank holds (``getTotalAmountTools`` for a flank)."""
    if level < 37:
        return 10
    if level < 50:
        return 20
    if level < 69:
        return 30
    return int(math.ceil(40 + bonus))


def middle_tool_capacity(level: int) -> int:
    """Tools the middle holds (``getTotalAmountTools`` for the middle)."""
    if level < 11:
        return 10
    if level < 37:
        return 20
    if level < 50:
        return 30
    if level < 69:
        return 40
    return 50


def unlocked_slots(unlock_levels: tuple[int, ...], level: int) -> int:
    """How many of a flank's slots exist at this level."""
    return sum(1 for unlock_level in unlock_levels if level >= unlock_level)


def max_wave_count(level: int, *, conquer: bool = False, bonus: int = 0) -> int:
    """
    How many waves an attack may carry (``getMaxWaveCountWithBonus``).

    Args:
        level: Effective level
        conquer: A conquest attack gets extra waves
        bonus: Extra waves from the ADDITIONAL_WAVE legend skill
    """
    count = 1
    for index in range(len(WAVE_UNLOCK_LEVELS) - 1, -1, -1):
        if level >= WAVE_UNLOCK_LEVELS[index]:
            count = index + 1
            break
    if conquer:
        count += CONQUER_ADDITIONAL_WAVES
    return count + bonus


class WaveCapacity(BaseModel):
    """
    The size of one wave at a given effective level.

    Build it with :meth:`for_level` rather than by hand::

        capacity = WaveCapacity.for_level(70)
        capacity.soldier_capacity(Flank.MIDDLE)   # 192
        capacity.unit_slots(Flank.LEFT)           # 2
    """

    model_config = ConfigDict(extra="forbid")

    level: int
    flank_soldiers: int
    middle_soldiers: int
    flank_tools: int
    middle_tools: int
    flank_unit_slots: int
    middle_unit_slots: int
    flank_tool_slots: int
    middle_tool_slots: int

    @classmethod
    def for_level(
        cls,
        level: int,
        *,
        flank_bonus_percent: float = 0.0,
        front_bonus_percent: float = 0.0,
        tool_bonus: float = 0.0,
    ) -> "WaveCapacity":
        """
        Derive a wave's capacity from the effective level and the unit bonuses.

        The client resizes the flank containers after building a wave, using two
        separate effects: a "units on the flank" bonus for the two sides and a
        "units on the front" bonus for the middle, both read from the selected
        commander's equipment for the target's area type. Pass them to get the
        numbers the attack dialog shows; with both at zero these are the
        unbuffed base capacities.

        Args:
            level: The attacker's level, or the target's minimum defence level
                when that is higher - the client uses ``max`` of the two
            flank_bonus_percent: Percentage bonus to units on each side flank
            front_bonus_percent: Percentage bonus to units in the middle
            tool_bonus: Extra flank tool capacity, e.g. from the
                ADDITIONAL_ATTACK_TOOL_AMOUNT_FLANK legend skill
        """
        return cls(
            level=level,
            flank_soldiers=flank_soldier_capacity(level, flank_bonus_percent),
            middle_soldiers=middle_soldier_capacity(level, front_bonus_percent),
            flank_tools=flank_tool_capacity(level, tool_bonus),
            middle_tools=middle_tool_capacity(level),
            flank_unit_slots=unlocked_slots(UNIT_SLOT_LEVELS_FLANK, level),
            middle_unit_slots=unlocked_slots(UNIT_SLOT_LEVELS_MIDDLE, level),
            flank_tool_slots=unlocked_slots(TOOL_SLOT_LEVELS_FLANK, level),
            middle_tool_slots=unlocked_slots(TOOL_SLOT_LEVELS_MIDDLE, level),
        )

    def soldier_capacity(self, flank: Flank) -> int:
        """Units this flank holds."""
        return self.middle_soldiers if flank == Flank.MIDDLE else self.flank_soldiers

    def tool_capacity(self, flank: Flank) -> int:
        """Tools this flank holds."""
        return self.middle_tools if flank == Flank.MIDDLE else self.flank_tools

    def unit_slots(self, flank: Flank) -> int:
        """Unlocked unit slots on this flank."""
        return self.middle_unit_slots if flank == Flank.MIDDLE else self.flank_unit_slots

    def tool_slots(self, flank: Flank) -> int:
        """Unlocked tool slots on this flank."""
        return self.middle_tool_slots if flank == Flank.MIDDLE else self.flank_tool_slots

    def tool_slot_type(self, flank: Flank) -> int:
        """Which slot type a tool must fit for this flank."""
        return TOOL_SLOT_TYPE_MIDDLE if flank == Flank.MIDDLE else TOOL_SLOT_TYPE_FLANK

    def total_soldiers(self) -> int:
        """Units the whole wave holds across its three flanks."""
        return 2 * self.flank_soldiers + self.middle_soldiers


__all__ = [
    "CONQUER_ADDITIONAL_WAVES",
    "TOOL_SLOT_LEVELS_FLANK",
    "TOOL_SLOT_LEVELS_MIDDLE",
    "TOOL_SLOT_TYPE_FLANK",
    "TOOL_SLOT_TYPE_MIDDLE",
    "UNIT_SLOT_LEVELS_FLANK",
    "UNIT_SLOT_LEVELS_MIDDLE",
    "WAVE_UNLOCK_LEVELS",
    "WaveCapacity",
    "flank_soldier_capacity",
    "flank_tool_capacity",
    "max_attackers",
    "max_wave_count",
    "middle_soldier_capacity",
    "middle_tool_capacity",
    "unlocked_slots",
]
