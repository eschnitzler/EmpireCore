"""
The soldier half of the client's wave auto-fill.

Ported from ``AFillFlankStrategy.fillFlankWithSoldiers`` and
``StrongestDefenceCounterRatioConsideredFlankStrategy.pickSoldierStack``: pick
the unit whose stack best counters whichever of the defender's melee or ranged
defense is the weaker share, place it, repeat until the flank is full.

Tools are not placed yet, so a wave built here carries units only.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from empire_core.gamedata import GameData
from empire_core.protocol.models import AttackWave, WaveFlank

from .capacity import YARD_SLOTS, WaveCapacity, max_wave_count
from .effects import AttackerFlankEffects, DefenderFlankEffects, Flank
from .tools import TargetContext, check_flank, default_tool_strategies, fill_flank_with_tools

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
    unit_attack_bonuses: Mapping[int, float] | None = None,
) -> tuple[int, int] | None:
    """
    Choose one stack for a flank slot and take it out of the inventory.

    The choice weighs the best melee stack against the best ranged stack by the
    defender's opposite defense share, so the attack lands where the defense is
    thinner. With no defender information both shares are 1.0 and the stronger
    stack simply wins.

    Args:
        free_items: Remaining troop capacity of the flank
        inventory: Pool to draw from; the chosen stack is deducted
        game_data: Loaded unit stats
        attacker: Attacker multipliers (unbuffed when omitted)
        defender: The defender's strength on this flank, if known
        options: Unit filters
        unit_attack_bonuses: Per-unit attack bonuses from active global
            effects, from ``global_unit_attack_bonuses``

    Returns:
        ``(wod_id, count)`` placed, or None when nothing is eligible
    """
    attacker = attacker or AttackerFlankEffects()
    options = options or FillOptions()

    if free_items <= 0:
        return None

    melee_defense = defender.melee_defense_value(0.0, attacker.defender_range_reduction) if defender else 0.0
    range_defense = defender.range_defense_value(attacker.defender_range_reduction, 0.0) if defender else 0.0
    total = melee_defense + range_defense
    melee_share = melee_defense / total if total > 0 else 1.0
    range_share = range_defense / total if total > 0 else 1.0

    best_melee = best_ranged = 0
    best_melee_id = best_ranged_id = 0

    # Scanned in wod-id order: the comparisons are strict, so a tie goes to
    # whichever unit comes first, and the client's own inventory order is not
    # reproducible here.
    for wod_id, available in sorted(inventory.counts.items()):
        unit = game_data.get_unit(wod_id)
        if unit is None or not _is_eligible(unit, options):
            continue
        value = attacker.soldier_stack_attack_value(
            unit, free_items, available, (unit_attack_bonuses or {}).get(wod_id, 0.0)
        )
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
        # Counter the defense that is proportionally weaker.
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
    unit_attack_bonuses: Mapping[int, float] | None = None,
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
        unit_attack_bonuses: Per-unit attack buffs from active global effects

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
            unit_attack_bonuses=unit_attack_bonuses,
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
    defense: Mapping[Flank, DefenderFlankEffects] | None = None,
    options: FillOptions | None = None,
    unit_attack_bonuses: Mapping[int, float] | None = None,
    strategies: Sequence | None = None,
    area_type: int | None = None,
    space_id: int | None = None,
    target_is_player: bool = True,
) -> AttackWave:
    """
    Build one wave, flank by flank.

    Follows the client's order: each flank takes tools first, then soldiers,
    then ``check_flank`` returns the tools if no unit ended up on that flank.
    Tools come first because a placed tool changes the defense the soldiers are
    then picked against.

    Args:
        inventory: Pool to draw from; placed stacks are deducted
        game_data: Loaded unit and tool stats
        capacity: The wave's size, from :meth:`WaveCapacity.for_level`
        attacker: Attacker multipliers
        defense: Defender strength per flank, if known
        options: Which flanks to fill and which units to allow
        unit_attack_bonuses: Per-unit attack buffs from active global effects
        strategies: The tool strategy pool; the client's five when omitted.
            Pass an empty list for a unit-only wave.
        area_type: The target's area type, which scopes a tool's effects
        space_id: The kingdom the target sits in, which some tools are limited to
        target_is_player: Whether the target belongs to another player

    Returns:
        An :class:`AttackWave` ready for ``send_attack``
    """
    options = options or FillOptions()
    # The client fills left, then right, then middle. The order is visible in
    # the output because the flanks share one inventory and one per-wave tool
    # budget.
    wanted = {
        Flank.LEFT: options.fill_left,
        Flank.RIGHT: options.fill_right,
        Flank.MIDDLE: options.fill_middle,
    }

    units: dict[Flank, list[list[int]]] = {}
    tools: dict[Flank, list[list[int]]] = {}
    # One per-tool-type budget for the whole wave, as getSumOfToolsByTool reads
    # all three containers.
    used_per_type: dict[str, int] = {}
    for flank, should_fill in wanted.items():
        units[flank] = []
        tools[flank] = []
        if not should_fill:
            continue

        defender = (defense or {}).get(flank)
        # A fresh pool per flank: a strategy that retires on one flank is
        # available again on the next.
        pool = default_tool_strategies() if strategies is None else list(strategies)
        tools_placed = fill_flank_with_tools(
            capacity.tool_capacity(flank),
            capacity.tool_slots(flank),
            capacity.tool_slot_type(flank),
            inventory,
            game_data,
            pool,
            attacker=attacker,
            defender=defender,
            target=TargetContext(area_type, space_id, target_is_player),
            used_per_type=used_per_type,
        )
        placed_tools = tools_placed.placed
        placed_units = fill_flank_with_soldiers(
            capacity.soldier_capacity(flank),
            capacity.unit_slots(flank),
            inventory,
            game_data,
            # The tools just placed have dented this flank's defense, and the
            # client scores its soldiers against the dented values.
            attacker=tools_placed.effects,
            defender=defender,
            options=options,
            unit_attack_bonuses=unit_attack_bonuses,
        )
        check_flank(placed_tools, placed_units, inventory, game_data=game_data, used_per_type=used_per_type)

        units[flank] = [[wod_id, count] for wod_id, count in placed_units]
        tools[flank] = [[wod_id, count] for wod_id, count in placed_tools]

    return AttackWave(
        L=WaveFlank(U=units[Flank.LEFT], T=tools[Flank.LEFT]),
        M=WaveFlank(U=units[Flank.MIDDLE], T=tools[Flank.MIDDLE]),
        R=WaveFlank(U=units[Flank.RIGHT], T=tools[Flank.RIGHT]),
    )


def fill_yard_wave(
    inventory: Inventory,
    game_data: GameData,
    capacity: int,
    *,
    slots: int = YARD_SLOTS,
    defender: DefenderFlankEffects | None = None,
    options: FillOptions | None = None,
    unit_attack_bonuses: Mapping[int, float] | None = None,
) -> list[list[int]]:
    """
    Fill the courtyard wave, which goes out in ``cra``'s RW field.

    ``AFillWaveStrategy.fillYardContainer`` fills it with soldiers only - no
    tools - and passes no attacker effects, so units are scored on their raw
    values against the yard's own defenders.

    Args:
        inventory: Pool to draw from
        game_data: Loaded unit stats
        capacity: The yard's capacity, from :func:`yard_capacity`
        slots: How many unit slots the yard offers; all eight are open from
            level 0
        defender: The yard's defenders, if known
        options: Unit filters
        unit_attack_bonuses: Per-unit attack buffs from active global effects

    Returns:
        One ``[wod_id, count]`` pair per slot, in slot order, for the RW field.
        The client sends every slot, so an empty one goes out as ``[-1, 0]``.
    """
    stacks = fill_flank_with_soldiers(
        capacity,
        slots,
        inventory,
        game_data,
        attacker=None,
        defender=defender,
        options=options,
        unit_attack_bonuses=unit_attack_bonuses,
    )
    filled = [[wod_id, count] for wod_id, count in stacks]
    return filled + [[-1, 0]] * (slots - len(filled))


def fill_waves(
    inventory: Inventory,
    game_data: GameData,
    *,
    level: int,
    attacker_level: int | None = None,
    conquer: bool = False,
    wave_bonus: int = 0,
    flank_bonus_percent: float = 0.0,
    front_bonus_percent: float = 0.0,
    tool_bonus: float = 0.0,
    attacker: AttackerFlankEffects | None = None,
    defense: Mapping[Flank, DefenderFlankEffects] | None = None,
    options: FillOptions | None = None,
    unit_attack_bonuses: Mapping[int, float] | None = None,
    area_type: int | None = None,
    space_id: int | None = None,
    target_is_player: bool = True,
) -> list[AttackWave]:
    """
    Fill every wave the attack may carry, front to back.

    Sizes itself the way the client does: each flank's capacity and slots follow
    the level of whoever owns the target, while the number of waves follows the
    attacker's own level. Waves that come out empty are dropped, so the result is ready
    for ``send_attack``.

    Args:
        inventory: Pool to draw from; shared across every wave
        game_data: Loaded unit stats
        level: The target owner's level, which sizes each flank
        attacker_level: The attacker's own level, which decides how many waves
            an attack carries; defaults to the target's level
        conquer: A conquest attack carries extra waves
        wave_bonus: Extra waves from the ADDITIONAL_WAVE legend skill
        flank_bonus_percent: Percentage bonus to units on each side flank
        front_bonus_percent: Percentage bonus to units in the middle
        tool_bonus: Extra flank tool capacity
        attacker: Attacker multipliers
        defense: Defender strength per flank, if known
        options: Which flanks to fill and which units to allow
        unit_attack_bonuses: Per-unit attack buffs from active global effects
        area_type: The target's area type, which scopes a tool's effects
        space_id: The kingdom the target sits in, which some tools are limited to
        target_is_player: Whether the target belongs to another player

    Returns:
        One :class:`AttackWave` per filled wave, in send order
    """
    capacity = WaveCapacity.for_level(
        level,
        flank_bonus_percent=flank_bonus_percent,
        front_bonus_percent=front_bonus_percent,
        tool_bonus=tool_bonus,
    )
    waves: list[AttackWave] = []
    wave_count = max_wave_count(
        attacker_level if attacker_level is not None else level,
        conquer=conquer,
        bonus=wave_bonus,
    )
    for _index in range(wave_count):
        wave = fill_wave(
            inventory,
            game_data,
            capacity,
            attacker=attacker,
            defense=defense,
            options=options,
            unit_attack_bonuses=unit_attack_bonuses,
            area_type=area_type,
            space_id=space_id,
            target_is_player=target_is_player,
        )
        if not wave.is_complete():
            break
        waves.append(wave)
    return waves


def wave_limit_violations(
    waves: Sequence[AttackWave],
    capacity: WaveCapacity,
    *,
    yard: Sequence[Sequence[int]] | None = None,
    yard_capacity: int | None = None,
) -> list[str]:
    """
    Which of an attack's containers hold more than they may.

    The client refuses to send at all when any wave's unit container or the
    courtyard is over capacity - ``exceedsUnitLimit()`` and ``exceedsLimit()``,
    both of which are ``freeItems < 0``. It shows a blocking dialog instead. A
    hand-built army can trip this; the solver cannot.

    Args:
        waves: The waves about to be sent
        capacity: The capacities those waves were sized against
        yard: The courtyard wave, if one is being sent
        yard_capacity: Its capacity, from :func:`yard_capacity`

    Returns:
        One readable line per overfull container, empty when the attack is legal
    """
    problems = []
    for index, wave in enumerate(waves):
        payload = wave.model_dump(by_alias=True)
        for name, flank in (("L", Flank.LEFT), ("M", Flank.MIDDLE), ("R", Flank.RIGHT)):
            units = sum(count for _wod_id, count in payload[name]["U"])
            allowed = capacity.soldier_capacity(flank)
            if units > allowed:
                problems.append(f"wave {index} {name}: {units} units, limit {allowed}")
            tools = sum(count for _wod_id, count in payload[name]["T"])
            allowed = capacity.tool_capacity(flank)
            if tools > allowed:
                problems.append(f"wave {index} {name}: {tools} tools, limit {allowed}")
    if yard is not None and yard_capacity is not None:
        placed = sum(pair[1] for pair in yard if len(pair) > 1 and pair[0] != -1)
        if placed > yard_capacity:
            problems.append(f"courtyard: {placed} units, limit {yard_capacity}")
    return problems


class FilledAttack(BaseModel):
    """
    A complete attack: its waves and its courtyard wave.

    ``waves`` goes in the ``A`` field of a ``cra`` and ``yard`` in ``RW``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    waves: list[AttackWave] = Field(default_factory=list)
    yard: list[list[int]] = Field(default_factory=list)

    def unit_count(self) -> int:
        """Units committed across every wave and the courtyard."""
        return sum(wave.unit_count() for wave in self.waves) + sum(count for _wod_id, count in self.yard)


__all__ = [
    "FillOptions",
    "FilledAttack",
    "Inventory",
    "fill_flank_with_soldiers",
    "fill_wave",
    "fill_waves",
    "fill_yard_wave",
    "pick_soldier_stack",
    "wave_limit_violations",
]
