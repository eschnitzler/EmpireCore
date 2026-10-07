"""
The parts of wave filling that need no server: the inventory pool, the
support tools and the estimate of the target's defense.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from empire_core.attack.targeting import _row_item, _Target
from empire_core.combat import (
    DefenderFlankEffects,
    Inventory,
    fortification_bonuses,
    npc_camp_defense,
    spied_castle_defense,
)
from empire_core.enums import Flank
from empire_core.gamedata import EMPTY_WOD_ID, GameData, ToolStats
from empire_core.map.models.items import MapAreaItem

if TYPE_CHECKING:
    from empire_core.gamedata import Tool


def _support_tools(game_data: GameData, wod_ids: Sequence[Tool | int | None] | None) -> list[ToolStats]:
    """The tools behind an ``AST`` list; ``toolsSupportWodIds`` sends -1 for an empty slot."""
    tools = []
    for wod_id in wod_ids or ():
        if wod_id is None or wod_id == EMPTY_WOD_ID:
            continue
        tool = game_data.get_tool(wod_id)
        if tool is None:
            raise ValueError(f"Support tool {wod_id} is not a tool in the items payload")
        tools.append(tool)
    return tools


def _pool(game_data: GameData, amounts: dict[int, int]) -> Inventory:
    """The units and tools of a wod/amount inventory, as a pool to fill from."""
    return Inventory(
        {wod_id: n for wod_id, n in amounts.items() if game_data.is_unit(wod_id) or game_data.is_tool(wod_id)}
    )


def _has_row_protection(item: MapAreaItem) -> bool:
    """
    Whether the row gives the target's own wall, gate and moat protection.

    Alien, invasion, alliance and daimyo camps and the wolf king return the
    row's value as their ``baseWallBonus``, ``baseGateBonus`` and
    ``baseMoatBonus`` (e.g. ``AAlienInvasionMapobjectVO``, bundle lines
    41571-41577); a castle-style row gives building levels instead.
    """
    return any(bonus is not None for bonus in (item.base_wall_bonus, item.base_gate_bonus, item.base_moat_bonus))


def _target_defense(game_data: GameData, target: "_Target") -> dict[Flank, DefenderFlankEffects] | None:
    """
    What defends the target, per flank.

    A camp's defenders and walls come from the items payload. A castle's
    fortification comes from the structure levels in its map row, and its
    defenders from the spy block when one is available - each flank's own
    stacks, so a defending tool raises only the flank it stands on.
    """
    if target.camp_victories is not None:
        return npc_camp_defense(game_data, target.camp_victories, target.camp_kingdom_id)
    item = _row_item(target.row)
    if item is None:
        return None
    if _has_row_protection(item):
        # FightScreenHelper.getDefenceBonuses (bundle line 19148) divides the target's
        # baseWallBonus (and gate, moat) by 100; the camps whose row carries them return it as sent.
        wall = (item.base_wall_bonus or 0.0) / 100
        gate = (item.base_gate_bonus or 0.0) / 100
        moat = (item.base_moat_bonus or 0.0) / 100
    else:
        wall, gate, moat = fortification_bonuses(
            game_data,
            wall_level=item.wall_level or 0,
            gate_level=item.gate_level or 0,
            moat_level=item.moat_level or 0,
        )
    if target.spy_army is not None:
        return spied_castle_defense(
            game_data,
            target.spy_army,
            wall_bonus=wall,
            gate_bonus=gate,
            moat_bonus=moat,
            castellan=target.castellan,
            defender_legend_skill_ids=target.defender_legend_skill_ids,
            area_type=target.area_type,
        )
    # Without a spy report the defending army is unknown, so only the
    # target's fortification is modeled. Only the middle flank meets the
    # gate.
    return {
        flank: DefenderFlankEffects(
            wall_bonus=wall,
            gate_bonus=gate if flank is Flank.MIDDLE else 0.0,
            moat_bonus=moat,
        )
        for flank in (Flank.LEFT, Flank.MIDDLE, Flank.RIGHT, Flank.YARD)
    }
