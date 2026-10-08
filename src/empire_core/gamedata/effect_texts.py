"""
An effect with its value, described the way the game's tooltips describe it.

Usage:
    from empire_core.gamedata import EffectTemplate, describe_construction_item, describe_effect

    item = game_data.construction_items[ConstructionItem.BARRACKS_COST_G1_L1]
    describe_construction_item(item, game_data)        # "-2% recruitment costs"
    describe_effect(gem.effects[0], game_data, EffectTemplate.EQUIPMENT, trigger_chance=gem.trigger_chance)

The text comes from the language file (:mod:`empire_core.texts`), fetched on first use
and cached; the game data names the effect and how its value reads.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable, Iterable
from enum import Enum
from typing import TYPE_CHECKING

from empire_core.texts import LocalizedNumber, text

from .ids import EffectType
from .models import ConstructionItemDef, EffectDef, EffectValue, EquipmentEffectValue

if TYPE_CHECKING:
    from .data import GameData
    from .tables import BuildingDef

Number = int | float | None
Replacements = Callable[[EffectValue, "GameData", str], list[object]]


class EffectTemplate(Enum):
    """Which of the game's texts describes an effect, by where it is shown."""

    CONSTRUCTION_ITEM = "ci_effect_"
    """``ci_effect_<name>``: a construction item's bonuses (``ConstructionItemVO.effectText``, bundle line 47766)."""
    BUILDING = "effect_name_"
    """``effect_name_<name>``, with the effect's cap when it has one: a decoration's effects
    (``ADecoBuildingVO.createAdditionalEffectItems``, bundle line 11897)."""
    EQUIPMENT = "equip_effect_description_"
    """``equip_effect_description_<name>``: an equipment item's or a gem's bonus (``BonusVO.descriptionText``,
    ``EquipmentBonusVO.descriptionText`` and ``GemBonusVO.descriptionText``, bundle lines 5711, 20944 and 46807)."""


def _round(value: Number, digits: int) -> float:
    """``MathBase.round`` (dll line 7294): ``Math.round(value * 10^digits) / 10^digits``; NaN for no number."""
    if value is None:
        return math.nan
    scale = 10**digits
    return math.floor(value * scale + 0.5) / scale


def _first(effect: EffectValue) -> Number:
    """``parseFloat`` of the whole value: its first number."""
    return effect.values[0][0] if effect.values and effect.values[0] else None


def _wod_values(effect: EffectValue) -> dict[int, Number]:
    """``wodID+value`` pairs joined by ``#``: ``EffectValueWodID.parseFromValueString`` (bundle line 17699)."""
    pairs: dict[int, Number] = {}
    for part in effect.values:
        if part and part[0] is not None:
            pairs[int(part[0])] = part[1] if len(part) > 1 else None
    return pairs


def _map_values(effect: EffectValue) -> dict[Number, Number]:
    """
    Id and value pairs, ``#``-joined or one flat ``+`` list, each number ``parseInt``.

    Client: ``EffectValueMap.parseFromValueString`` (bundle line 31617)
    """

    def as_int(number: Number) -> Number:
        return None if number is None else math.trunc(number)

    if len(effect.values) > 1:
        pairs = [(part[0] if part else None, part[1] if len(part) > 1 else 0) for part in effect.values]
    else:
        flat = effect.values[0] if effect.values else ()
        pairs = [(flat[i], flat[i + 1] if i + 1 < len(flat) else 0) for i in range(0, len(flat), 2)]
    return {as_int(key): as_int(value) for key, value in pairs}


def _abs(value: Number) -> Number:
    return None if value is None else abs(value)


def _unit_name(game_data: GameData, wod_id: Number) -> str | None:
    """The text id of a unit's or tool's name: ``CastleWodData.getUnitVOByWodId`` then ``getNameString``."""
    if wod_id is None:
        return None
    unit = game_data.get_unit(int(wod_id)) or game_data.get_tool(int(wod_id))
    return unit.name_text_id if unit is not None else None


def _simple(effect: EffectValue, game_data: GameData, lang: str) -> list[object]:
    """``EffectValueSimple.textReplacements`` (bundle line 17754), the default."""
    return [LocalizedNumber(_round(_abs(_first(effect)), 2), compact=True, fractional_digits=2)]


def _wod_id(effect: EffectValue, game_data: GameData, lang: str) -> list[object]:
    """``EffectValueWodID.textReplacements`` (bundle line 17732): the first unit's value."""
    return [_round(_abs(next(iter(_wod_values(effect).values()), None)), 1)]


def _unit_speed_boost(effect: EffectValue, game_data: GameData, lang: str) -> list[object]:
    """``EffectValueUnitSpeedBoost.textReplacements`` (bundle line 62359): always 20."""
    return [20]


def _currency_boost(effect: EffectValue, game_data: GameData, lang: str) -> list[object]:
    """``EffectValueCurrencyBoost.textReplacements`` (bundle line 62371): the value and the currency's name."""
    pairs = _wod_values(effect)
    currency_id = next(iter(pairs), None)
    currency = game_data.currencies.get(currency_id) if currency_id is not None else None
    value = pairs.get(currency_id) if currency_id is not None else None
    name = text(currency.name_text_id, lang=lang) if currency is not None else ""
    return [_round(abs(value or 0), 1), name]


def _reserve_units(effect: EffectValue, game_data: GameData, lang: str) -> list[object]:
    """``EffectValueSpawnReserveUnit.textReplacements`` (bundle line 62324): the total and the first unit's name."""
    pairs = _wod_values(effect)
    total = sum(value or 0 for value in pairs.values())
    return [total, _unit_name(game_data, next(iter(pairs), None)) or ""]


def _reserve_unit_lines(effect: EffectValue, game_data: GameData) -> list[list[object]]:
    """``EffectValueSpawnReserveUnit.allTextReplacements`` (bundle line 62328): each unit's count and name."""
    named = ((value, _unit_name(game_data, wod_id)) for wod_id, value in _wod_values(effect).items())
    return [[value, name] for value, name in named if name is not None]


def _map(effect: EffectValue, game_data: GameData, lang: str) -> list[object]:
    """``EffectValueMap.textReplacements`` (bundle line 31658): the first value."""
    return [next(iter(_map_values(effect).values()), 0)]


_SUPPORT_UNIT_PACKAGES = {
    655: "troops_package_travellingKnight",
    714: "troops_package_demonWarriors",
    723: "troops_package_desertElite",
    686: "troops_package_kingsguard",
}


def _support_units(effect: EffectValue, game_data: GameData, lang: str) -> list[object]:
    """
    ``EquippableEffectValueSupportUnits.textReplacements`` (bundle line 62165): the total and the troops' name.

    Four wod ids name a troop package; any other unit its name, with its level when it has one.
    """
    pairs = _map_values(effect)
    total = sum(value or 0 for value in pairs.values())
    wod_id = next(iter(pairs), None)
    if wod_id in _SUPPORT_UNIT_PACKAGES:
        return [total, _SUPPORT_UNIT_PACKAGES[int(wod_id)]]
    unit = game_data.get_unit(int(wod_id)) if wod_id is not None else None
    if unit is None:
        return [total, ""]
    if unit.level > 0:
        level = text("levelX", unit.level, lang=lang)
        return [total, text("value_simple_comp", level, unit.name_text_id, lang=lang)]
    return [total, unit.name_text_id]


def _id_list(effect: EffectValue, game_data: GameData, lang: str) -> list[object]:
    """``EffectValueIdList.textReplacements`` (bundle line 62259): the ids themselves."""
    return [part[0] for part in effect.values if part]


def _one_digit(*factors: float) -> Replacements:
    """The value times each factor, rounded to one digit, as the commander ability values write it."""

    def replacements(effect: EffectValue, game_data: GameData, lang: str) -> list[object]:
        value = _first(effect)
        scaled = (_round(_abs(None if value is None else value * factor), 1) for factor in factors)
        return [LocalizedNumber(number, compact=True, fractional_digits=1) for number in scaled]

    return replacements


def _mind_clarity(effect: EffectValue, game_data: GameData, lang: str) -> list[object]:
    """
    ``EffectValueMindClarity.textReplacements`` (bundle line 62296): two numbers, of which a value read from
    text has only the first (``parseFromValueString``), so the second reads NaN as in the game.
    """
    return [
        LocalizedNumber(_round(_first(effect), 1), compact=True, fractional_digits=1),
        LocalizedNumber(math.nan, compact=True, fractional_digits=1),
    ]


def _ayala_falcon(effect: EffectValue, game_data: GameData, lang: str) -> list[object]:
    """``EffectValueAyalaFalcon.textReplacements`` (bundle line 62188)."""
    value = _round(abs(_first(effect) or 0), 1)
    return [" " + text("generals_abilities_desc_upgrade_placeholder_1021", value, lang=lang) if value > 0 else ""]


# The value class each effect type reads its value with, where it is not EffectValueSimple:
# EffectTypeEnum registrations (bundle line 1322). EffectValueMutateReserveUnit (214) needs the
# unit's upgradeWodID, which the units table model does not read, and EffectValueTools (61) has
# no effect type in the items, so neither is registered.
_REPLACEMENTS: dict[int, Replacements] = {
    EffectType.DEFENSE_SUPPORT_UNITS: _support_units,
    EffectType.ATTACK_SUPPORT_UNITS: _support_units,
    EffectType.ENABLE_BUILDINGS: _id_list,
    EffectType.RECRUITMENT_COST_DECREASE: _wod_id,
    EffectType.RECUITMENT_SPEED_BOOST: _wod_id,
    EffectType.TOOL_PRODUCTION_SPEED_BOOST: _wod_id,
    EffectType.ENABLE_UNITS: _id_list,
    EffectType.DISABLE_UNITS: _id_list,
    EffectType.UNIT_SPEED_BOOST: _unit_speed_boost,
    EffectType.ENABLE_CONSTRUCTION_ITEM_RECIPES: _id_list,
    EffectType.ATTACK_BONUS_UNIT: _map,
    EffectType.SPEED_BOOST_UNIT: _map,
    EffectType.LOOT_VALUE_BOOST_UNIT: _map,
    EffectType.FAME_BOOST_UNIT: _map,
    EffectType.CURRENCY_LOOT_BOOST: _currency_boost,
    EffectType.ENABLE_EXPANSION: _id_list,
    EffectType.ENABLE_CRAFTING_RECIPES: _id_list,
    EffectType.UNLOCK_ABILITY: _id_list,
    EffectType.CRAFTING_QUEUE_PRODUCTION_BOOST: _map,
    EffectType.ENABLE_CRAFTING_RECIPE_GROUPS: _id_list,
    EffectType.RESERVE_UNIT_KILL: _reserve_units,
    EffectType.SPAWN_RESERVE_UNIT: _reserve_units,
    EffectType.MIND_CLARITY_EVEN_WAVE: _mind_clarity,
    EffectType.AYALA_FALCON: _ayala_falcon,
    EffectType.LONGBOWS: _one_digit(1, 0.1),
    EffectType.PLUNDER: _wod_id,
    EffectType.HIDDEN_TREASURES: _one_digit(1, 1),
    EffectType.WINGS_WHIRLWIND: _one_digit(1, 1),
    EffectType.DRAGONSCALE_ARMOR: _one_digit(1, 2),
}

# The value classes with allTextReplacements, which the equipment texts write one line each
_LINES: dict[int, Callable[[EffectValue, GameData], list[list[object]]]] = {
    EffectType.RESERVE_UNIT_KILL: _reserve_unit_lines,
    EffectType.SPAWN_RESERVE_UNIT: _reserve_unit_lines,
}


# The effect types EffectTypeEnum (bundle line 1322) gives VALUE_NOMINAL_ADD as their simpleValueTextID:
# their values are counts, not percentages
_NOMINAL_TYPES = frozenset(
    {
        EffectType.DEFENSE_SUPPORT_UNITS,
        EffectType.ATTACK_SUPPORT_UNITS,
        EffectType.FOOD_PRODUCTION_BONUS,
        EffectType.FOOD_CAPACITY_BONUS,
        EffectType.MARKET_CARRIAGE_CAPACITY_BONUS,
        EffectType.ADDITIONAL_WAVES,
        EffectType.MEAD_PRODUCTION_INCREASE,
        EffectType.UNBOOSTED_MEAD_PRODUCTION,
        EffectType.HONEY_PRODUCTION_INCREASE,
        EffectType.UNBOOSTED_HONEY_PRODUCTION,
        EffectType.MEAD_CAPACITY_BONUS,
        EffectType.HONEY_CAPACITY_BONUS,
        EffectType.ATTACK_UNIT_AMOUNT_REINFORCEMENT_BONUS,
        EffectType.DEFENSE_UNIT_AMOUNT_YARD_BONUS,
        EffectType.ALLIANCE_DEFENSE_UNIT_AMOUNT_YARD_BONUS,
        EffectType.BEEF_PRODUCTION_INCREASE,
        EffectType.UNBOOSTED_BEEF_PRODUCTION,
        EffectType.BEEF_CAPACITY_BONUS,
        EffectType.UNIT_WALL_ABSOLUTE_AMOUNT,
        EffectType.CONSTRUCTION_QUEUE,
        EffectType.SIMULTANEOUS_CONSTRUCTION,
        EffectType.RAID_BOSS_WALL_REGENERATION_DELAY_LEFT,
        EffectType.RAID_BOSS_WALL_REGENERATION_DELAY_FRONT,
        EffectType.RAID_BOSS_WALL_REGENERATION_DELAY_RIGHT,
        EffectType.RAID_BOSS_WALL_REGENERATION_DELAY_ALL,
    }
)


def _with_cap(described: str, effect: EffectDef, game_data: GameData, lang: str) -> str:
    """
    A building effect's text with the most it stacks to, when its cap has a ``maxTotalBonus``.

    Client: ``ADecoBuildingVO.createAdditionalEffectItems`` (bundle line 11897)
    """
    cap = game_data.effect_caps.get(effect.cap_id) if effect.cap_id is not None else None
    if cap is None or cap.max_total_bonus is None or cap.max_total_bonus >= sys.float_info.max:
        return described
    nominal = effect.effect_type_id in _NOMINAL_TYPES
    maximum = text(f"equipment_bonus_maximum{'_noPercentage' if nominal else ''}", cap.max_total_bonus, lang=lang)
    return text("value_simple_comp", described, maximum, lang=lang)


def _text_name(effect: EffectDef, value: EffectValue, template: EffectTemplate) -> str:
    """
    The effect's part of the text id: its name, and for a crafting queue boost the queue it boosts.

    Client: ``EffectVO.getEnhancedName`` (bundle line 41716), which the equipment texts do not use
    """
    if template is not EffectTemplate.EQUIPMENT and effect.effect_type_id == EffectType.CRAFTING_QUEUE_PRODUCTION_BOOST:
        return f"{effect.name}_{next(iter(_map_values(value)), '')}"
    return effect.name


def _boss_names(effect: EffectDef, game_data: GameData, lang: str) -> list[object]:
    """``BonusVO.raidBossNameReplacement`` (bundle line 5723): the raid bosses it is for, as one last argument."""
    names = [
        text(f"are_boss_name_{boss.name}", lang=lang)
        for boss in (game_data.raid_bosses.get(boss_id) for boss_id in effect.raid_boss_ids)
        if boss is not None
    ]
    return [", ".join(names)] if names else []


def describe_effect(
    effect: EffectValue | EquipmentEffectValue,
    game_data: GameData,
    template: EffectTemplate = EffectTemplate.CONSTRUCTION_ITEM,
    *,
    trigger_chance: int = 100,
    lang: str = "en",
) -> str | None:
    """
    One bonus as the game describes it in ``lang``: ``"-5% recruitment costs"``.

    The text is the ``template``'s for the effect, filled with the value as the effect's type
    reads it (one number, the value of the first unit it names, the ids it unlocks, ...). An
    equipment effect resolves to its effect and always reads as equipment. A gem that does not
    always trigger (``GemDef.trigger_chance`` below 100) reads ``gem_effect_description_<gem
    type>`` with the chance first. Fetches the language file on first use (:func:`empire_core.texts.text`).

    Returns:
        The description; None when ``game_data`` does not have the effect

    Client: ``EffectTypeEnum`` registrations (bundle line 1322) choose the value class, whose
    ``textReplacements`` fill the text
    """
    if isinstance(effect, EquipmentEffectValue):
        equipment_effect = game_data.equipment_effects.get(effect.equipment_effect_id)
        effect_id = equipment_effect.effect_id if equipment_effect is not None else effect.equipment_effect_id
        effect = EffectValue(effect_id=effect_id, values=effect.values)
        template = EffectTemplate.EQUIPMENT
    effect_def = game_data.effects.get(effect.effect_id)
    if effect_def is None:
        return None
    replace = _REPLACEMENTS.get(effect_def.effect_type_id, _simple)
    if template is not EffectTemplate.EQUIPMENT:
        key = template.value + _text_name(effect_def, effect, template)
        described = text(key, *replace(effect, game_data, lang), lang=lang)
        return _with_cap(described, effect_def, game_data, lang) if template is EffectTemplate.BUILDING else described
    bosses = _boss_names(effect_def, game_data, lang)
    if trigger_chance != 100:
        gem_type = f"gem{effect_def.name[:1].upper()}{effect_def.name[1:]}"
        replacements = replace(effect, game_data, lang)
        return text(f"gem_effect_description_{gem_type}", trigger_chance, *replacements, *bosses, lang=lang)
    key = template.value + effect_def.name
    lines = _LINES.get(effect_def.effect_type_id)
    all_replacements = lines(effect, game_data) if lines else []
    if len(all_replacements) > 1:
        return "\n".join(text(key, *line, *bosses, lang=lang) for line in all_replacements)
    return text(key, *replace(effect, game_data, lang), *bosses, lang=lang)


def describe_effects(
    effects: Iterable[EffectValue],
    game_data: GameData,
    template: EffectTemplate = EffectTemplate.CONSTRUCTION_ITEM,
    *,
    lang: str = "en",
) -> list[str]:
    """Each bonus as :func:`describe_effect` describes it; an effect ``game_data`` lacks is left out."""
    described = (describe_effect(effect, game_data, template, lang=lang) for effect in effects)
    return [line for line in described if line is not None]


def describe_construction_item(item: ConstructionItemDef, game_data: GameData, *, lang: str = "en") -> str:
    """
    A construction item's bonuses as its tooltip lists them, one per line: the fixed bonuses of its own
    columns (``ci_effect_<column>``, the value as it is), then its ``effects``; ``ci_effect_NA`` for none.

    Client: ``ConstructionItemVO.effectText`` (bundle line 47766), the fixed bonuses' text from
    ``CastleEffectVO.constructionItemTextId`` (bundle line 79073)
    """
    fixed = [text(f"ci_effect_{bonus.effect.value}", bonus.value, lang=lang) for bonus in item.castle_effects]
    lines = fixed + describe_effects(item.effects, game_data, lang=lang)
    return "\n".join(lines) if lines else text("ci_effect_NA", lang=lang)


def describe_building(building: BuildingDef, game_data: GameData, *, lang: str = "en") -> list[str]:
    """
    A decoration's effects as its info lists them, its ``effects`` then its ``area_specific_effects``, each with
    its cap.

    Client: ``ABasicBuildingVO.allBuildingEffects`` (bundle line 18113) and
    ``ADecoBuildingVO.createAdditionalEffectItems`` (bundle line 11897)
    """
    effects = (*building.effects, *building.area_specific_effects)
    return describe_effects(effects, game_data, EffectTemplate.BUILDING, lang=lang)


__all__ = ["EffectTemplate", "describe_building", "describe_construction_item", "describe_effect", "describe_effects"]
