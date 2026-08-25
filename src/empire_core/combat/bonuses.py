"""
Resolving a commander's bonuses into the multipliers combat uses.

A bonus on an item names an *effect*; the effect names an *effect type*, which
is what a formula reads, and a *cap*, which is what it stacks within. This
module does that resolution and the client's two-stage capping, so the combat
maths can ask for "the melee attack multiplier" and get a number.

See ``docs/design/combat_effects.md`` for the full catalogue.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Sequence
from enum import IntEnum

from pydantic import BaseModel, ConfigDict

from empire_core.gamedata import EffectDef, GameData
from empire_core.protocol.models import Commander

logger = logging.getLogger(__name__)


class CombatEffectType(IntEnum):
    """
    Effect type ids the attack path reads.

    Verified against both the client's ``EffectTypeEnum`` and the items
    ``effecttypes`` table.
    """

    MELEE_BONUS = 9
    RANGE_BONUS = 10
    WALL_REDUCTION = 19
    GATE_REDUCTION = 20
    MOAT_REDUCTION = 21
    OFFENSIVE_MELEE_BONUS = 23
    OFFENSIVE_RANGE_BONUS = 24
    ATTACK_UNIT_AMOUNT_FLANK = 28
    ATTACK_UNIT_AMOUNT_FRONT = 34
    ATTACK_BONUS = 36


class Bonus(BaseModel):
    """
    One granted bonus: an id, its strength, and which id space the id is in.

    A relic item's bonus ids index the relic effect table rather than the plain
    effect table. The two overlap and disagree - id 4 is an economy effect in
    one and a gate reduction in the other - so the space has to travel with the
    bonus.
    """

    model_config = ConfigDict(extra="forbid")

    effect_id: int
    value: float
    via_relic: bool = False


def _first_number(candidate: object) -> float | None:
    if isinstance(candidate, bool):
        return None
    if isinstance(candidate, (int, float)):
        return float(candidate)
    if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
        for item in candidate:
            number = _first_number(item)
            if number is not None:
                return number
    return None


def parse_bonus_entries(entries: Iterable, *, via_relic: bool = False) -> list[Bonus]:
    """
    Parse the bonus encodings the server uses.

    Three shapes occur and all are handled: ``[effect_id, value]``,
    ``[effect_id, [value], source_tag]`` as sent for a commander's own effects,
    and ``[effect_id, strength_id, [value]]`` as sent inside an equipment entry.
    The effect id is always first; the strength is the first number found after
    it, preferring a nested list, which is where the real value sits when one is
    present.

    Unparseable entries are skipped rather than failing the batch.

    Args:
        entries: Raw bonus entries
        via_relic: The ids index the relic effect table, as they do for the
            bonuses inside a relic equipment item
    """
    bonuses: list[Bonus] = []
    skipped = 0
    for entry in entries or []:
        if not isinstance(entry, Sequence) or isinstance(entry, (str, bytes)) or len(entry) < 2:
            skipped += 1
            continue
        effect_id = _first_number(entry[0])
        if effect_id is None:
            skipped += 1
            continue
        nested = next(
            (
                _first_number(part)
                for part in entry[1:]
                if isinstance(part, Sequence) and not isinstance(part, (str, bytes))
            ),
            None,
        )
        value = nested if nested is not None else _first_number(entry[1])
        if value is None:
            skipped += 1
            continue
        bonuses.append(Bonus(effect_id=int(effect_id), value=value, via_relic=via_relic))
    if skipped:
        logger.debug(f"Skipped {skipped} unparseable bonus entries")
    return bonuses


class EffectResolver:
    """
    Turns bonuses into combat multipliers using the game data tables.

    Capping follows the client: bonuses are grouped by their effect's cap, each
    group is summed up to that cap's ceiling, and the capped group totals are
    then added together with no further ceiling. So a cap limits what stacks
    *within* it, never the effect type as a whole.
    """

    def __init__(self, game_data: GameData) -> None:
        self.game_data = game_data

    def accumulate(
        self,
        bonuses: Iterable[Bonus],
        effect_type: int,
        *,
        area_type: int | None = None,
        player_target: bool | None = None,
        space_id: int | None = None,
        relation: str | None = None,
        raid_boss_id: int | None = None,
        include_economy: bool = False,
        ignore_cap: bool = False,
    ) -> float:
        """
        Total strength of one effect type across the given bonuses.

        Args:
            bonuses: The bonuses a commander (or other source) grants
            effect_type: Which effect type to total, see :class:`CombatEffectType`
            area_type: The target's area type; effects scoped to other areas are
                dropped, and None keeps all of them
            player_target: True for a fight against a player, False for an NPC;
                None keeps effects flagged for either
            space_id: The castle space, for effects limited to one
            relation: Relationship to the target - ``sameAlliance``,
                ``allianceInWar`` or ``samePlayer``
            raid_boss_id: The raid boss being fought, for boss-scoped effects
            include_economy: Keep economy effects, which combat normally drops
            ignore_cap: Skip capping entirely

        Returns:
            The summed strength, 0.0 when nothing applies
        """
        buckets: dict[int | None, float] = {}
        for bonus in bonuses:
            effect = self.effect_for(bonus)
            if effect is None or effect.effect_type_id != effect_type:
                continue
            if not effect.applies_to_area(area_type):
                continue
            if not effect.applies_to_fight(player_target=player_target):
                continue
            if not effect.applies_to_space(space_id):
                continue
            if not effect.applies_to_relation(relation):
                continue
            if not effect.applies_to_raid_boss(raid_boss_id):
                continue
            if not include_economy:
                effect_type_def = self.game_data.effect_types.get(effect.effect_type_id)
                if effect_type_def is not None and effect_type_def.is_economy:
                    continue
            running = buckets.get(effect.cap_id, 0.0) + bonus.value
            ceiling = math.inf if ignore_cap else self._ceiling(effect.cap_id)
            buckets[effect.cap_id] = min(running, ceiling)
        return sum(buckets.values())

    def effect_for(self, bonus: Bonus) -> EffectDef | None:
        """The effect a bonus grants, resolved in the bonus's own id space."""
        if bonus.via_relic:
            return self.game_data.resolve_relic_effect(bonus.effect_id)
        return self.game_data.effects.get(bonus.effect_id)

    def _ceiling(self, cap_id: int | None) -> float:
        """A cap's ceiling; unknown or uncapped groups have none."""
        if cap_id is None:
            return math.inf
        cap = self.game_data.effect_caps.get(cap_id)
        if cap is None or cap.is_uncapped or cap.max_total_bonus is None:
            return math.inf
        return cap.max_total_bonus

    # ------------------------------------------------------------------
    # The quantities the attack path asks for
    # ------------------------------------------------------------------

    def attack_multiplier(
        self,
        bonuses: Iterable[Bonus],
        *,
        melee: bool,
        area_type: int | None = None,
        player_target: bool | None = None,
    ) -> float:
        """
        The attacker's melee or ranged multiplier for a flank.

        Mirrors ``getFullAttackBonusForLordByFlankAndAreaType``: the general
        attack bonus plus the matching side's plain and offensive bonuses, as a
        percentage, on top of a base of 1.0.
        """
        bonuses = list(bonuses)
        side = CombatEffectType.MELEE_BONUS if melee else CombatEffectType.RANGE_BONUS
        offensive = CombatEffectType.OFFENSIVE_MELEE_BONUS if melee else CombatEffectType.OFFENSIVE_RANGE_BONUS
        total = sum(
            self.accumulate(bonuses, effect_type, area_type=area_type, player_target=player_target)
            for effect_type in (CombatEffectType.ATTACK_BONUS, side, offensive)
        )
        return 1.0 + total / 100

    def flank_unit_bonus(
        self,
        bonuses: Iterable[Bonus],
        *,
        area_type: int | None = None,
        player_target: bool | None = None,
    ) -> float:
        """Percentage bonus to units on a side flank."""
        return self.accumulate(
            bonuses,
            CombatEffectType.ATTACK_UNIT_AMOUNT_FLANK,
            area_type=area_type,
            player_target=player_target,
        )

    def front_unit_bonus(
        self,
        bonuses: Iterable[Bonus],
        *,
        area_type: int | None = None,
        player_target: bool | None = None,
    ) -> float:
        """Percentage bonus to units in the middle."""
        return self.accumulate(
            bonuses,
            CombatEffectType.ATTACK_UNIT_AMOUNT_FRONT,
            area_type=area_type,
            player_target=player_target,
        )

    def fortification_reductions(
        self,
        bonuses: Iterable[Bonus],
        *,
        area_type: int | None = None,
        player_target: bool | None = None,
    ) -> tuple[float, float, float]:
        """
        Wall, gate and moat reductions as fractions.

        The client divides each by 100 before subtracting them from the
        defender's matching bonus.
        """
        bonuses = list(bonuses)
        return tuple(  # type: ignore[return-value]
            self.accumulate(bonuses, effect_type, area_type=area_type, player_target=player_target) / 100
            for effect_type in (
                CombatEffectType.WALL_REDUCTION,
                CombatEffectType.GATE_REDUCTION,
                CombatEffectType.MOAT_REDUCTION,
            )
        )


# Index 11 of an EQ entry is the equipment type; 3 means the item is a relic,
# so its bonus ids belong to the relic effect table.
_EQUIPMENT_TYPE_FIELD = 11
_EQUIPMENT_TYPE_RELIC = 3
_EQUIPMENT_BONI_FIELD = 5


def commander_bonuses(commander: Commander) -> list[Bonus]:
    """
    Every bonus a commander grants, resolved into the right id space.

    Three sources from the ``gli`` payload: the commander's own effects (``E``),
    its area effects (``AE``), and the bonus list inside each equipped item.
    A relic item's bonuses are tagged so they resolve through the relic effect
    table.

    Equipment set bonuses are not included - those are computed from the items
    tables rather than sent in the payload - so a commander wearing a full set
    resolves low.
    """
    bonuses: list[Bonus] = []
    for source in (commander.effects, commander.area_effects):
        bonuses.extend(parse_bonus_entries(entry for entry in source if isinstance(entry, list)))

    for item in commander.raw_equipment:
        if not isinstance(item, Sequence) or isinstance(item, (str, bytes)):
            continue
        if len(item) <= _EQUIPMENT_BONI_FIELD:
            continue
        boni = item[_EQUIPMENT_BONI_FIELD]
        if not isinstance(boni, list):
            continue
        is_relic = len(item) > _EQUIPMENT_TYPE_FIELD and item[_EQUIPMENT_TYPE_FIELD] == _EQUIPMENT_TYPE_RELIC
        bonuses.extend(parse_bonus_entries(boni, via_relic=is_relic))
    return bonuses


__all__ = [
    "Bonus",
    "CombatEffectType",
    "EffectResolver",
    "commander_bonuses",
    "parse_bonus_entries",
]
