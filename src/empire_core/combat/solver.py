"""
The soldier half of the client's wave auto-fill.

Ported from ``AFillFlankStrategy.fillFlankWithSoldiers`` and
``StrongestDefenceCounterRatioConsideredFlankStrategy.pickSoldierStack``: pick
the unit whose stack best counters whichever of the defender's melee or ranged
defence is the weaker share, place it, repeat until the flank is full.

Tools are not placed yet, so a wave built here carries units only.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping

from pydantic import BaseModel, ConfigDict

from empire_core.gamedata import GameData
from empire_core.protocol.models import AttackWave, WaveFlank

from .capacity import WaveCapacity, max_wave_count
from .effects import AttackerFlankEffects, DefenderFlankEffects, Flank

logger = logging.getLogger(__name__)


class FillOptions(BaseModel):
    """
    Which flanks to fill and which units may be used.

    Every filter defaults to allowed, matching the client's
    ``AutoFillOptions.createNewUnitFilter``. Turning one off excludes units that
    carry that cost: ``allow_c2_cost=False`` keeps units whose healing costs
    rubies out of the wave, for instance.
    """

    model_config = ConfigDict(extra="forbid")

    fill_left: bool = True
    fill_middle: bool = True
    fill_right: bool = True
    allow_c1_cost: bool = True
    allow_c2_cost: bool = True
    allow_mead: bool = True
    allow_beef: bool = True
    use_melee: bool = True
    use_ranged: bool = True


class Inventory:
    """
    A mutable pool of units to draw a wave from.

    The solver deducts what it places, so one inventory can fill several waves
    in sequence without double-spending a unit.
    """

    def __init__(self, stacks: Mapping[int, int] | Iterable[tuple[int, int]]) -> None:
        pairs = stacks.items() if isinstance(stacks, Mapping) else stacks
        self.counts: dict[int, int] = {wod_id: count for wod_id, count in pairs if count > 0}

    def available(self, wod_id: int) -> int:
        return self.counts.get(wod_id, 0)

    def soldier_count(self, game_data: GameData) -> int:
        """How many actual units are left, ignoring tools and boost items."""
        return sum(count for wod_id, count in self.counts.items() if game_data.is_unit(wod_id))

    def deduct(self, wod_id: int, limit: int) -> int:
        """
        Take up to ``limit`` of a unit out of the pool.

        Returns:
            How many were actually taken
        """
        taken = min(max(0, limit), self.counts.get(wod_id, 0))
        if taken:
            remaining = self.counts[wod_id] - taken
            if remaining:
                self.counts[wod_id] = remaining
            else:
                del self.counts[wod_id]
        return taken

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Inventory({len(self.counts)} kinds, {sum(self.counts.values())} units)"


def _is_eligible(unit, options: FillOptions) -> bool:
    """The client's per-unit filter chain."""
    if not (unit.is_offensive or unit.is_allround):
        return False
    if unit.healing_cost_c1 > 0 and not options.allow_c1_cost:
        return False
    if unit.healing_cost_c2 > 0 and not options.allow_c2_cost:
        return False
    if unit.mead_supply > 0 and not options.allow_mead:
        return False
    if unit.beef_supply > 0 and not options.allow_beef:
        return False
    return True


def pick_soldier_stack(
    free_items: int,
    inventory: Inventory,
    game_data: GameData,
    *,
    attacker: AttackerFlankEffects | None = None,
    defender: DefenderFlankEffects | None = None,
    options: FillOptions | None = None,
) -> tuple[int, int] | None:
    """
    Choose one stack for a flank slot and take it out of the inventory.

    The choice weighs the best melee stack against the best ranged stack by the
    defender's opposite defence share, so the attack lands where the defence is
    thinner. With no defender information both shares are 1.0 and the stronger
    stack simply wins.

    Args:
        free_items: Remaining troop capacity of the flank
        inventory: Pool to draw from; the chosen stack is deducted
        game_data: Loaded unit stats
        attacker: Attacker multipliers (unbuffed when omitted)
        defender: The defender's strength on this flank, if known
        options: Unit filters

    Returns:
        ``(wod_id, count)`` placed, or None when nothing is eligible
    """
    attacker = attacker or AttackerFlankEffects()
    options = options or FillOptions()

    if free_items <= 0:
        return None

    melee_defence = defender.melee_defence_value(0.0, attacker.defender_range_reduction) if defender else 0.0
    range_defence = defender.range_defence_value(attacker.defender_range_reduction, 0.0) if defender else 0.0
    total = melee_defence + range_defence
    melee_share = melee_defence / total if total > 0 else 1.0
    range_share = range_defence / total if total > 0 else 1.0

    best_melee = best_ranged = 0
    best_melee_id = best_ranged_id = 0

    for wod_id, available in inventory.counts.items():
        unit = game_data.get_unit(wod_id)
        if unit is None or not _is_eligible(unit, options):
            continue
        value = attacker.soldier_stack_attack_value(unit, free_items, available)
        if unit.is_melee and options.use_melee:
            if value > best_melee:
                best_melee, best_melee_id = value, wod_id
        elif unit.is_ranged and options.use_ranged:
            if value > best_ranged:
                best_ranged, best_ranged_id = value, wod_id

    if best_melee + best_ranged == 0:
        return None
    if best_melee == 0:
        chosen = best_ranged_id
    elif best_ranged == 0:
        chosen = best_melee_id
    else:
        # Counter the defence that is proportionally weaker.
        chosen = best_melee_id if best_melee * range_share >= best_ranged * melee_share else best_ranged_id

    taken = inventory.deduct(chosen, free_items)
    if not taken:
        return None
    return chosen, taken


def fill_flank_with_soldiers(
    capacity: int,
    slots: int,
    inventory: Inventory,
    game_data: GameData,
    *,
    attacker: AttackerFlankEffects | None = None,
    defender: DefenderFlankEffects | None = None,
    options: FillOptions | None = None,
) -> list[tuple[int, int]]:
    """
    Fill one flank's unit slots.

    Stops early when a slot cannot be filled, as the client does, so a partly
    filled flank is a normal result rather than an error.

    Args:
        capacity: The flank's troop capacity
        slots: How many unlocked unit slots the flank has
        inventory: Pool to draw from; placed stacks are deducted
        game_data: Loaded unit stats
        attacker: Attacker multipliers
        defender: The defender's strength on this flank, if known
        options: Unit filters

    Returns:
        ``(wod_id, count)`` per filled slot
    """
    placed: list[tuple[int, int]] = []
    free = capacity
    for _slot in range(max(0, slots)):
        if free <= 0 or inventory.soldier_count(game_data) <= 0:
            break
        stack = pick_soldier_stack(
            free,
            inventory,
            game_data,
            attacker=attacker,
            defender=defender,
            options=options,
        )
        if stack is None:
            break
        placed.append(stack)
        free -= stack[1]
    return placed


def fill_wave(
    inventory: Inventory,
    game_data: GameData,
    capacity: WaveCapacity,
    *,
    attacker: AttackerFlankEffects | None = None,
    defence: Mapping[Flank, DefenderFlankEffects] | None = None,
    options: FillOptions | None = None,
) -> AttackWave:
    """
    Build one wave's units, flank by flank.

    Tools are not placed: the returned wave's tool slots are empty, so it is a
    unit-only wave. Pass the defence from
    :func:`~empire_core.combat.defence.npc_camp_defence` (or build it from a spy
    report) to get counter-aware picks.

    Args:
        inventory: Pool to draw from; placed stacks are deducted
        game_data: Loaded unit stats
        capacity: The wave's size, from :meth:`WaveCapacity.for_level`
        attacker: Attacker multipliers
        defence: Defender strength per flank, if known
        options: Which flanks to fill and which units to allow

    Returns:
        An :class:`AttackWave` ready for ``send_attack``
    """
    options = options or FillOptions()
    wanted = {
        Flank.LEFT: options.fill_left,
        Flank.MIDDLE: options.fill_middle,
        Flank.RIGHT: options.fill_right,
    }

    filled: dict[Flank, list[list[int]]] = {}
    for flank, should_fill in wanted.items():
        if not should_fill:
            filled[flank] = []
            continue
        stacks = fill_flank_with_soldiers(
            capacity.soldier_capacity(flank),
            capacity.unit_slots(flank),
            inventory,
            game_data,
            attacker=attacker,
            defender=(defence or {}).get(flank),
            options=options,
        )
        filled[flank] = [[wod_id, count] for wod_id, count in stacks]

    return AttackWave(
        L=WaveFlank(U=filled[Flank.LEFT]),
        M=WaveFlank(U=filled[Flank.MIDDLE]),
        R=WaveFlank(U=filled[Flank.RIGHT]),
    )


def fill_waves(
    inventory: Inventory,
    game_data: GameData,
    *,
    level: int,
    conquer: bool = False,
    wave_bonus: int = 0,
    soldier_bonus_percent: float = 0.0,
    tool_bonus: float = 0.0,
    attacker: AttackerFlankEffects | None = None,
    defence: Mapping[Flank, DefenderFlankEffects] | None = None,
    options: FillOptions | None = None,
) -> list[AttackWave]:
    """
    Fill every wave the attack may carry, front to back.

    Sizes itself: how many waves, how many units each flank holds and how many
    slots are unlocked all follow from the effective level, the way the client
    derives them. Waves that come out empty are dropped, so the result is ready
    for ``send_attack``.

    Args:
        inventory: Pool to draw from; shared across every wave
        game_data: Loaded unit stats
        level: Effective level - the attacker's own, or the target's minimum
            defence level when that is higher
        conquer: A conquest attack carries extra waves
        wave_bonus: Extra waves from the ADDITIONAL_WAVE legend skill
        soldier_bonus_percent: Percentage bonus to units per flank
        tool_bonus: Extra flank tool capacity
        attacker: Attacker multipliers
        defence: Defender strength per flank, if known
        options: Which flanks to fill and which units to allow

    Returns:
        One :class:`AttackWave` per filled wave, in send order
    """
    capacity = WaveCapacity.for_level(
        level,
        soldier_bonus_percent=soldier_bonus_percent,
        tool_bonus=tool_bonus,
    )
    waves: list[AttackWave] = []
    for _index in range(max_wave_count(level, conquer=conquer, bonus=wave_bonus)):
        wave = fill_wave(
            inventory,
            game_data,
            capacity,
            attacker=attacker,
            defence=defence,
            options=options,
        )
        if not wave.is_complete():
            break
        waves.append(wave)
    return waves


__all__ = [
    "FillOptions",
    "Inventory",
    "fill_flank_with_soldiers",
    "fill_wave",
    "fill_waves",
    "pick_soldier_stack",
]
