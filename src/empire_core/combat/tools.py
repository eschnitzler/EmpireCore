"""
Placing tools in a wave's tool slots.

Ported from ``AFillFlankStrategy.fillFlankWithTools`` and ``checkFlank``. The
mechanics are here; the strategies that choose *which* tool are supplied by the
caller, because the client's five are still being derived and a plausible
substitute would produce waves that look right and are not what the game builds.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from empire_core.gamedata import GameData, ToolStats

from .effects import AttackerFlankEffects, DefenderFlankEffects

if TYPE_CHECKING:
    from .solver import Inventory

logger = logging.getLogger(__name__)


class ToolStrategy(Protocol):
    """
    Chooses one tool for a slot, or None when it has nothing to offer.

    The client keeps five of these in a pool and pops one whenever it fails to
    produce a tool that fits the slot, so a strategy returning None retires for
    the rest of the flank.
    """

    def __call__(
        self,
        inventory: "Inventory",
        game_data: GameData,
        *,
        free_items: int,
        attacker: AttackerFlankEffects,
        defender: DefenderFlankEffects | None,
    ) -> tuple[ToolStats, int] | None: ...


@dataclass
class ReduceDefenceBonusStrategy:
    """
    Picks the tool that best cancels one of the defender's bonuses.

    Ported from ``AReduceDefenseBonusStrategy.pickToolByStrategy``. Given how
    much of a defence remains after the attacker's own reduction, it prefers the
    tool that cancels it outright with the *fewest* units; failing that, the one
    that removes the most in the units that fit. A defence already at or below
    zero needs no tool, and the strategy retires.

    The client builds five of these, one per defender bonus; see
    :func:`default_tool_strategies`.
    """

    name: str
    tool_bonus: Callable[[ToolStats], float]
    defender_bonus: Callable[[AttackerFlankEffects, DefenderFlankEffects], float]
    requires: Callable[[DefenderFlankEffects], bool] | None = None

    def __call__(
        self,
        inventory: "Inventory",
        game_data: GameData,
        *,
        free_items: int,
        attacker: AttackerFlankEffects,
        defender: DefenderFlankEffects | None,
    ) -> tuple[ToolStats, int] | None:
        if defender is None:
            return None
        # The range and melee strategies stand down when the defender has no
        # defender of that kind at all.
        if self.requires is not None and not self.requires(defender):
            return None

        remaining = self.defender_bonus(attacker, defender)
        if remaining <= 0:
            return None

        best_exact: tuple[ToolStats, int] | None = None
        best_partial: tuple[ToolStats, int] | None = None
        best_partial_value = 0.0

        for wod_id, available in inventory.counts.items():
            tool = game_data.get_tool(wod_id)
            if tool is None or not tool.is_attack_tool or available <= 0:
                continue
            bonus = self.tool_bonus(tool)
            if bonus <= 0:
                continue
            needed = math.ceil(remaining / bonus)
            limit = tool.amount_per_wave if tool.amount_per_wave > 0 else free_items
            placeable = int(min(available, free_items, limit))
            if placeable <= 0:
                continue
            if needed <= placeable:
                if best_exact is None or needed < best_exact[1]:
                    best_exact = (tool, needed)
            else:
                value = bonus * placeable
                if value > best_partial_value:
                    best_partial, best_partial_value = (tool, placeable), value

        return best_exact or best_partial


def default_tool_strategies() -> list[ReduceDefenceBonusStrategy]:
    """
    The client's five strategies, in pool order.

    ``fillToolStrategyPool`` pushes moat, range, melee, gate then wall, and pops
    from the end - so wall is tried first and moat last.
    """
    return [
        ReduceDefenceBonusStrategy(
            "moat",
            lambda tool: tool.moat_bonus,
            lambda a, d: d.moat_bonus - a.moat_reduction,
        ),
        ReduceDefenceBonusStrategy(
            "range",
            lambda tool: tool.def_range_bonus,
            lambda a, d: d.range_bonus - a.defender_range_reduction,
            requires=lambda d: d.has_range_defenders,
        ),
        ReduceDefenceBonusStrategy(
            "melee",
            lambda tool: tool.def_melee_bonus,
            lambda a, d: d.melee_bonus - a.defender_melee_reduction,
            requires=lambda d: d.has_melee_defenders,
        ),
        ReduceDefenceBonusStrategy(
            "gate",
            lambda tool: tool.gate_bonus,
            lambda a, d: d.gate_bonus - a.gate_reduction,
        ),
        ReduceDefenceBonusStrategy(
            "wall",
            lambda tool: tool.wall_bonus,
            lambda a, d: d.wall_bonus - a.wall_reduction,
        ),
    ]


def fill_flank_with_tools(
    capacity: int,
    slots: int,
    slot_type: int,
    inventory: "Inventory",
    game_data: GameData,
    strategies: Sequence[ToolStrategy],
    *,
    attacker: AttackerFlankEffects | None = None,
    defender: DefenderFlankEffects | None = None,
) -> list[tuple[int, int]]:
    """
    Fill one flank's tool slots.

    Follows the client: for each free slot, ask the last strategy in the pool
    for a tool. A tool that does not fit this slot type retires that strategy
    and the next one is tried; when the pool empties, filling stops. A tool
    already present in the flank merges into its existing slot rather than
    taking a new one.

    Args:
        capacity: The flank's tool capacity
        slots: How many unlocked tool slots the flank has
        slot_type: The slot type a tool must fit, from ``WaveCapacity``
        inventory: Pool to draw from; placed tools are deducted
        game_data: Loaded tool stats
        strategies: The strategy pool, tried from the end
        attacker: Attacker multipliers, which each placed tool feeds
        defender: The defender's strength on this flank

    Returns:
        ``(wod_id, count)`` per filled slot
    """
    attacker = attacker or AttackerFlankEffects()
    pool = list(strategies)
    placed: dict[int, int] = {}
    free = capacity

    for _slot in range(max(0, slots)):
        if free <= 0 or not pool:
            break
        chosen: tuple[ToolStats, int] | None = None
        while pool and chosen is None:
            candidate = pool[-1](
                inventory,
                game_data,
                free_items=free,
                attacker=attacker,
                defender=defender,
            )
            if candidate is not None and candidate[0].fits_slot(slot_type):
                chosen = candidate
            else:
                pool.pop()
        if chosen is None:
            break
        tool, wanted = chosen
        taken = inventory.deduct(tool.wod_id, min(wanted, free))
        if not taken:
            break
        placed[tool.wod_id] = placed.get(tool.wod_id, 0) + taken
        free -= taken

    return list(placed.items())


def check_flank(
    tools: list[tuple[int, int]],
    units: list[tuple[int, int]],
    inventory: "Inventory",
) -> bool:
    """
    Drop a flank's tools when it has no units to use them.

    ``AFillFlankStrategy.checkFlank``: tools without units are returned to the
    inventory rather than sent, since they would be spent for nothing.

    Args:
        tools: The flank's placed tools
        units: The flank's placed units
        inventory: Pool the tools return to

    Returns:
        True when the flank stands, False when its tools were taken back
    """
    if sum(count for _wod_id, count in units) > 0:
        return True
    for wod_id, count in tools:
        inventory.counts[wod_id] = inventory.counts.get(wod_id, 0) + count
    tools.clear()
    return False


__all__ = [
    "ReduceDefenceBonusStrategy",
    "ToolStrategy",
    "check_flank",
    "default_tool_strategies",
    "fill_flank_with_tools",
]
