"""
Typed rows from the GGE items payload.

Values arrive as strings, so every numeric field relies on pydantic coercion.
Tables whose meaning is not yet established are kept raw by
:class:`~empire_core.gamedata.data.GameData` instead of being modelled here on
a guess.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ITEMS units column "fightType": 0 = offensive, 1 = defensive.
FIGHT_TYPE_OFFENSIVE = 0
FIGHT_TYPE_DEFENSIVE = 1

# effecttypes sortCategory 7 is economy; combat filter strategies exclude it.
ECONOMY_SORT_CATEGORY = 7


def parse_stacks(value: str | None) -> list[tuple[int, int]]:
    """
    Parse the ``wodID+count#wodID+count`` encoding used for camp defences.

    Unparseable segments are skipped rather than failing the row.
    """
    stacks: list[tuple[int, int]] = []
    for part in str(value or "").split("#"):
        part = part.strip()
        if not part:
            continue
        wod_id, _, count = part.partition("+")
        try:
            stacks.append((int(wod_id), int(count or 0)))
        except ValueError:
            continue
    return stacks


def parse_ids(value: str | None) -> tuple[int, ...]:
    """Parse a comma-separated ID list."""
    ids = []
    for part in str(value or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return tuple(ids)


class _Row(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class UnitStats(_Row):
    """
    A combat unit.

    Units are the entries without ``slotTypes``; everything else is a tool.
    """

    wod_id: int = Field(alias="wodID")
    source: str = Field(alias="name", default="")
    unit_type: str = Field(alias="type", default="")
    role: str = ""
    level: int = 0
    speed: int = 0
    melee_attack: int = Field(alias="meleeAttack", default=0)
    range_attack: int = Field(alias="rangeAttack", default=0)
    melee_defence: int = Field(alias="meleeDefence", default=0)
    range_defence: int = Field(alias="rangeDefence", default=0)
    loot_value: float = Field(alias="lootValue", default=0)
    might_value: float = Field(alias="mightValue", default=0)
    mead_supply: int = Field(alias="meadSupply", default=0)
    beef_supply: int = Field(alias="beefSupply", default=0)
    food_supply: int = Field(alias="foodSupply", default=0)
    healing_cost_c1: int = Field(alias="healingCostC1", default=0)
    healing_cost_c2: int = Field(alias="healingCostC2", default=0)
    hybrid: bool = False
    fight_type: int = Field(alias="fightType", default=0)

    @property
    def is_melee(self) -> bool:
        return self.role == "melee"

    @property
    def is_ranged(self) -> bool:
        return self.role == "ranged"

    @property
    def is_allround(self) -> bool:
        """A hybrid unit, which the client treats as fitting either flank."""
        return self.hybrid

    @property
    def attack_value(self) -> int:
        """
        Raw offence, before any commander or equipment effects.

        The client adds a global-event bonus on top of this
        (EFFECT_TYPE_ATTACK_BONUS_UNIT), which is not modelled yet.
        """
        return max(self.melee_attack, self.range_attack)

    @property
    def is_offensive(self) -> bool:
        """
        Whether the game treats this unit as an attacker.

        This is the ``fightType`` column, not "has an attack value": a defensive
        unit such as a halberdier carries a small attack value but is never an
        auto-fill candidate.
        """
        return self.fight_type == FIGHT_TYPE_OFFENSIVE


class ToolStats(_Row):
    """
    A siege or defence tool.

    ``effects`` is kept raw; resolve it through
    :attr:`~empire_core.gamedata.data.GameData.effects`.
    """

    wod_id: int = Field(alias="wodID")
    source: str = Field(alias="name", default="")
    tool_type: str = Field(alias="type", default="")
    category: str = Field(alias="typ", default="")
    raw_slot_types: str = Field(alias="slotTypes", default="")
    raw_allowed_to_attack: str = Field(alias="allowedToAttack", default="")
    tool_category: str = Field(alias="toolCategory", default="")
    speed: int = 0
    # The client reads both of these with a default, and both defaults are
    # permissive: -1 is "no per-wave limit", 1 is "usable against an NPC".
    amount_per_wave: int = Field(alias="amountPerWave", default=-1)
    # 0/absent, 1 and 2 all occur; the client distinguishes them, so keep the value.
    delete_after_battle: int = Field(alias="deleteToolAfterBattle", default=0)
    can_attack_npc: bool = Field(alias="canBeUsedToAttackNPC", default=True)
    fight_type: int = Field(alias="fightType", default=0)
    effects: Any = None

    # The raw items columns, which are percentages. The client scales them by
    # 0.01 when it parses a tool, so the fractions are exposed as properties
    # below: scaling in a validator instead would re-scale on every cache
    # round-trip, since the cache stores what validation produced.
    raw_wall_bonus: float = Field(alias="wallBonus", default=0)
    raw_gate_bonus: float = Field(alias="gateBonus", default=0)
    raw_moat_bonus: float = Field(alias="moatBonus", default=0)
    raw_def_range_bonus: float = Field(alias="defRangeBonus", default=0)
    raw_def_melee_bonus: float = Field(alias="defMeleeBonus", default=0)
    raw_off_range_bonus: float = Field(alias="offRangeBonus", default=0)
    raw_off_melee_bonus: float = Field(alias="offMeleeBonus", default=0)

    @property
    def wall_bonus(self) -> float:
        """Wall protection this tool cancels, as a fraction."""
        return self.raw_wall_bonus * 0.01

    @property
    def gate_bonus(self) -> float:
        """Gate protection this tool cancels, as a fraction."""
        return self.raw_gate_bonus * 0.01

    @property
    def moat_bonus(self) -> float:
        """Moat protection this tool cancels, as a fraction."""
        return self.raw_moat_bonus * 0.01

    @property
    def def_range_bonus(self) -> float:
        """Defender ranged strength this tool cancels, as a fraction."""
        return self.raw_def_range_bonus * 0.01

    @property
    def def_melee_bonus(self) -> float:
        """Defender melee strength this tool cancels, as a fraction."""
        return self.raw_def_melee_bonus * 0.01

    @property
    def off_range_bonus(self) -> float:
        """Ranged attack this tool adds, as a fraction."""
        return self.raw_off_range_bonus * 0.01

    @property
    def off_melee_bonus(self) -> float:
        """Melee attack this tool adds, as a fraction."""
        return self.raw_off_melee_bonus * 0.01

    @property
    def slot_types(self) -> tuple[int, ...]:
        """Attack-screen slot types this tool fits."""
        return parse_ids(self.raw_slot_types)

    @property
    def allowed_targets(self) -> tuple[tuple[int, int], ...]:
        """
        ``(space_id, area_type)`` pairs this tool may attack.

        ``BasicUnitVO.parseSpaceIdAreaTypeValues`` reads
        ``"space+areaType#space+areaType"``. An empty list means no restriction,
        and ``-1`` in either position means "any".
        """
        pairs = []
        for entry in self.raw_allowed_to_attack.split("#"):
            if not entry:
                continue
            space, _, area = entry.partition("+")
            try:
                pairs.append((int(space), int(area)))
            except ValueError:
                continue
        return tuple(pairs)

    def is_allowed_by_attack_target(self, space_id: int | None, area_type: int | None) -> bool:
        """``BasicUnitVO.isAllowedByAttackTarget``: no list means allowed anywhere."""
        allowed = self.allowed_targets
        if not allowed:
            return True
        return any(
            (space_id is None or space in (space_id, -1)) and (area == -1 or area_type is None or area == area_type)
            for space, area in allowed
        )

    @property
    def is_attack_tool(self) -> bool:
        return self.category == "Attack"

    @property
    def is_defence_tool(self) -> bool:
        return self.category == "Defence"

    @property
    def is_consumed_in_battle(self) -> bool:
        return self.delete_after_battle > 0

    def fits_slot(self, slot_type: int) -> bool:
        """Whether this tool may go in the given slot type."""
        return slot_type in self.slot_types


class EffectDef(_Row):
    """
    An effect, e.g. ``relicOffensiveMeleeBonus``.

    An effect names *which* bonus an item grants; the effect type says what it
    modifies, and the cap says what it stacks with.
    """

    effect_id: int = Field(alias="effectID")
    name: str = ""
    effect_type_id: int = Field(alias="effectTypeID", default=0)
    cap_id: int | None = Field(alias="capID", default=None)
    raw_area_type_ids: str = Field(alias="areaTypeID", default="")
    is_pvp_fight: bool = Field(alias="isPvPFight", default=False)
    is_pve_fight: bool = Field(alias="isPvEFight", default=False)
    raw_space_ids: str = Field(alias="spaceIDs", default="")
    player_relation: str = Field(alias="playerRelation", default="")
    raid_boss_id: int | None = Field(alias="raidBossID", default=None)

    @property
    def area_type_ids(self) -> tuple[int, ...]:
        """Area types this effect applies to; empty means every area."""
        return parse_ids(self.raw_area_type_ids)

    def applies_to_area(self, area_type: int | None) -> bool:
        """Whether the effect counts against a target of this area type."""
        allowed = self.area_type_ids
        if not allowed or area_type is None:
            return True
        return area_type in allowed

    @property
    def space_ids(self) -> tuple[int, ...]:
        """Castle spaces this effect is limited to; empty means every space."""
        return parse_ids(self.raw_space_ids)

    def applies_to_space(self, space_id: int | None) -> bool:
        """Whether the effect counts in this castle space."""
        allowed = self.space_ids
        if not allowed or space_id is None:
            return True
        return space_id in allowed

    def applies_to_relation(self, relation: str | None) -> bool:
        """
        Whether the effect counts given the relationship to the target.

        Values seen: ``sameAlliance``, ``allianceInWar``, ``samePlayer``. An
        unconditioned effect always counts; passing None leaves conditioned
        ones in, since the relationship is unknown rather than absent.
        """
        if not self.player_relation or relation is None:
            return True
        return self.player_relation == relation

    def applies_to_raid_boss(self, raid_boss_id: int | None) -> bool:
        """Whether the effect counts against this raid boss."""
        if self.raid_boss_id is None or raid_boss_id is None:
            return True
        return self.raid_boss_id == raid_boss_id

    def applies_to_fight(self, *, player_target: bool | None) -> bool:
        """
        Whether the effect counts in this kind of fight.

        Some effects are flagged for player fights only and some for NPC fights
        only; an unflagged effect counts in both.
        """
        if player_target is None or not (self.is_pvp_fight or self.is_pve_fight):
            return True
        return self.is_pvp_fight if player_target else self.is_pve_fight


class EffectTypeDef(_Row):
    """An effect type, e.g. ``fameDefenseBonus``."""

    effect_type_id: int = Field(alias="effectTypeID")
    name: str = ""
    sort_category: int | None = Field(alias="sortCategory", default=None)
    combat_type: int | None = Field(alias="combatType", default=None)

    @property
    def is_economy(self) -> bool:
        """
        Economy effects, which every combat filter strategy drops.

        Category 7 in the client's own grouping.
        """
        return self.sort_category == ECONOMY_SORT_CATEGORY


class EffectCapDef(_Row):
    """
    The ceiling a group of effects stacks up to.

    A row without ``maxTotalBonus`` - cap 99 among them - is uncapped, which is
    why the field is optional rather than defaulting to zero.
    """

    cap_id: int = Field(alias="capID")
    max_total_bonus: float | None = Field(alias="maxTotalBonus", default=None)

    @property
    def is_uncapped(self) -> bool:
        return self.max_total_bonus is None


class EffectSpecRow(_Row):
    """
    Base for tables whose bonuses are an ``effectID&value`` string.

    Construction items, alliance buffs, global effects, sceat skills and
    buildings all encode their bonuses this way, comma separated.
    """

    raw_effects: str = Field(alias="effects", default="")


class ConstructionItemDef(EffectSpecRow):
    """
    A construction item - the decorations placed on castle buildings.

    Their bonuses are real combat bonuses: the flank unit limit item grants
    +2% per level, so a level 15 one is the +30% a player sees on the flanks.
    """

    construction_item_id: int = Field(alias="constructionItemID")
    name: str = ""
    group_id: int = Field(alias="constructionItemGroupID", default=0)
    level: int = 0
    rareness_id: int = Field(alias="rarenessID", default=0)
    slot_type_id: int = Field(alias="slotTypeID", default=0)
    effect_group_id: int = Field(alias="constructionItemEffectGroupID", default=0)


class AllianceBuffDef(EffectSpecRow):
    """One level of an alliance buff."""

    alliance_buff_id: int = Field(alias="allianceBuffID")
    series_id: int = Field(alias="allianceBuffSeriesID", default=0)
    level: int = 0
    max_level: int = Field(alias="maxLevel", default=0)


class GlobalEffectDef(EffectSpecRow):
    """A global (event) effect, active for everyone while its event runs."""

    global_effect_id: int = Field(alias="globalEffectID")
    name: str = ""
    boost_value: float = Field(alias="boostValue", default=0)
    min_level: int = Field(alias="minLevel", default=0)
    max_level: int = Field(alias="maxLevel", default=0)


class SceatSkillDef(EffectSpecRow):
    """One level of a sceat skill, from the Hall of Legends trees."""

    skill_id: int = Field(alias="skillID")
    skill_group_id: int = Field(alias="skillGroupID", default=0)
    level: int = 0
    skill_tree_id: int = Field(alias="skillTreeID", default=0)
    tier: int = 0


class GeneralSkillDef(EffectSpecRow):
    """One level of a general's skill."""

    skill_id: int = Field(alias="skillID")
    general_id: int = Field(alias="generalID", default=0)
    name: str = ""
    skill_group_id: int = Field(alias="skillGroupID", default=0)
    level: int = 0
    tier: int = 0


class FortificationDef(_Row):
    """
    A wall, gate or moat building and the protection it gives.

    The bonuses are the items columns, i.e. percentages: a level 3 castle wall
    reads 70 and protects by 0.70 once scaled.
    """

    wod_id: int = Field(alias="wodID")
    label: str = Field(alias="comment2", default="")
    level: int = 0
    wall_bonus: float = Field(alias="wallBonus", default=0)
    gate_bonus: float = Field(alias="gateBonus", default=0)
    moat_bonus: float = Field(alias="moatBonus", default=0)


class RelicEffectDef(_Row):
    """
    A relic effect, which is a *different id space* from a plain effect.

    A relic item's bonus ids index this table, not ``effects``: id 4 is
    ``perceptionBonus`` as a plain effect but ``gateReduction`` as a relic
    effect. Resolving in the wrong space yields a plausible, wrong answer.
    """

    relic_effect_id: int = Field(alias="id")
    effect_id: int = Field(alias="effectID", default=0)
    minimum_value: float = Field(alias="minimumValue", default=0)
    maximum_value: float = Field(alias="maximumValue", default=0)
    relic_effect_type: str = Field(alias="relicEffectType", default="")


class EquipmentEffectDef(_Row):
    """A bonus an equipment item can roll."""

    equipment_effect_id: int = Field(alias="equipmentEffectID")
    effect_id: int = Field(alias="effectID", default=0)
    bonus: float = 0
    wearer_id: int = Field(alias="wearerID", default=0)
    raw_item_group_ids: str = Field(alias="itemGroupID", default="")

    @property
    def item_group_ids(self) -> tuple[int, ...]:
        return parse_ids(self.raw_item_group_ids)


class LegendSkillDef(_Row):
    """One level of a legend skill, e.g. ``gateReduction``."""

    skill_id: int = Field(alias="skillID")
    level: int = 0
    tier: int = 0
    skill_tree_id: int = Field(alias="skillTreeID", default=0)
    skill_group_id: int = Field(alias="skillGroupID", default=0)
    effect_type: str = Field(alias="effectType", default="")
    total_effect_value: float = Field(alias="totalEffectValue", default=0)
    total_cost_skill_points: int = Field(alias="totalCostSkillPoints", default=0)


class AttackSlotDef(_Row):
    """An attack-screen slot and what unlocking it costs."""

    slot_id: int = Field(alias="slotID")
    cost_c2: int = Field(alias="costC2", default=0)


class ToolCategoryDef(_Row):
    """A tool category, e.g. ``basic``."""

    tool_category_id: int = Field(alias="toolCategoryID")
    name: str = ""


class HorseStats(_Row):
    """A travel booster - the value behind the ``HBW`` field on movements."""

    wod_id: int = Field(alias="wodID")
    source: str = Field(alias="name", default="")
    label: str = Field(alias="comment2", default="")
    horse_type: str = Field(alias="type", default="")
    unit_boost: float = Field(alias="unitBoost", default=0)
    market_boost: float = Field(alias="marketBoost", default=0)
    spy_boost: float = Field(alias="spyBoost", default=0)


class DefaultLordDef(_Row):
    """
    A default lord.

    These are the negative ``LID`` sentinels: -14 for "no commander" on a
    support movement, -21 for the NPC that holds a camp, and so on.
    """

    lord_id: int = Field(alias="lordID")
    lord_type: str = Field(alias="type", default="")
    wearer_id: int = Field(alias="wearerID", default=0)


class GeneralDef(_Row):
    """A general, the hero assigned to a commander."""

    general_id: int = Field(alias="generalID")
    name: str = Field(alias="generalName", default="")
    raw_attack_slots: str = Field(alias="attackSlots", default="")
    raw_defense_slots: str = Field(alias="defenseSlots", default="")
    rarity_id: int = Field(alias="generalRarityID", default=0)
    max_level: int = Field(alias="maxLevel", default=0)
    max_star_level: int = Field(alias="maxStarLevel", default=0)

    @property
    def attack_slots(self) -> tuple[int, ...]:
        return parse_ids(self.raw_attack_slots)

    @property
    def defense_slots(self) -> tuple[int, ...]:
        return parse_ids(self.raw_defense_slots)


class DungeonDefence(_Row):
    """
    What defends an NPC camp at a given victory count.

    The per-flank fields use the ``wodID+count#wodID+count`` encoding; read them
    through the parsed properties.
    """

    count_victories: int = Field(alias="countVictories", default=0)
    kingdom_id: int = Field(alias="kID", default=0)
    lord_id: int = Field(alias="lordID", default=0)
    skip_costs: int = Field(alias="skipCosts", default=0)
    raw_units_left: str = Field(alias="unitsL", default="")
    raw_units_middle: str = Field(alias="unitsM", default="")
    raw_units_right: str = Field(alias="unitsR", default="")
    raw_units_keep: str = Field(alias="unitsK", default="")
    raw_tools_left: str = Field(alias="toolL", default="")
    raw_tools_middle: str = Field(alias="toolM", default="")
    raw_tools_right: str = Field(alias="toolR", default="")

    @property
    def units_left(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_units_left)

    @property
    def units_middle(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_units_middle)

    @property
    def units_right(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_units_right)

    @property
    def units_keep(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_units_keep)

    @property
    def tools_left(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_tools_left)

    @property
    def tools_middle(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_tools_middle)

    @property
    def tools_right(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_tools_right)

    def total_units(self) -> int:
        """Defending units across every flank and the keep."""
        return sum(
            count
            for stacks in (
                self.units_left,
                self.units_middle,
                self.units_right,
                self.units_keep,
            )
            for _wod_id, count in stacks
        )


class NpcCampDefence(_Row):
    """
    An event camp's defence, shared shape across the camp tables.

    Covers the nomad, samurai, faction invasion and alliance invasion camps.
    """

    count_victory: int = Field(alias="countVictory", default=0)
    def_strength: int = Field(alias="defStrength", default=0)
    raw_defence_units: str = Field(alias="defenceUnits", default="")
    raw_defence_tools: str = Field(alias="defenceTools", default="")
    wall_bonus: float = Field(alias="wallBonus", default=0)
    gate_bonus: float = Field(alias="gateBonus", default=0)
    lord_id: int = Field(alias="lordID", default=0)
    guards: int = 0
    unit_wall_count: int = Field(alias="unitWallCount", default=0)
    cool_down: int = Field(alias="coolDown", default=0)
    dungeon_level: int = Field(alias="dungeonlevel", default=0)

    @property
    def defence_unit_ids(self) -> tuple[int, ...]:
        return parse_ids(self.raw_defence_units)

    @property
    def defence_tool_ids(self) -> tuple[int, ...]:
        return parse_ids(self.raw_defence_tools)


__all__ = [
    "ECONOMY_SORT_CATEGORY",
    "FIGHT_TYPE_DEFENSIVE",
    "FIGHT_TYPE_OFFENSIVE",
    "AttackSlotDef",
    "DefaultLordDef",
    "DungeonDefence",
    "EffectCapDef",
    "EffectDef",
    "EffectTypeDef",
    "EquipmentEffectDef",
    "GeneralDef",
    "HorseStats",
    "LegendSkillDef",
    "AllianceBuffDef",
    "ConstructionItemDef",
    "EffectSpecRow",
    "FortificationDef",
    "GeneralSkillDef",
    "GlobalEffectDef",
    "NpcCampDefence",
    "RelicEffectDef",
    "SceatSkillDef",
    "ToolCategoryDef",
    "ToolStats",
    "UnitStats",
    "parse_ids",
    "parse_stacks",
]
