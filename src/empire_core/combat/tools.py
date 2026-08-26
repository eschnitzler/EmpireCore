"""
Placing tools in a wave's tool slots.

Ported from ``AFillFlankStrategy.fillFlankWithTools`` and ``checkFlank``. The
mechanics are here; the strategies that choose *which* tool are supplied by the
caller, because the client's five are still being derived and a plausible
substitute would produce waves that look right and are not what the game builds.
"""

from __future__ import annotations

import logging
from typing import Protocol

from empire_core.gamedata import GameData, ToolStats

from .effects import AttackerFlankEffects, DefenderFlankEffects
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
        inventory: Inventory,
        game_data: GameData,
        *,
        free_items: int,
        attacker: AttackerFlankEffects,
        defender: DefenderFlankEffects | None,
    ) -> ToolStats | None: ...


def fill_flank_with_tools(
    capacity: int,
    slots: int,
    slot_type: int,
    inventory: Inventory,
    game_data: GameData,
    strategies: list[ToolStrategy],
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
        chosen: ToolStats | None = None
        while pool and chosen is None:
            candidate = pool[-1](
                inventory,
                game_data,
                free_items=free,
                attacker=attacker,
                defender=defender,
            )
            if candidate is not None and candidate.fits_slot(slot_type):
                chosen = candidate
            else:
                pool.pop()
        if chosen is None:
            break
        taken = inventory.deduct(chosen.wod_id, free)
        if not taken:
            break
        placed[chosen.wod_id] = placed.get(chosen.wod_id, 0) + taken
        free -= taken

    return list(placed.items())


def check_flank(
    tools: list[tuple[int, int]],
    units: list[tuple[int, int]],
    inventory: Inventory,
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


__all__ = ["ToolStrategy", "check_flank", "fill_flank_with_tools"]
