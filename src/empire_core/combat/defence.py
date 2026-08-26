"""
Building a defender's flank strength from an army composition.

Two sources of composition are supported: an NPC camp, whose defenders the
items payload lists offline, and an explicit stack list, which is what a spy
report gives for a player's castle.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from empire_core.gamedata import GameData, NpcCampDefence

from .bonuses import Bonus, CombatEffectType, EffectResolver, commander_bonuses
from .effects import DefenderFlankEffects, Flank

if TYPE_CHECKING:
    from empire_core.protocol.models import Commander
    from empire_core.services.spy_army import SpyArmy

logger = logging.getLogger(__name__)

# ClientConstCastle wall, gate and moat buildings, indexed by level - 1.
WALL_WOD_IDS = (501, 502, 503, 504, 505, 2542, 1984, 2543, 3182)
GATE_WOD_IDS = (450, 451, 452, 453, 469, 2544, 1985, 2545, 3183)
MOAT_WOD_IDS = (455, 830, 1987, 2546, 456, 831, 1988, 2547)

# DungeonConst: a camp's level follows from how often it has been beaten, and
# its walls from that level.
CAMP_LEVEL_FACTOR = 1.9
CAMP_LEVEL_POWER = 0.555
CAMP_KINGDOM_OFFSETS = {0: 1, 2: 20, 1: 35, 3: 45}


def camp_level(victories: int, kingdom_id: int = 0) -> int:
    """
    A camp's level, from its victory count (``DungeonConst.getLevel``).

    Args:
        victories: The camp's victory count, from ``MapAreaItem.victory_count``
        kingdom_id: Kingdom the camp sits in, which shifts the result
    """
    offset = CAMP_KINGDOM_OFFSETS.get(kingdom_id, 0)
    return int(CAMP_LEVEL_FACTOR * abs(victories) ** CAMP_LEVEL_POWER) + offset


def camp_fortification_levels(level: int) -> tuple[int, int]:
    """
    A camp's wall and gate levels (``DungeonConst.getWallUpgradeByLevel``).

    Returns:
        ``(wall_level, gate_level)``; camps have no moat.
    """
    upgrade = 1 if level < 11 else (2 if level < 24 else 3)
    return upgrade, upgrade


def fortification_bonuses(
    game_data: GameData,
    *,
    wall_level: int = 0,
    gate_level: int = 0,
    moat_level: int = 0,
) -> tuple[float, float, float]:
    """
    Wall, gate and moat protection as fractions, from building levels.

    Each level indexes the matching building, whose items column is a
    percentage; the client divides by 100 before using it as a defence.

    Args:
        game_data: Loaded tables
        wall_level: The defender's wall level, 0 for none
        gate_level: The defender's gate level
        moat_level: The defender's moat level

    Returns:
        ``(wall, gate, moat)`` as fractions
    """

    def bonus(ids: tuple[int, ...], level: int, attribute: str) -> float:
        if level <= 0 or level > len(ids):
            return 0.0
        row = game_data.fortifications.get(ids[level - 1])
        return (getattr(row, attribute) / 100) if row else 0.0

    return (
        bonus(WALL_WOD_IDS, wall_level, "wall_bonus"),
        bonus(GATE_WOD_IDS, gate_level, "gate_bonus"),
        bonus(MOAT_WOD_IDS, moat_level, "moat_bonus"),
    )


Stacks = Iterable[tuple[int, int]]


def defender_flank_effects(
    stacks: Stacks,
    game_data: GameData,
    *,
    flank: Flank | None = None,
    melee_bonus: float = 1.0,
    range_bonus: float = 1.0,
    wall_bonus: float = 0.0,
    gate_bonus: float = 0.0,
    moat_bonus: float = 0.0,
) -> DefenderFlankEffects:
    """
    Aggregate a flank's defenders into strength values.

    Mirrors ``FightScreenHelper.getDefendingUnitStrength``: each defender adds
    both its melee and its ranged defence, credited to the melee or ranged
    group according to its own role. Tools among the stacks add their wall,
    gate and moat bonuses, as the client's ``getDefenceBonuses`` does.

    Say which flank this is and the gate is dropped everywhere but the middle,
    which is what ``getDefenceBonuses`` returns - only the middle meets the gate,
    so gate tools are wasted anywhere else.

    Args:
        stacks: ``(wod_id, count)`` pairs defending this flank
        game_data: Loaded stats, for the defenders' defence values
        flank: Which flank these defenders hold; without it the gate is left
            alone
        melee_bonus: Defender melee multiplier (1.0 = unbuffed)
        range_bonus: Defender ranged multiplier
        wall_bonus: Base wall bonus as a fraction
        gate_bonus: Base gate bonus as a fraction
        moat_bonus: Base moat bonus as a fraction

    Returns:
        The flank's defender effects
    """
    melee_melee = melee_range = range_melee = range_range = 0.0
    unknown = 0

    for wod_id, count in stacks:
        if count <= 0:
            continue
        unit = game_data.get_unit(wod_id)
        if unit is None:
            # A tool defending the flank raises its fortification instead of
            # standing in the line. The client adds the bonus once per stack and
            # ignores how many the stack holds.
            tool = game_data.get_tool(wod_id)
            if tool is None:
                unknown += 1
                continue
            wall_bonus += tool.wall_bonus
            gate_bonus += tool.gate_bonus
            moat_bonus += tool.moat_bonus
            continue
        if unit.is_melee:
            melee_melee += unit.melee_defence * count
            melee_range += unit.range_defence * count
        elif unit.is_ranged:
            range_melee += unit.melee_defence * count
            range_range += unit.range_defence * count

    if unknown:
        logger.warning(f"{unknown} defending stack(s) matched no known unit or tool")

    if flank is not None and flank is not Flank.MIDDLE:
        gate_bonus = 0.0

    return DefenderFlankEffects(
        melee_units_melee_strength=melee_melee,
        melee_units_range_strength=melee_range,
        range_units_melee_strength=range_melee,
        range_units_range_strength=range_range,
        melee_bonus=melee_bonus,
        range_bonus=range_bonus,
        wall_bonus=wall_bonus,
        gate_bonus=gate_bonus,
        moat_bonus=moat_bonus,
    )


# The defending castellan's own effect types, which are a different set from
# the attacker's: 6/7/8 raise the fortification, 9/10 the defenders themselves,
# 31 every defender on any flank, and 49/50/32 one position each.
DEFENDER_WALL_BONUS_TYPE = 6
DEFENDER_GATE_BONUS_TYPE = 7
DEFENDER_MOAT_BONUS_TYPE = 8
DEFENCE_BONUS_TYPE = 31
DEFENCE_BOOST_YARD_TYPE = 32
DEFENCE_BOOST_FRONT_TYPE = 49
DEFENCE_BOOST_FLANK_TYPE = 50


def castellan_defence_multiplier(
    resolver: EffectResolver,
    bonuses: Sequence[Bonus],
    *,
    flank: Flank,
    melee: bool,
    area_type: int | None = None,
) -> float:
    """
    How much a defending castellan multiplies its own defenders by.

    ``CastleEffectsHelper.getFullDefenseBonusForLordByFlankAndAreaType``: the
    all-flank defence bonus, plus the melee or ranged one, plus whichever
    position-specific boost applies. The result is a percentage the caller adds
    to 1.0.

    One client quirk is kept: the courtyard boost (type 32) is added on the
    **middle** flank, not the courtyard, so it never reaches the courtyard fight
    through this path. The client reads it as ``rawValues[0]`` rather than
    ``strength``, which for a plain value is the same number - both return
    ``_value``, and the cap was already applied when the effects were merged.

    Args:
        resolver: Effect resolver over the loaded tables
        bonuses: The castellan's bonuses, from ``commander_bonuses``
        flank: Which flank is being defended
        melee: True for the melee multiplier, False for the ranged one
        area_type: The target's area type, which scopes the effects

    Returns:
        The percentage to add to 1.0
    """
    total = resolver.accumulate(bonuses, DEFENCE_BONUS_TYPE, area_type=area_type)
    total += resolver.accumulate(
        bonuses,
        CombatEffectType.MELEE_BONUS if melee else CombatEffectType.RANGE_BONUS,
        area_type=area_type,
    )
    if flank is Flank.MIDDLE:
        total += resolver.accumulate(bonuses, DEFENCE_BOOST_FRONT_TYPE, area_type=area_type)
        # The client adds the courtyard boost here, on the middle flank.
        total += resolver.accumulate(bonuses, DEFENCE_BOOST_YARD_TYPE, area_type=area_type)
    elif flank in (Flank.LEFT, Flank.RIGHT):
        total += resolver.accumulate(bonuses, DEFENCE_BOOST_FLANK_TYPE, area_type=area_type)
    return total / 100


def castellan_fortification(
    resolver: EffectResolver,
    bonuses: Sequence[Bonus],
    *,
    area_type: int | None = None,
) -> tuple[float, float, float]:
    """
    What a defending castellan adds to its castle's wall, gate and moat.

    ``getDefenceBonuses`` adds these on top of the structures' own protection,
    as fractions.
    """
    return tuple(  # type: ignore[return-value]
        resolver.accumulate(bonuses, effect_type, area_type=area_type) / 100
        for effect_type in (DEFENDER_WALL_BONUS_TYPE, DEFENDER_GATE_BONUS_TYPE, DEFENDER_MOAT_BONUS_TYPE)
    )


def spied_castle_defence(
    game_data: GameData,
    spy_army: "SpyArmy",
    *,
    wall_bonus: float = 0.0,
    gate_bonus: float = 0.0,
    moat_bonus: float = 0.0,
    melee_bonus: float = 1.0,
    range_bonus: float = 1.0,
    castellan: "Commander | None" = None,
    area_type: int | None = None,
) -> dict[Flank, DefenderFlankEffects]:
    """
    What defends a spied castle, per flank.

    ``getDefenceBonuses`` builds one of these per flank from that flank's own
    stacks, so the flanks differ: a defending tool raises the fortification of
    the flank it sits on and no other. That is why the game asks for a different
    number of siege tools on the left than on the right, and a uniform
    fortification cannot reproduce it.

    The keep's stacks become the courtyard flank.

    Args:
        game_data: Loaded stats
        spy_army: The report's positional army, from ``aci``'s ``S`` block
        wall_bonus: The castle's own wall protection, as a fraction
        gate_bonus: Its gate protection; only the middle flank keeps it
        moat_bonus: Its moat protection
        melee_bonus: Defender melee multiplier before the castellan
        range_bonus: Defender ranged multiplier before the castellan
        castellan: The defending castellan, from ``aci``'s ``B`` block. Its
            equipment raises both the fortification and the defenders, and
            differently per flank
        area_type: The target's area type, which scopes the castellan's effects

    Returns:
        Effects per flank
    """
    resolver = EffectResolver(game_data)
    castellan_bonuses = commander_bonuses(castellan) if castellan is not None else []
    if castellan_bonuses:
        wall, gate, moat = castellan_fortification(resolver, castellan_bonuses, area_type=area_type)
        wall_bonus += wall
        gate_bonus += gate
        moat_bonus += moat

    def multiplier(flank: Flank, *, melee: bool) -> float:
        base = melee_bonus if melee else range_bonus
        if not castellan_bonuses:
            return base
        return base + castellan_defence_multiplier(
            resolver, castellan_bonuses, flank=flank, melee=melee, area_type=area_type
        )

    # Support troops hold every flank, the courtyard included, as the client
    # concatenates them onto each.
    support = [(stack.wod_id, stack.count) for stack in spy_army.support]
    per_flank = {
        Flank.LEFT: spy_army.left,
        Flank.MIDDLE: spy_army.middle,
        Flank.RIGHT: spy_army.right,
        Flank.YARD: spy_army.keep,
    }
    return {
        flank: defender_flank_effects(
            [(stack.wod_id, stack.count) for stack in stacks] + support,
            game_data,
            flank=flank,
            wall_bonus=wall_bonus,
            gate_bonus=gate_bonus,
            moat_bonus=moat_bonus,
            melee_bonus=multiplier(flank, melee=True),
            range_bonus=multiplier(flank, melee=False),
        )
        for flank, stacks in per_flank.items()
    }


def npc_camp_defence(
    game_data: GameData,
    victories: int,
    kingdom_id: int = 0,
) -> dict[Flank, DefenderFlankEffects] | None:
    """
    What defends an NPC camp, per flank, without asking the server.

    The items payload lists a camp's defenders by victory count, so a robber
    baron camp's defence can be computed offline instead of spying it.

    Args:
        game_data: Loaded stats
        victories: The camp's victory count (negative for a robber baron camp)
        kingdom_id: Kingdom the camp sits in

    Returns:
        Effects per flank, or None when the payload lists no such camp. The
        camp's own wall and gate protection is included, derived from the level
        its victory count implies.
    """
    row = game_data.dungeon_defence(victories, kingdom_id)
    if row is None:
        return None

    level = camp_level(victories, kingdom_id)
    wall_level, gate_level = camp_fortification_levels(level)
    wall, gate, moat = fortification_bonuses(game_data, wall_level=wall_level, gate_level=gate_level)

    # Defending tools (row.tools_*) are not folded in: their contributions live
    # in the tool's unresolved effects block, so the fortification here is the
    # camp's own walls.
    per_flank = {
        Flank.LEFT: row.units_left,
        Flank.MIDDLE: row.units_middle,
        Flank.RIGHT: row.units_right,
        Flank.YARD: row.units_keep,
    }
    return {
        flank: defender_flank_effects(units, game_data, flank=flank, wall_bonus=wall, gate_bonus=gate, moat_bonus=moat)
        for flank, units in per_flank.items()
    }


def event_camp_defence(
    game_data: GameData,
    table: str,
    victories: int,
) -> dict[Flank, DefenderFlankEffects] | None:
    """
    What defends an event camp, per flank.

    Nomad, samurai, faction invasion and alliance invasion camps are described
    differently from robber baron camps: instead of a per-flank composition they
    give a defence strength, a unit and tool list, and wall and gate bonuses.
    The same units defend every flank, so the composition is split evenly and
    the fortification applied to each.

    Args:
        game_data: Loaded tables
        table: One of ``empire_core.gamedata.CAMP_TABLES``
        victories: The camp's victory count

    Returns:
        Effects per flank, or None when no such camp is listed. Unit counts are
        not given by these tables, so the strengths reflect one of each listed
        unit; treat the wall and gate bonuses as the reliable part.
    """
    row = next(
        (camp for camp in game_data.camps.get(table, []) if camp.count_victory == victories),
        None,
    )
    if row is None:
        return None
    return _camp_flanks(row, game_data)


def _camp_flanks(row: NpcCampDefence, game_data: GameData) -> dict[Flank, DefenderFlankEffects]:
    stacks = [(wod_id, 1) for wod_id in row.defence_unit_ids]
    return {
        flank: defender_flank_effects(
            stacks,
            game_data,
            wall_bonus=row.wall_bonus / 100,
            gate_bonus=row.gate_bonus / 100,
        )
        for flank in (Flank.LEFT, Flank.MIDDLE, Flank.RIGHT, Flank.YARD)
    }


__all__ = [
    "camp_fortification_levels",
    "camp_level",
    "defender_flank_effects",
    "event_camp_defence",
    "fortification_bonuses",
    "castellan_defence_multiplier",
    "castellan_fortification",
    "npc_camp_defence",
    "spied_castle_defence",
]
