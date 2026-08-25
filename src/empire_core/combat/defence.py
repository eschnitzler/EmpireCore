"""
Building a defender's flank strength from an army composition.

Two sources of composition are supported: an NPC camp, whose defenders the
items payload lists offline, and an explicit stack list, which is what a spy
report gives for a player's castle.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from empire_core.gamedata import GameData

from .effects import DefenderFlankEffects, Flank

logger = logging.getLogger(__name__)

Stacks = Iterable[tuple[int, int]]


def defender_flank_effects(
    stacks: Stacks,
    game_data: GameData,
    *,
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

    Args:
        stacks: ``(wod_id, count)`` pairs defending this flank
        game_data: Loaded stats, for the defenders' defence values
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
            # A tool defending the flank contributes fortification, not units.
            tool = game_data.get_tool(wod_id)
            if tool is None:
                unknown += 1
            continue
        if unit.is_melee:
            melee_melee += unit.melee_defence * count
            melee_range += unit.range_defence * count
        elif unit.is_ranged:
            range_melee += unit.melee_defence * count
            range_range += unit.range_defence * count

    if unknown:
        logger.warning(f"{unknown} defending stack(s) matched no known unit or tool")

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
        Effects per flank, or None when the payload lists no such camp. Wall,
        gate and moat bonuses are left at zero; see the note in the body.
    """
    row = game_data.dungeon_defence(victories, kingdom_id)
    if row is None:
        return None

    # Defending tools (row.tools_*) are not folded in yet: their wall, gate and
    # moat contributions live in the tool's unresolved effects block, so the
    # returned bonuses cover units only.
    per_flank = {
        Flank.LEFT: row.units_left,
        Flank.MIDDLE: row.units_middle,
        Flank.RIGHT: row.units_right,
        Flank.YARD: row.units_keep,
    }
    return {flank: defender_flank_effects(units, game_data) for flank, units in per_flank.items()}


__all__ = ["defender_flank_effects", "npc_camp_defence"]
