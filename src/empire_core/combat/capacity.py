"""
How big a wave may be, ported from the client's ``CombatConst``.

A wave's capacity is a function of one effective level: the attacker's own
level, or the target's minimum defense level when that is higher. The client
derives every number below from it, so a caller does not have to guess how many
troops a flank holds.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict

from empire_core.protocol.models.map import MapItemType

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


# A fight is legendary when a capped attacker hits a capped player. Legend
# skills only contribute to a wave then - which is why the same attacker fits
# 159 units per flank against a level 70 player and 65 against a level 28 one.
LEVEL_CAP = 70


def is_legendary_fight(attacker_level: int, target_level: int, *, target_is_player: bool) -> bool:
    """
    Whether legend skills contribute to this attack.

    Both sides must be at the level cap and the target must be a player: an NPC
    camp is never a legendary fight however high its level.
    """
    return target_is_player and attacker_level >= LEVEL_CAP and target_level >= LEVEL_CAP


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


def boost_to_modifier(boost: float) -> float:
    """
    Turn a "boost" effect into a multiplier (``EffectConst.boostToModifier``).

    A boost of 0 is a multiplier of 1.0; the client adds it to a base of 100 and
    scales by 1/100, flooring at zero.
    """
    return max((100 + boost) * 0.01, 0.0)


# A wave is sized by the higher of the target owner's level and a floor the
# area type sets: ``CastleAttackWaveVO`` opens with ``e = int(max(e, t))`` and
# ``addAdditionalWave`` picks ``t`` from the area type. A king's tower, monument
# and laboratory take OutpostConst's 70; a capital and a metropolis read their
# landmark's own minDefenseLevel, which is not in the items payload, so those
# two have to be supplied.
AREA_TYPE_LEVEL_FLOORS: dict[int, int] = {
    int(MapItemType.KINGS_TOWER): 70,
    int(MapItemType.MONUMENT): 70,
    int(MapItemType.LABORATORY): 70,
}

LANDMARK_FLOOR_AREA_TYPES = frozenset({int(MapItemType.CAPITAL), int(MapItemType.METRO)})


def minimum_owner_level(
    target_level: int,
    area_type: int | None = None,
    *,
    landmark_min_level: int = 0,
) -> int:
    """
    The level a target defends at, whoever owns it.

    ``AInteractiveMapobjectVO.minimumOwnerLevel`` returns the owner's own level,
    and the landmark subclasses override it with a fixed one: a king's tower,
    monument and laboratory answer 70, a capital and a metropolis their
    landmark's ``minDefenseLevel``.

    Args:
        target_level: The target owner's level
        area_type: The target's area type
        landmark_min_level: The landmark's ``minDefenseLevel``, for a capital or
            a metropolis; those two read it at runtime and it is not in the
            items payload

    Returns:
        The level the area type defends at
    """
    if area_type is None:
        return int(target_level)
    if area_type in LANDMARK_FLOOR_AREA_TYPES:
        return int(landmark_min_level)
    return int(AREA_TYPE_LEVEL_FLOORS.get(area_type, target_level))


def wave_level(
    target_level: int,
    area_type: int | None = None,
    *,
    landmark_min_level: int = 0,
) -> int:
    """
    The level a wave is actually sized by.

    Some targets defend at a floor of their own however low their owner's level
    is: attack a level 12 player's monument and the wave is built for level 70.

    Returns:
        The higher of the owner's level and the area type's own level
    """
    return max(
        int(target_level),
        minimum_owner_level(target_level, area_type, landmark_min_level=landmark_min_level),
    )


YARD_SLOTS = 8
"""Slots the courtyard wave offers. All eight are open from level 0."""


def yard_capacity(
    attacker_level: int,
    target_level: int,
    *,
    bonus: float = 0.0,
    boost: float = 0.0,
) -> int:
    """
    Units the courtyard - the final assault - wave holds.

    ``CombatConst.getMaxUnitsInReinforcementWave``: unlike a flank, this one
    grows with *both* levels, and the additions are absolute units rather than
    percentages.

    Verified against four captured dialogs from one account, which give an
    identical implied bonus of 2872 at target levels 1, 13, 45 and 70:
    3109, 3349, 3989 and 4489.

    Args:
        attacker_level: The attacker's own level
        target_level: The target owner's level, or the minimum owner level when
            the target is under conquer control
        bonus: Absolute unit bonus, effect type 179
        boost: Percentage boost, effect type 180, applied as a multiplier last

    Returns:
        The courtyard wave's capacity
    """
    base = 20 * math.sqrt(max(0, attacker_level)) + 50 + 20 * target_level + int(bonus)
    # JS Math.round is half-up; Python's round() goes to even.
    return math.floor(base * boost_to_modifier(boost) + 0.5)


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
            level: The *target owner's* level. The client sizes a wave from
                ``attackInfoVO.targetOwnerLevel``, so a small defender caps the
                wave however strong the attacker is
            flank_bonus_percent: Total percentage bonus to units on each side
                flank - commander equipment, the general's skills, and legend
                skills when the fight is legendary
            front_bonus_percent: The same for the middle
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
    "AREA_TYPE_LEVEL_FLOORS",
    "LANDMARK_FLOOR_AREA_TYPES",
    "WAVE_UNLOCK_LEVELS",
    "YARD_SLOTS",
    "minimum_owner_level",
    "wave_level",
    "boost_to_modifier",
    "is_legendary_fight",
    "WaveCapacity",
    "flank_soldier_capacity",
    "flank_tool_capacity",
    "max_attackers",
    "max_wave_count",
    "middle_soldier_capacity",
    "middle_tool_capacity",
    "unlocked_slots",
    "yard_capacity",
]
