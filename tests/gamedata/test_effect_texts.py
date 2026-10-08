"""Effect descriptions: the template, the value as its effect type reads it, and the stubbed language file."""

from typing import Any

import pytest
import requests

from empire_core import texts
from empire_core.gamedata import EffectTemplate, EffectValue, GameData, describe_effect, describe_effects
from empire_core.gamedata.models import ConstructionItemDef, EquipmentEffectValue, GemDef

LANG_FILE = {
    "ci_effect_recruitCostReduction": "-{0}% recruitment costs",
    "ci_effect_simpleBonus": "+{0}% defence",
    "ci_effect_craftingBoost_2": "Queue 2 is {0}% faster",
    "ci_effect_NA": "No effect",
    "effect_name_simpleBonus": "Defence +{0}%",
    "equip_effect_description_simpleBonus": "+{0}% defence{1}",
    "equip_effect_description_unitAttack": "+{0}% attack",
    "equip_effect_description_supportUnits": "{0} {1} join the defence",
    "equip_effect_description_spawnReserve": "{0} {1} spawn",
    "equip_effect_description_currencyLoot": "+{0}% {1} looted",
    "equip_effect_description_unlockUnits": "Unlocks {0} and {1}",
    "equip_effect_description_longbows": "{0}% and {1}%",
    "gem_effect_description_gemSimpleBonus": "{0}% chance: +{1}% defence",
    "troops_package_kingsguard": "Kingsguard",
    "meadranger_name": "Mead ranger",
    "currency_name_Khan": "Khan tablets",
    "are_boss_name_Dragon": "the dragon",
    "levelX": "Level {0}",
    "value_simple_comp": "{0} {1}",
    "generic_kForThousand": "k",
}

PAYLOAD = {
    "effects": [
        {"effectID": "1", "name": "recruitCostReduction", "effectTypeID": "70"},
        {"effectID": "2", "name": "simpleBonus", "effectTypeID": "0"},
        {"effectID": "3", "name": "craftingBoost", "effectTypeID": "188"},
        {"effectID": "4", "name": "unitAttack", "effectTypeID": "148"},
        {"effectID": "5", "name": "supportUnits", "effectTypeID": "47"},
        {"effectID": "6", "name": "spawnReserve", "effectTypeID": "213"},
        {"effectID": "7", "name": "currencyLoot", "effectTypeID": "168"},
        {"effectID": "8", "name": "unlockUnits", "effectTypeID": "79"},
        {"effectID": "9", "name": "longbows", "effectTypeID": "1023"},
        {"effectID": "10", "name": "simpleBonus", "effectTypeID": "0", "raidBossID": "1"},
    ],
    "units": [
        {"wodID": "211", "type": "MeadRanger", "level": "6"},
        {"wodID": "212", "type": "MeadRanger", "level": "0"},
    ],
    "currencies": [{"currencyID": "40", "Name": "Khan", "JSONKey": "KT"}],
    "raidBosses": [{"raidBossID": "1", "name": "Dragon"}],
    "equipment_effects": [{"equipmentEffectID": "900", "effectID": "4"}],
}


@pytest.fixture(autouse=True)
def stub_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"test attempted a real HTTP request: {args!r}")

    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(texts, "fetch_texts", lambda lang="en": LANG_FILE)


@pytest.fixture
def game_data() -> GameData:
    return GameData.parse("786.03", PAYLOAD)


def value(effect_id: int, *values: tuple[int | float | None, ...]) -> EffectValue:
    return EffectValue(effect_id=effect_id, values=values)


class TestConstructionItems:
    def test_a_plain_value_is_rounded_to_two_digits(self, game_data: GameData) -> None:
        assert describe_effect(value(2, (12.345,)), game_data) == "+12.35% defence"
        assert describe_effect(value(2, (-250000,)), game_data) == "+250k% defence"

    def test_a_unit_keyed_value_is_the_first_units(self, game_data: GameData) -> None:
        assert describe_effect(value(1, (686, 12.345), (687, 50)), game_data) == "-12.3% recruitment costs"

    def test_a_crafting_queue_boost_names_its_queue(self, game_data: GameData) -> None:
        assert describe_effect(value(3, (2, 25)), game_data) == "Queue 2 is 25% faster"

    def test_a_row_reads_one_line_per_bonus(self, game_data: GameData) -> None:
        item = ConstructionItemDef.model_validate({"constructionItemID": "1", "effects": "2&10,1&686+5,999&1"})
        assert describe_effects(item.effects, game_data) == "+10% defence\n-5% recruitment costs"
        assert describe_effects((), game_data) == "No effect"

    def test_an_effect_the_game_data_lacks(self, game_data: GameData) -> None:
        assert describe_effect(value(999, (1,)), game_data) is None


class TestOtherTemplates:
    def test_buildings(self, game_data: GameData) -> None:
        assert describe_effect(value(2, (5,)), game_data, EffectTemplate.BUILDING) == "Defence +5%"

    def test_equipment_names_its_raid_bosses(self, game_data: GameData) -> None:
        assert describe_effect(value(10, (5,)), game_data, EffectTemplate.EQUIPMENT) == "+5% defencethe dragon"
        assert describe_effect(value(2, (5,)), game_data, EffectTemplate.EQUIPMENT) == "+5% defence{1}"

    def test_an_equipment_effect_resolves_to_its_effect(self, game_data: GameData) -> None:
        bonus = EquipmentEffectValue(equipment_effect_id=900, values=((686, 30), (687, 40)))
        assert describe_effect(bonus, game_data) == "+30% attack"

    def test_a_gem_that_may_not_trigger_reads_its_chance_first(self, game_data: GameData) -> None:
        gem = GemDef.model_validate({"gemID": "5", "gemLevelID": "3", "effects": "2&10", "triggerChance": "25"})
        described = describe_effect(gem.effects[0], game_data, EffectTemplate.EQUIPMENT, trigger_chance=25)
        assert described == "25% chance: +10% defence"


class TestValueKinds:
    def test_support_units_name_their_package_or_unit(self, game_data: GameData) -> None:
        def described(*values: tuple[int, ...]) -> str | None:
            return describe_effect(value(5, *values), game_data, EffectTemplate.EQUIPMENT)

        assert described((686, 30), (687, 20)) == "50 Kingsguard join the defence"
        assert described((211, 10)) == "10 Level 6 Mead ranger join the defence"
        assert described((212, 10)) == "10 Mead ranger join the defence"

    def test_reserve_units_read_one_line_per_unit(self, game_data: GameData) -> None:
        described = describe_effect(value(6, (211, 3), (212, 4)), game_data, EffectTemplate.EQUIPMENT)
        assert described == "3 Mead ranger spawn\n4 Mead ranger spawn"
        assert describe_effect(value(6, (211, 3)), game_data, EffectTemplate.EQUIPMENT) == "3 Mead ranger spawn"

    def test_a_currency_boost_names_its_currency(self, game_data: GameData) -> None:
        described = describe_effect(value(7, (40, 12.36)), game_data, EffectTemplate.EQUIPMENT)
        assert described == "+12.4% Khan tablets looted"

    def test_an_id_list_fills_in_the_ids(self, game_data: GameData) -> None:
        assert describe_effect(value(8, (211,), (212,)), game_data, EffectTemplate.EQUIPMENT) == "Unlocks 211 and 212"

    def test_a_commander_ability_value_with_factors(self, game_data: GameData) -> None:
        assert describe_effect(value(9, (25,)), game_data, EffectTemplate.EQUIPMENT) == "25% and 2.5%"
