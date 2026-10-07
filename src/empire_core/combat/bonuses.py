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
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from empire_core.commanders.models.equipment import Equipment
from empire_core.commanders.models.roster import Commander, CommanderEffect
from empire_core.enums import CombatEffectType
from empire_core.gamedata import EffectDef, EffectValue, EquipmentEffectValue, GameData, GlobalEffectDef, ToolStats

if TYPE_CHECKING:
    from empire_core.gamedata import GlobalEffect

    from .effects import AttackerFlankEffects

logger = logging.getLogger(__name__)


# Effect types whose value is a wod-id-keyed map rather than a single number.
# Their wire form is a flat ``[wod_id, value, wod_id, value, ...]`` array and
# their strength is the value of the first key, never the key itself.
#
#   EffectValueMap                     148, 149, 150, 154, 188
#   EquippableEffectValueSupportUnits  47, 51       extends EffectValueMap
#   EffectValueWodID                   70, 71, 72, 1026
#   EffectValueUnitSpeedBoost          102          extends EffectValueWodID
#   EffectValueSpawnReserveUnit        208, 213     extends EffectValueWodID
#   EffectValueCurrencyBoost           168          extends EffectValueWodID
#   EffectValueMutateReserveUnit       214          extends EffectValueWodID
#
# Client: EffectTypeEnum registrations (bundle line 1322); the subclasses at
# bundle lines 62164, 62311, 62323 and 62369 leave ``strength`` alone.
#
# EffectValueIdList (57, 79, 90, 116, 169, 170, 178, 193) is deliberately
# absent: its strength getter returns ``idList[0]``, so its first number really
# is the value.
KEYED_EFFECT_TYPES = frozenset(
    {
        CombatEffectType.DEFENSE_SUPPORT_UNITS,
        CombatEffectType.ATTACK_SUPPORT_UNITS,
        CombatEffectType.RECRUITMENT_COST_DECREASE,
        CombatEffectType.RECRUITMENT_SPEED_BOOST,
        CombatEffectType.TOOL_PRODUCTION_SPEED_BOOST,
        CombatEffectType.UNIT_SPEED_BONUS,
        CombatEffectType.ATTACK_BONUS_UNIT,
        CombatEffectType.SPEED_BOOST_UNIT,
        CombatEffectType.LOOT_VALUE_BOOST_UNIT,
        CombatEffectType.FAME_BOOST_UNIT,
        CombatEffectType.CURRENCY_LOOT_BOOST,
        CombatEffectType.CRAFTING_QUEUE_PRODUCTION_BOOST,
        CombatEffectType.RESERVE_UNIT_KILL,
        CombatEffectType.SPAWN_RESERVE_UNIT,
        CombatEffectType.MUTATE_RESERVE_UNIT,
        CombatEffectType.ABILITY_PLUNDER,
    }
)


UNCAPPED_EQUIPMENT_CAP_ID = -1
"""``EquipmentBonusVO.capID`` of a bonus that overrides its cap (bundle line 20962)."""


class Bonus(BaseModel):
    """
    One granted bonus: an id, its strength, and which id space the id is in.

    A relic item's bonus ids index the relic effect table, and any other
    item's the equipment effect table, rather than the plain effect table. The
    tables overlap and disagree - id 4 is an economy effect in one and a gate
    reduction in another - so the space has to travel with the bonus.
    """

    model_config = ConfigDict(extra="forbid")

    effect_id: int
    value: float
    via_relic: bool = False
    via_equipment: bool = False
    """The id is an equipment effect id, as on an item that is not a relic."""
    raw_values: tuple[float, ...] = ()
    """The value array as sent, for the effect types that carry a keyed map."""

    def strength(self, effect_type_id: int | None) -> float:
        """
        What this bonus is worth for an effect of this type.

        A keyed effect's array is ``[wod_id, value, ...]``, so its first number
        is an id. ``EffectValueMap.strength`` returns the first *value* and
        ``EffectValueWodID.strength`` the value of the first key - the same
        number - so both read index 1.
        """
        if effect_type_id in KEYED_EFFECT_TYPES and len(self.raw_values) > 1:
            return self.raw_values[1]
        return self.value


def _numbers(candidate: object) -> list[float]:
    """Every number in a value array, flattened, in the order sent."""
    if isinstance(candidate, bool):
        return []
    if isinstance(candidate, (int, float)):
        return [float(candidate)]
    if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
        return [number for item in candidate for number in _numbers(item)]
    return []


def _first_number(candidate: object) -> float | None:
    """The first number in a value, however deeply it is nested."""
    return next(iter(_numbers(candidate)), None)


def parse_bonus_entries(entries: Iterable, *, via_relic: bool = False, via_equipment: bool = False) -> list[Bonus]:
    """
    Parse the bonus encodings the server uses.

    Three shapes occur and all are handled: ``[effect_id, value]`` or
    ``[effect_id, [value]]`` as on an item that is not a relic,
    ``[effect_id, [value], source_tag]`` as sent for a commander's own effects,
    and ``[relic_effect_id, power, [value]]`` as on a relic item. The id is
    always first; the strength is the first number found after it, preferring a
    nested list, which is where the value sits when one is present.

    Unparseable entries are skipped rather than failing the batch.

    Client: ``BasicEquipmentVO.parseBonuses`` (bundle line 7135),
    ``RelicBonusVO.parseRelicFromValueArray`` (bundle line 45132),
    ``LordVO.parseRawEffects`` (bundle line 26483).

    Args:
        entries: Raw bonus entries
        via_relic: The ids index the relic effect table, as they do for the
            bonuses inside a relic equipment item
        via_equipment: The ids index the equipment effect table, as they do
            for the bonuses inside any other equipment item
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
        array = next(
            (part for part in entry[1:] if isinstance(part, Sequence) and not isinstance(part, (str, bytes))),
            None,
        )
        raw_values = tuple(_numbers(array)) if array is not None else ()
        value = raw_values[0] if raw_values else _first_number(entry[1])
        if value is None:
            skipped += 1
            continue
        bonuses.append(
            Bonus(
                effect_id=int(effect_id),
                value=value,
                via_relic=via_relic,
                via_equipment=via_equipment,
                raw_values=raw_values,
            )
        )
    if skipped:
        logger.debug(f"Skipped {skipped} unparseable bonus entries")
    return bonuses


class EffectResolver:
    """
    Turns bonuses into combat multipliers using the game data tables.

    Capping follows the client: bonuses are grouped by their effect's cap, each
    group is summed up to that cap's ceiling, and the capped group totals are
    then added together with no further ceiling. So a cap limits what stacks
    *within* it, never the effect type as a whole. An equipment bonus whose
    equipment effect row sets ``ignoreCap`` goes into a group of its own with no
    ceiling.

    Client: ``CastleEffectsHelper.getTotalEffectValue`` (bundle line 4139),
    ``EquipmentBonusVO.capID`` and ``maxValueStrength`` (bundle line 20959).
    """

    def __init__(self, game_data: GameData) -> None:
        self.game_data = game_data

    def accumulate(
        self,
        bonuses: Iterable[Bonus],
        effect_type: CombatEffectType | int,
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
            overrides_cap = self.overrides_cap(bonus)
            cap_id = UNCAPPED_EQUIPMENT_CAP_ID if overrides_cap else effect.cap_id
            running = buckets.get(cap_id, 0.0) + bonus.strength(effect.effect_type_id)
            ceiling = math.inf if ignore_cap or overrides_cap else self._ceiling(cap_id)
            buckets[cap_id] = min(running, ceiling)
        return sum(buckets.values())

    def effect_for(self, bonus: Bonus) -> EffectDef | None:
        """
        The effect a bonus grants, resolved in the bonus's own id space.

        An equipment effect id names the effect in its row's ``effectID``; an id
        with no row is taken as a plain effect id.

        Client: ``EquipmentXml.getEquippableEffectByEquipmentEffect`` (bundle
        line 144136).
        """
        if bonus.via_relic:
            return self.game_data.resolve_relic_effect(bonus.effect_id)
        if bonus.via_equipment:
            row = self.game_data.equipment_effects.get(bonus.effect_id)
            return self.game_data.effects.get(row.effect_id if row is not None else bonus.effect_id)
        return self.game_data.effects.get(bonus.effect_id)

    def overrides_cap(self, bonus: Bonus) -> bool:
        """
        Whether an equipment bonus escapes its effect's cap.

        Client: ``EquipmentBonusVO.parseBasic`` (bundle line 20942) reads the
        equipment effect row's ``ignoreCap``.
        """
        if not bonus.via_equipment or bonus.via_relic:
            return False
        row = self.game_data.equipment_effects.get(bonus.effect_id)
        return row is not None and row.ignore_cap

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

    def yard_capacity_bonus(
        self,
        bonuses: Iterable[Bonus],
        *,
        area_type: int | None = None,
        player_target: bool | None = None,
    ) -> float:
        """Absolute unit bonus to the courtyard wave."""
        return self.accumulate(
            bonuses,
            CombatEffectType.ATTACK_UNIT_AMOUNT_REINFORCEMENT_BONUS,
            area_type=area_type,
            player_target=player_target,
        )

    def yard_capacity_boost(
        self,
        bonuses: Iterable[Bonus],
        *,
        area_type: int | None = None,
        player_target: bool | None = None,
    ) -> float:
        """Percentage boost to the courtyard wave, applied as a multiplier."""
        return self.accumulate(
            bonuses,
            CombatEffectType.ATTACK_UNIT_AMOUNT_REINFORCEMENT_BOOST,
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
        wall, gate, moat = (
            self.accumulate(bonuses, effect_type, area_type=area_type, player_target=player_target) / 100
            for effect_type in (
                CombatEffectType.WALL_REDUCTION,
                CombatEffectType.GATE_REDUCTION,
                CombatEffectType.MOAT_REDUCTION,
            )
        )
        return wall, gate, moat


def effect_value_bonuses(effects: Iterable[EffectValue | EquipmentEffectValue]) -> list[Bonus]:
    """
    The bonuses of an items row's ``effects``: one per entry with a value.

    A single number is the bonus's value. Anything else is a keyed value,
    ``wod_id+value`` pairs joined by ``#``, which the bonus keeps flattened as
    ``EffectValueMap.parseFromValueString`` reads it (bundle line 31617): a
    part without a ``+``, or whose value is no number, adds a 0; a part whose
    id is no number is left out. An equipment effect id is marked
    ``via_equipment``.
    """
    bonuses = []
    for entry in effects:
        pairs = [(first, _second(part)) for part in entry.values if part and (first := part[0]) is not None]
        if not pairs:
            continue
        via_equipment = isinstance(entry, EquipmentEffectValue)
        effect_id = entry.equipment_effect_id if isinstance(entry, EquipmentEffectValue) else entry.effect_id
        if len(entry.values) == 1 and len(entry.values[0]) == 1:
            bonuses.append(Bonus(effect_id=effect_id, value=pairs[0][0], via_equipment=via_equipment))
            continue
        flat = tuple(float(n) for pair in pairs for n in pair)
        bonuses.append(Bonus(effect_id=effect_id, value=flat[0], raw_values=flat, via_equipment=via_equipment))
    return bonuses


def _second(part: tuple[int | float | None, ...]) -> int | float:
    """The value of a ``wod_id+value`` part, 0 when it has none."""
    return part[1] if len(part) > 1 and part[1] is not None else 0


def _spec_bonuses(rows: Iterable) -> list[Bonus]:
    return [bonus for row in rows if row is not None for bonus in effect_value_bonuses(row.effects)]


def construction_item_bonuses(game_data: GameData, item_ids: Iterable[int]) -> list[Bonus]:
    """
    Bonuses from the construction items placed on a castle's buildings.

    These are the decorations players call look items, and they carry real
    combat bonuses - the flank unit limit item is where a +30% flank bonus
    comes from.
    """
    return _spec_bonuses(game_data.construction_items.get(item_id) for item_id in item_ids)


def alliance_buff_bonuses(game_data: GameData, buff_ids: Iterable[int]) -> list[Bonus]:
    """Bonuses from the alliance's researched buffs, at their current levels."""
    return _spec_bonuses(game_data.alliance_buffs.get(buff_id) for buff_id in buff_ids)


def global_effect_bonuses(game_data: GameData, global_effect_ids: Iterable[int]) -> list[Bonus]:
    """Bonuses from the global event effects currently running."""
    return _spec_bonuses(game_data.global_effects.get(effect_id) for effect_id in global_effect_ids)


def sceat_skill_bonuses(game_data: GameData, skill_ids: Iterable[int]) -> list[Bonus]:
    """Bonuses from unlocked sceat skills (the Hall of Legends trees)."""
    return _spec_bonuses(game_data.sceat_skills.get(skill_id) for skill_id in skill_ids)


def general_skill_bonuses(game_data: GameData, skill_ids: Iterable[int]) -> list[Bonus]:
    """Bonuses from the skills unlocked on the general leading the attack."""
    return _spec_bonuses(game_data.general_skills.get(skill_id) for skill_id in skill_ids)


def general_passive_bonuses(game_data: GameData, skill_ids: Iterable[int]) -> list[Bonus]:
    """
    The general's passive effects, which join its commander's bonuses.

    Client: ``GeneralVO.getPassiveEffects`` / ``getPassiveSkills`` (bundle line
    26781): the boni of every unlocked skill that is not an ability skill, one
    with an ``EFFECT_TYPE_UNLOCK_ABILITY`` effect (``GeneralSkillVO.isAbilitySkill``,
    bundle line 113404). Skill effects parse as ``effectID&value``
    (``GeneralSkillVO.parseXML``, bundle line 113364).
    """
    bonuses: list[Bonus] = []
    for skill_id in skill_ids:
        skill = game_data.general_skills.get(skill_id)
        if skill is None:
            continue
        boni = effect_value_bonuses(skill.effects)
        if any(
            (effect := game_data.effects.get(bonus.effect_id)) is not None
            and effect.effect_type_id == CombatEffectType.UNLOCK_ABILITY
            for bonus in boni
        ):
            continue
        bonuses.extend(boni)
    return bonuses


def legend_skill_value(game_data: GameData, skill_ids: Iterable[int], effect_type: str) -> float:
    """
    Total value of one legend skill effect type.

    Legend skills sit outside the effect and cap pipeline: they name an effect
    type directly and the client sums their values as plain numbers, so they are
    returned as a number rather than as bonuses.

    Args:
        game_data: Loaded tables
        skill_ids: The player's unlocked legend skill ids
        effect_type: The effect type name, e.g. ``gateReduction``

    Returns:
        The summed value, 0.0 when none match
    """
    return sum(
        skill.total_effect_value
        for skill_id in skill_ids
        if (skill := game_data.legend_skills.get(skill_id)) is not None and skill.effect_type == effect_type
    )


def global_unit_attack_bonuses(
    game_data: GameData,
    global_effects: Iterable[int | Sequence[int]],
    *,
    player_level: int | None = None,
    boosts: Mapping[GlobalEffect | int, float] | None = None,
) -> dict[int, float]:
    """
    Per-unit attack bonuses from the global effects currently running.

    This is the only thing that buffs a unit's attack value. The client reads it
    in ``SoldierUnitVO.buffedMeleeAttack`` as
    ``rawAttack + int(globalEffectData.getBonusByEffectType(ATTACK_BONUS_UNIT,
    -1, -1, wodId))``, and that getter looks only at the active global-effect
    event: a commander carrying the same effect type does **not** buff units
    through this path.

    The rows encode a per-unit map, ``273&<wod_id>+<strength>#<wod_id>+<strength>``.
    No condition is applied: the client resolves an unset area or kingdom to the
    castle the player happens to be looking at, and the one effect row this path
    can reach restricts neither, so there is nothing to check.
    The strengths in the table are only a fallback: each running effect is a
    ``[id, seconds_left, strength]`` row in the ``GE`` of the global effects
    event's ``sei`` entry (``Event.GLOBAL_EFFECT``), and ``setEffectStrength``
    writes a strength above -1 onto every unit in the map
    (``GlobalEffectEventVO.parseParamObject``, bundle lines 116399-116411). The
    state reads those rows into ``GlobalEffectEvent.effects``.

    A boosted effect - one ``bie`` lists - gets the booster event's boost on top
    (``GlobalEffectData.parse_GIE``, bundle lines 143676-143680):
    ``addBuffStrengthValue`` writes the effect's strength (its first unit's) plus
    the boost onto every unit of the map, as an int (``GlobalEffectVO``, bundle
    lines 143711-143718), and the effect's ``bonus`` is that buffed copy while
    ``bie`` lists it (bundle line 143712). Without a boost every unit keeps its
    own strength, where the client reads the first unit's for all
    (``EffectValueMap.strength``, bundle line 31649); live maps are uniform.

    Args:
        game_data: Loaded tables
        global_effects: Which global effects are active - either plain ids, or
            the ``GE`` rows of the ``Event.GLOBAL_EFFECT`` event, where a
            strength above -1 replaces the table's
        player_level: The attacker's level, which some effects are bracketed to;
            without it the brackets are ignored
        boosts: What the booster adds to each boosted effect: the effects
            ``bie`` lists, each with its ``GlobalEffectBuffEvent.boost_value``

    Returns:
        ``{wod_id: bonus}``, empty when no listed effect is active
    """
    bonuses: dict[int, float] = {}
    for entry in global_effects:
        if isinstance(entry, int):
            effect_id, override = entry, -1
        else:
            effect_id, override = int(entry[0]), int(entry[2]) if len(entry) > 2 else -1
        row = game_data.global_effects.get(effect_id)
        if row is None:
            continue
        if player_level is not None and not _within_level_bracket(row, player_level):
            continue
        for spec in row.effects:
            effect = game_data.effects.get(spec.effect_id)
            if effect is None or effect.effect_type_id != CombatEffectType.ATTACK_BONUS_UNIT:
                continue
            stacks = [
                (int(part[0]), override if override > -1 else _second(part))
                for part in spec.values
                if part and part[0] is not None
            ]
            if boosts and effect_id in boosts and stacks:
                buffed = math.trunc(stacks[0][1] + boosts[effect_id])
                stacks = [(wod_id, buffed) for wod_id, _ in stacks]
            for wod_id, strength in stacks:
                bonuses[wod_id] = bonuses.get(wod_id, 0.0) + strength
    return bonuses


def _within_level_bracket(row: GlobalEffectDef, level: int) -> bool:
    """``GlobalEffectVO.canBeUsed``. A ceiling of zero is an absent column, not a bar."""
    ceiling = int(row.max_level)
    return level >= int(row.min_level) and (ceiling <= 0 or level <= ceiling)


def commander_bonuses(
    game_data: GameData, commander: Commander, *, area_effects: Sequence[Bonus] | None = None
) -> list[Bonus]:
    """
    Every bonus a commander grants, resolved into the right id space.

    Five sources from the ``gli`` payload: the commander's own effects (``E``),
    its area effects (``AE``), the bonus list inside each equipped item, the
    gem slotted in each item (see :func:`gem_bonuses`), and the alien
    equipment of ``AIE``/``TAE`` when ``EQ`` is empty, whose rows the client
    builds as ``EquipmentBonusVO`` (``AlienLordEquipmentVO`` and
    ``AlienLordHeroVO.parseAlienBoniData``, bundle lines 67479 and 67502) in
    the commander's equipment slots. A relic item's
    bonuses are tagged so they resolve through the relic effect table, and any
    other item's so they resolve through the equipment effect table.

    The bonuses come in the client's order, equipment slots first and then
    ``E`` and ``AE``, which matters once a capped total mixes signs. The gems of
    alien equipment (``GEM``) count while ``AIE``/``TAE`` stand in for ``EQ``.

    The bonuses of the equipment sets worn (see :func:`equipment_set_bonuses`)
    come last, after ``AE``, as the client adds them.

    A default commander (``commander_id`` below 0, such as -14, the bought
    premium commander, or -15, a robber baron attack's) has no slots and no
    sets: its bonuses are its ``lords`` row's ``effects`` (see
    ``GameData.get_default_lord``), which name equipment effect ids, then
    ``E`` and ``AE``. Without a row the client builds no commander, so only
    ``area_effects`` count. Client: ``LordFactory.createLord`` (bundle lines
    26399-26401) returns ``CastleLordData.getDefaultLordByID`` for an id below
    0; ``DefaultLordVO.parseFromXml`` (bundle lines 101999-102002) reads the
    row and ``DefaultLordVO.getUniqueBoni`` (bundle lines 102005-102011) returns
    its effects, ``E`` and ``AE``, with ``getCountOfSetId`` always 0 (bundle
    line 102012).

    A movement's ``commander`` resolves the same way. The client builds it from
    the ``UM`` ``L`` block with ``LordFactory.createLord(e.L, true)``
    (``BasicMapmovementVO.parseUnitMovement``, bundle line 19385), the factory
    of the ``gli`` roster too, and shows its effects through the same
    ``LordVO.getUniqueBoni`` (``CastleArmyListDialog.updateLord``, bundle line
    95640, into ``LordEffectTooltip.createContent``, bundle line 65364) that the
    attack dialog reads a roster commander's from (``CastleEffectsHelper``,
    bundle line 4130). The movement tooltip leaves the general's passive
    effects out and the attack dialog adds them (see
    :func:`attack_dialog_bonuses`); a movement's commander carries its general's
    ``general_skill_ids`` for that. Legend and sceat skills belong to the
    attacking player, not the commander, and a movement does not carry them.

    A movement's commander comes with the area effects (``AE``) of the castle
    it was sent from, so it matches a roster commander resolved with that
    castle's ``aci`` ``AE`` as ``area_effects``, not its bare ``gli`` entry.

    Client: ``LordVO.getUniqueBoni`` (bundle line 26496). The attack dialog
    replaces the commander's area effects with the ``aci`` ``AE`` list
    (``AttackDialogController.updateAreEffects``, bundle line 4332), but the
    ``areaEffects`` setter ignores an empty list (bundle line 26652), so the
    commander keeps its own ``gli`` ``AE`` when ``aci`` sends none.

    Args:
        game_data: Loaded tables, for the gems and equipment sets
        commander: The commander's ``gli`` entry, or a movement's ``commander``
        area_effects: The ``aci`` ``AE`` list, from
            ``GetAttackInfoResponse.attacker_bonuses()``. When it has entries
            they are used instead of the commander's own ``AE``
    """
    if commander.commander_id < 0:
        default = game_data.get_default_lord(commander.commander_id)
        if default is None:
            return list(area_effects or [])
        return [
            *effect_value_bonuses(default.effects),
            *effect_bonuses(commander.effects),
            *(area_effects if area_effects else effect_bonuses(commander.area_effects)),
        ]

    bonuses: list[Bonus] = []
    for item in commander.worn_items():
        if item.is_relic:
            rows = [[bonus.relic_effect_id, bonus.power, bonus.values] for bonus in item.relic_bonuses]
        else:
            rows = [[bonus.effect_id, bonus.values] for bonus in item.bonuses]
        bonuses.extend(parse_bonus_entries(rows, via_relic=item.is_relic, via_equipment=not item.is_relic))
        bonuses.extend(gem_bonuses(game_data, item))

    alien_rows = [
        [bonus.effect_id, bonus.values] for bonus in (*commander.alien_hero_bonuses, *commander.alien_bonuses)
    ]
    bonuses.extend(parse_bonus_entries(alien_rows, via_equipment=True))
    if commander.uses_alien_equipment:
        # AlienLordEquipmentVO.parseGemBoniData (bundle line 67486) looks each GEM id up in the
        # int-keyed gem table as sent, so only a number finds a gem
        for gem_id in commander.alien_gem_ids:
            row = game_data.gems.get(gem_id) if isinstance(gem_id, int) and not isinstance(gem_id, bool) else None
            if row is not None:
                bonuses.extend(effect_value_bonuses(row.effects))

    bonuses.extend(effect_bonuses(commander.effects))
    bonuses.extend(area_effects if area_effects else effect_bonuses(commander.area_effects))
    bonuses.extend(equipment_set_bonuses(game_data, commander.worn_items()))
    return bonuses


def equipment_set_bonuses(game_data: GameData, items: Iterable[Equipment]) -> list[Bonus]:
    """
    The bonuses of the equipment sets the worn items and their gems complete.

    Each item whose ``set_id`` is not -1 counts once toward its set, and so does
    each distinct gem slotted in an item whose gem row names a ``set_id`` above
    0. A relic item's relic gem counts toward no set. Every threshold row of a
    set (``GameData.equipment_sets``) whose ``needed_items`` the count reaches
    grants its bonuses, which name equipment effect ids.

    Client: ``LordVO.setCounts`` (bundle line 26576) and ``LordVO.getUniqueBoni``
    (bundle lines 26510-26518). ``BasicEquipmentVO.hasSetbonus`` (bundle line
    7213) reads ``setID != -1``; ``RelicGemVO`` keeps ``BasicEquippableVO``'s
    ``setID`` of 0 (bundle line 4820). The alien equipment of ``AIE``/``TAE`` is
    left out: the client counts it under set 0, which no set row uses.

    Args:
        game_data: Loaded tables, for the gems and equipment sets
        items: The items worn, see ``Commander.worn_items``
    """
    counts: dict[int, int] = {}
    gems_counted: set[int] = set()
    for item in items:
        if item.has_set:
            counts[item.set_id] = counts.get(item.set_id, 0) + 1
        gem = game_data.gems.get(item.gem_id) if item.relic_info is None and item.has_gem else None
        if gem is not None and gem.set_id > 0 and gem.gem_id not in gems_counted:
            gems_counted.add(gem.gem_id)
            counts[gem.set_id] = counts.get(gem.set_id, 0) + 1
    return [
        bonus
        for set_id, count in counts.items()
        for row in game_data.equipment_sets.get(set_id, [])
        if row.needed_items <= count
        for bonus in effect_value_bonuses(row.effects)
    ]


def gem_bonuses(game_data: GameData, item: Equipment) -> list[Bonus]:
    """
    The bonuses of the gem slotted in an item.

    A gem id at index 10 other than -1 names a ``gems`` row, whose ``effects``
    are plain ``effectID&value`` bonuses; an id missing from the table grants
    nothing. A relic item that carries index 12 has its relic gem there
    instead, and that gem's bonuses resolve through the relic effect table.

    Client: ``BasicEquipmentVO.parseEquipFromArray`` (bundle line 7116),
    ``RelicEquipmentVO.parseEquipFromArray`` (bundle line 25039), which replaces
    the index 10 gem with the index 12 one, ``CastleGemVO.parseXML`` (bundle
    line 28287) and ``LordVO.getUniqueBoni`` (bundle line 26496).
    """
    if item.relic_info is not None:
        gem = item.relic_info.gem
        if gem is None:
            return []
        rows = [[bonus.relic_effect_id, bonus.power, bonus.values] for bonus in gem.bonuses]
        return parse_bonus_entries(rows, via_relic=True)
    if not item.has_gem:
        return []
    row = game_data.gems.get(item.gem_id)
    return effect_value_bonuses(row.effects) if row is not None else []


def effect_bonuses(effects: Iterable[CommanderEffect]) -> list[Bonus]:
    """The bonuses of a list of commander effects, such as a ``gli`` ``E`` or an ``aci`` ``AE``."""
    return parse_bonus_entries([effect.effect_id, effect.values] for effect in effects)


def attack_dialog_bonuses(
    game_data: GameData,
    commander: Commander | None,
    *,
    area_effects: Sequence[Bonus] | None = None,
    general_skill_ids: Iterable[int] | None = None,
) -> list[Bonus]:
    """
    The one bonus list the attack dialog reads its commander's effects from.

    Client: ``LordVO.getUniqueBoni`` with the assigned general included, as
    ``CastleEffectsHelper.getAccumulatedEquipmentBonusByEffectTypeForArea``
    calls it (bundle line 4136): the commander's equipment, effects and area
    effects (see :func:`commander_bonuses`) plus the general's passive effects.
    Sceat skills are not part of it.

    Args:
        game_data: Loaded tables
        commander: The commander leading the attack. Without one, only
            ``area_effects`` and the general's skills are counted
        area_effects: The ``aci`` ``AE`` list
        general_skill_ids: The unlocked skills of the commander's general

    Returns:
        Every bonus, unmerged; :meth:`EffectResolver.accumulate` caps them
    """
    if commander is not None:
        bonuses = commander_bonuses(game_data, commander, area_effects=area_effects)
    else:
        bonuses = list(area_effects or [])
    if general_skill_ids:
        bonuses.extend(general_passive_bonuses(game_data, general_skill_ids))
    return bonuses


def tool_effect_strength(game_data: GameData, tool: ToolStats, effect_type: CombatEffectType | int) -> float:
    """
    The summed strength of a tool's own effects of one type, with no condition.

    Client: ``ToolUnitVO.getEffectValue`` with ``NULL_CONDITION`` (bundle line
    6640), as ``getBonusByEffect`` reads it for a mapped tool effect type: area,
    space and wod id are all -1, so no effect is filtered out. The effects parse
    as ``effectID&value`` (``ToolUnitVO.parseEffects``, bundle line 6644).
    """
    total = 0.0
    for bonus in effect_value_bonuses(tool.effects):
        effect = game_data.effects.get(bonus.effect_id)
        if effect is not None and effect.effect_type_id == effect_type:
            total += bonus.strength(effect_type)
    return total


def attacker_flank_effects(
    resolver: "EffectResolver",
    bonuses: Iterable[Bonus],
    *,
    area_type: int | None = None,
    player_target: bool | None = None,
    legend_skill_ids: Iterable[int] = (),
    legendary: bool = False,
    support_tools: Sequence[ToolStats] = (),
) -> "AttackerFlankEffects":
    """
    Build a flank's attacker multipliers from resolved bonuses.

    Client: ``FightScreenHelper.getAttackerFlankEffectVO`` (bundle line 19179),
    in its order: the commander's reductions and multipliers, then the legend
    skills in a legendary fight, then each tool. The auto-fill starts from an
    empty wave, so the tools here are only the support tools, one of each
    ``AST`` entry. Tools the solver places later are added by
    ``AttackerFlankEffects.apply_tool``.

    Args:
        resolver: Resolver over the loaded game data
        bonuses: The commander's bonuses, see :func:`attack_dialog_bonuses`
        area_type: The target's area type, for scoping, such as a movement's
            ``target_type``; None or below 0 keeps every effect
        player_target: True when attacking a player. The client passes no
            filter strategy here, which keeps PvP and PvE effects alike; that
            is what None does
        legend_skill_ids: The player's unlocked legend skills
        legendary: ``AttackDialogHelper.isLegendaryFight``, i.e.
            ``LegendaryFight.unit_amount``. The legend skills count only then
        support_tools: The support tools picked for the attack

    Returns:
        The flank's attacker effects
    """
    from .effects import AttackerFlankEffects

    game_data = resolver.game_data
    bonuses = list(bonuses)
    wall, gate, moat = resolver.fortification_reductions(bonuses, area_type=area_type, player_target=player_target)
    melee = resolver.attack_multiplier(bonuses, melee=True, area_type=area_type, player_target=player_target)
    ranged = resolver.attack_multiplier(bonuses, melee=False, area_type=area_type, player_target=player_target)
    defender_range = 0.0
    if legendary:
        skills = list(legend_skill_ids)
        wall += legend_skill_value(game_data, skills, "wallReduction") / 100
        gate += legend_skill_value(game_data, skills, "gateReduction") / 100
        moat += legend_skill_value(game_data, skills, "moatReduction") / 100
        melee += legend_skill_value(game_data, skills, "attackMeleeBonus") / 100
        ranged += legend_skill_value(game_data, skills, "attackRangeBonus") / 100
    for tool in support_tools:
        wall += tool.wall_bonus
        gate += tool.gate_bonus
        moat += tool.moat_bonus
        defender_range += tool.def_range_bonus
        ranged += tool.off_range_bonus
        melee += tool.off_melee_bonus
        # ToolEffectType.ATTACK_BONUS is not absolute (bundle line 9629), so
        # getBonusByEffect scales it by 0.01.
        attack = 0.01 * tool_effect_strength(game_data, tool, CombatEffectType.ATTACK_BONUS)
        ranged += attack
        melee += attack
    return AttackerFlankEffects(
        melee_bonus=melee,
        range_bonus=ranged,
        defender_range_reduction=defender_range,
        wall_reduction=wall,
        gate_reduction=gate,
        moat_reduction=moat,
    )


def support_tool_waves(game_data: GameData, support_tools: Sequence[ToolStats]) -> float:
    """
    Extra waves the support tools grant.

    Client: ``CastleFightItemContainer.getTotalBonusByToolEffect(ADDITIONAL_WAVE)``
    (bundle line 20719)
    over the support container, one of each ``AST`` entry.
    ``ToolEffectType.ADDITIONAL_WAVE`` is absolute (bundle line 9615), so the
    effect's strength is taken as it is; it maps to effect type 156.
    """
    return sum(tool_effect_strength(game_data, tool, CombatEffectType.ADDITIONAL_WAVE) for tool in support_tools)


__all__ = [
    "Bonus",
    "attacker_flank_effects",
    "EffectResolver",
    "alliance_buff_bonuses",
    "attack_dialog_bonuses",
    "commander_bonuses",
    "effect_bonuses",
    "equipment_set_bonuses",
    "gem_bonuses",
    "construction_item_bonuses",
    "general_passive_bonuses",
    "general_skill_bonuses",
    "global_effect_bonuses",
    "global_unit_attack_bonuses",
    "legend_skill_value",
    "parse_bonus_entries",
    "effect_value_bonuses",
    "sceat_skill_bonuses",
    "support_tool_waves",
    "tool_effect_strength",
]
