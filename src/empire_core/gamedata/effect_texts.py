"""
An effect with its value, described the way the game's tooltips describe it.

Usage:
    from empire_core.gamedata import EffectTemplate, describe_effect, describe_effects

    item = game_data.construction_items[ConstructionItem.BARRACKS_COST_G1_L1]
    describe_effects(item.effects, game_data)          # "-5% recruitment costs"
    describe_effect(gem.effects[0], game_data, EffectTemplate.EQUIPMENT, trigger_chance=gem.trigger_chance)

The text comes from the language file (:mod:`empire_core.texts`), fetched on first use
and cached; the game data names the effect and how its value reads.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from enum import Enum
from typing import TYPE_CHECKING

from empire_core.texts import LocalizedNumber, text

from .ids import EffectType
from .models import EffectDef, EffectValue, EquipmentEffectValue

if TYPE_CHECKING:
    from .data import GameData

Number = int | float | None
Replacements = Callable[[EffectValue, "GameData", str], list[object]]


class EffectTemplate(Enum):
    """Which of the game's texts describes an effect, by where it is shown."""

    CONSTRUCTION_ITEM = "ci_effect_"
    """``ci_effect_<name>``: a construction item's bonuses (``ConstructionItemVO.effectText``, bundle line 47766)."""
    BUILDING = "effect_name_"
    """``effect_name_<name>``: a decoration's effects (``ADecoBuildingVO.createAdditionalEffectItems``, bundle line
    11897)."""
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
        return text(template.value + _text_name(effect_def, effect, template), *replace(effect, game_data, lang), lang=lang)
    bosses = _boss_names(effect_def, game_data, lang)
    if trigger_chance != 100:
        gem_type = f"gem{effect_def.name[:1].upper()}{effect_def.name[1:]}"
        return text(f"gem_effect_description_{gem_type}", trigger_chance, *replace(effect, game_data, lang), *bosses, lang=lang)
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
) -> str:
    """
    Every bonus of a row, one per line, as :func:`describe_effect` describes them; an effect ``game_data`` lacks is
    left out.

    A construction item without any reads ``ci_effect_NA``, as in the game.

    Client: ``ConstructionItemVO.effectText`` (bundle line 47766)
    """
    lines = [line for line in (describe_effect(e, game_data, template, lang=lang) for e in effects) if line is not None]
    if not lines and template is EffectTemplate.CONSTRUCTION_ITEM:
        return text("ci_effect_NA", lang=lang)
    return "\n".join(lines)


__all__ = ["EffectTemplate", "describe_effect", "describe_effects"]
