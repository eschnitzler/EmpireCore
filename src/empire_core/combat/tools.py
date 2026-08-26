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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from empire_core.gamedata import GameData, ToolStats

from .bonuses import parse_effect_spec
from .effects import AttackerFlankEffects, DefenderFlankEffects

if TYPE_CHECKING:
    from .solver import Inventory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TargetContext:
    """
    What a strategy needs to know about the target to judge a tool.

    The client passes the defender's area and space id down into
    ``pickToolByStrategy``; both defaults here are permissive, matching a tool
    that names no restriction.
    """

    area_type: int | None = None
    space_id: int | None = None
    is_player: bool = True


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
        target: TargetContext | None = None,
        used_per_type: Mapping[str, int] | None = None,
    ) -> tuple[ToolStats, int] | None: ...


# Effect types a tool can carry that weaken a defender directly, rather than
# through one of its own columns.
MELEE_DEFENCE_MALUS_TYPE = 215
RANGE_DEFENCE_MALUS_TYPE = 217


def conditioned_effect_bonus(
    game_data: GameData,
    tool: ToolStats,
    effect_type: int,
    area_type: int | None = None,
) -> float:
    """
    A tool's contribution from its effects rather than its columns.

    ``AReduceDefenseBonusStrategy.getConditionedEffectBonus``: sum a hundredth
    of each matching effect's strength, keeping only effects that apply to the
    target's area. Six tools today carry a defense malus this way and no column
    at all, so without this they look useless to the strategies.
    """
    total = 0.0
    for bonus in parse_effect_spec(tool.effects if isinstance(tool.effects, str) else ""):
        effect = game_data.effects.get(bonus.effect_id)
        if effect is None or effect.effect_type_id != effect_type:
            continue
        if not effect.applies_to_area(area_type):
            continue
        total += 0.01 * bonus.strength(effect.effect_type_id)
    return total


@dataclass
class ReduceDefenceBonusStrategy:
    """
    Picks the tool that best cancels one of the defender's bonuses.

    Ported from ``AReduceDefenseBonusStrategy.pickToolByStrategy``. Given how
    much of a defense remains after the attacker's own reduction, it prefers the
    tool that cancels it outright with the *fewest* units; failing that, the one
    that removes the most in the units that fit. A defense already at or below
    zero needs no tool, and the strategy retires.

    The client builds five of these, one per defender bonus; see
    :func:`default_tool_strategies`.
    """

    name: str
    tool_bonus: Callable[[ToolStats], float]
    defender_bonus: Callable[[AttackerFlankEffects, DefenderFlankEffects], float]
    requires: Callable[[DefenderFlankEffects], bool] | None = None
    malus_effect_type: int | None = None

    def __call__(
        self,
        inventory: "Inventory",
        game_data: GameData,
        *,
        free_items: int,
        attacker: AttackerFlankEffects,
        defender: DefenderFlankEffects | None,
        target: TargetContext | None = None,
        used_per_type: Mapping[str, int] | None = None,
    ) -> tuple[ToolStats, int] | None:
        target = target or TargetContext()
        used_per_type = used_per_type or {}
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

        # The client walks its inventory in insertion order and gives a tie to
        # whichever tool it meets first; that order is not reproducible here, so
        # settle it by wod id.
        for wod_id, available in sorted(inventory.counts.items()):
            tool = game_data.get_tool(wod_id)
            if tool is None or not tool.is_attack_tool or available <= 0:
                continue
            if not can_use_tool_on_target(tool, target):
                continue
            bonus = self.tool_bonus(tool)
            if self.malus_effect_type is not None:
                bonus += conditioned_effect_bonus(game_data, tool, self.malus_effect_type, target.area_type)
            if bonus <= 0:
                continue
            needed = math.ceil(remaining / bonus)
            limit = _per_wave_allowance(tool, used_per_type, free_items)
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


def _per_wave_allowance(tool: ToolStats, used_per_type: Mapping[str, int], free_items: int) -> int:
    """
    How many more of this tool the wave may take.

    The budget is keyed by the ITEMS ``type`` string, so every upgrade level of
    one tool shares it, and it spans all three flanks of the wave.

    A tool with no per-wave column is bounded only by the flank's free capacity.
    """
    limit = tool.per_wave_limit
    if limit > 0:
        return limit - used_per_type.get(tool.tool_type, 0)
    return free_items


def can_use_tool_on_target(tool: ToolStats, target: TargetContext) -> bool:
    """
    Whether this tool may be carried against this target at all.

    ``AttackHelper.canUseToolForAttackOnTarget``: a tool flagged
    ``canBeUsedToAttackNPC="0"`` is only allowed against another player, and
    ``allowedToAttack`` restricts a tool to named kingdoms and area types. Both
    default to permissive, so a tool that says nothing is usable everywhere.

    The client's third branch, an event tool with no inventory left, cannot be
    reached from the fill path - it needs an amount of zero, which the pick
    already skips.

    Args:
        tool: The tool being considered
        target: Where the attack is going

    Returns:
        True when the tool may be used
    """
    if not (tool.can_attack_npc or target.is_player):
        return False
    return tool.is_allowed_by_attack_target(target.space_id, target.area_type)


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
            malus_effect_type=RANGE_DEFENCE_MALUS_TYPE,
        ),
        ReduceDefenceBonusStrategy(
            "melee",
            lambda tool: tool.def_melee_bonus,
            lambda a, d: d.melee_bonus - a.defender_melee_reduction,
            requires=lambda d: d.has_melee_defenders,
            malus_effect_type=MELEE_DEFENCE_MALUS_TYPE,
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
    target: TargetContext | None = None,
    used_per_type: dict[str, int] | None = None,
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
        target: Where the attack is going, which scopes a tool's effects and
            decides whether it may be carried at all
        used_per_type: The wave's per-tool-type budget so far, shared across its
            three flanks and updated in place

    Returns:
        ``(wod_id, count)`` per filled slot

    Note:
        One deliberate divergence. The client deducts a stack inside the pick,
        before it knows whether the tool fits the slot, and drops it on the floor
        when it does not - the tools are gone from the inventory and never
        placed. This deducts only what it places. The loss is reachable on a side
        flank through the range strategy, so a wave built here can carry tools a
        wave built in the client would have lost.

        The attacker effects passed in are not mutated; the updated copy is used
        internally for later picks. Callers that need the post-tool effects for
        soldier filling should rebuild them, or accept that the client's own
        soldier pass sees them.
    """
    effects = attacker or AttackerFlankEffects()
    area_type = (target or TargetContext()).area_type
    if used_per_type is None:
        used_per_type = {}
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
                attacker=effects,
                defender=defender,
                target=target,
                used_per_type=used_per_type,
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
        used_per_type[tool.tool_type] = used_per_type.get(tool.tool_type, 0) + taken
        free -= taken
        # Each placed tool dents the defense the next pick is measured against,
        # including any malus it carries as an effect rather than a column -
        # without that term the loop could re-pick the same tool forever.
        effects = effects.apply_tool(
            tool,
            taken,
            range_malus=conditioned_effect_bonus(game_data, tool, RANGE_DEFENCE_MALUS_TYPE, area_type),
            melee_malus=conditioned_effect_bonus(game_data, tool, MELEE_DEFENCE_MALUS_TYPE, area_type),
        )

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
    "MELEE_DEFENCE_MALUS_TYPE",
    "RANGE_DEFENCE_MALUS_TYPE",
    "ReduceDefenceBonusStrategy",
    "can_use_tool_on_target",
    "TargetContext",
    "conditioned_effect_bonus",
    "ToolStrategy",
    "check_flank",
    "default_tool_strategies",
    "fill_flank_with_tools",
]
