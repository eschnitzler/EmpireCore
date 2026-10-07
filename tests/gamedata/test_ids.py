"""The generated game-data id enums and the script that writes them."""

import copy
import importlib.util
import json
import logging
import os
import pickle
import shutil
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from empire_core import gamedata
from empire_core.commanders import SelectedAbility
from empire_core.commanders.models.skills import SetGeneralAbilitiesRequest
from empire_core.enums import BuildingGroup, Kingdom, QuestConditionType
from empire_core.gamedata import (
    BuildingDef,
    GameData,
    HorseStats,
    QuestCondition,
    QuestDef,
    ScalingCampDef,
    TitleDef,
    default_cache_dir,
    ids,
)
from empire_core.gamedata.data import CACHE_FILENAME_TEMPLATE
from tests.gamedata.test_gamedata import LOOKUP_PAYLOAD, PAYLOAD

ROOT = Path(__file__).resolve().parents[2]
IDS_DIR = ROOT / "src" / "empire_core" / "gamedata" / "ids"
SNAPSHOT = ROOT / "scripts" / "gamedata_ids_texts.json"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "generate_gamedata_ids", ROOT / "scripts" / "generate_gamedata_ids.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gen = _load_script()

ENUMS = [getattr(ids, name) for name in ids.__all__ if isinstance(getattr(ids, name), type)]


def committed_texts():
    """The texts the committed names came from."""
    return gen.Texts(json.loads(SNAPSHOT.read_text()))


@pytest.fixture(autouse=True)
def no_live_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(lang: str = "en") -> dict[str, str]:
        raise AssertionError("the generator fetched the live language file; pass --texts")

    monkeypatch.setattr(gen, "fetch_texts", _forbidden)


# Rows of the tables GameData does not model, as the items payload has them, from v786.03.
IDS_PAYLOAD: dict[str, Any] = {
    **LOOKUP_PAYLOAD,
    "effects": [{"effectID": "1", "name": "fameDefenseBonus", "effectTypeID": "0", "capID": "0", "sortOrder": "6.9.1"}],
    "buildings": [
        {"wodID": 171, "name": "Keep", "level": "1", "group": "Building", "type": "Level1"},
        {"wodID": 172, "name": "Keep", "level": "2", "group": "Building", "type": "Level2"},
        {"wodID": 301, "comment2": "Supplies1", "group": "Building", "type": "Supplies1", "name": "Deco", "level": "1"},
        {"wodID": 401, "name": "Guard", "level": "0", "group": "Tower", "type": "Placeholder"},
        {"wodID": 501, "name": "Castlewall", "level": "1", "group": "Defence", "type": "Level1", "wallBonus": "30"},
    ],
    "researches": [
        {"researchID": "1", "comment2": "Rekrutierungsgeschw", "groupID": "1", "level": "1"},
        {"researchID": "256", "comment2": "recruitment speed", "groupID": "41", "level": "1"},
    ],
    "events": [
        {"eventID": "5", "comment2": "Herald of the Invasion", "eventType": "NomadInvasion"},
        {"eventID": "6", "comment2": "Prime Day Special Offer", "eventType": "Paymentreward"},
        {"eventID": "74", "eventType": "Paymentreward"},
    ],
    "lootBoxes": [{"lootBoxID": "1", "name": "MysteryBoxBronze", "rarity": "1"}],
    "lootBoxTypes": [{"lootBoxTypeID": "1", "lootBoxTheme": "MysteryBox", "lootBoxKeyPayoutThreshold": "10"}],
    "quests": [
        {"questID": "3047", "questSeriesID": "159", "conditions": "buyRubies+1"},
        {"questID": "3600", "eventID": "129", "comment1": "AME", "conditions": "spendCurrency1+1000"},
    ],
    "dailyactivities": [
        {"dailyQuestID": "1", "triggerKingdomID": "-1", "conditions": "login+1"},
        {"dailyQuestID": "7", "triggerKingdomID": "0", "conditions": "countDungeons+1"},
    ],
    "equipment_groups": [{"itemGroupID": "102", "name": "AttackPVP", "wearerID": "2", "slotID": "6"}],
    "eventAutoScalingDifficultyTypes": [{"difficultyTypeID": "2", "name": "easyPlus"}],
    "constructionItems": [
        {
            "constructionItemID": "1",
            "name": "barracksCost",
            "constructionItemGroupID": "1",
            "level": "1",
            "rarenessID": "1",
        },
    ],
    "gems": [
        {"gemID": "12", "comment2": "Lizard's eye", "gemLevelID": "0", "setID": "40", "effects": "1&10"},
        {"gemID": "55", "gemLevelID": "6", "wearerID": "1", "triggerChance": "30", "effects": "1&13"},
    ],
    "sceatSkills": [{"skillID": "41", "skillGroupID": "1", "level": "1", "skillTreeID": "3", "effects": "294&1942"}],
    "achievements": [
        {
            "achievementID": "1",
            "achievementSeriesID": "0",
            "achievementSeriesNumber": "1",
            "conditions": "achievementPoints+100",
        },
        {
            "achievementID": "1107",
            "achievementSeriesID": "373",
            "achievementSeriesNumber": "6",
            "conditions": "defeatNomadOnDifficulty+800+309",
        },
    ],
    "horses": [{"wodID": 1002, "comment1": "Stable1", "comment2": "Warhorse", "name": "Horse", "type": "2"}],
    "titles": [{"titleID": "0", "type": "FAME", "displayType": "prefix", "mightValue": "25"}],
    "allianceCoatLayouts": [
        {"allianceCoatLayoutID": "1", "comment1": "free", "noofColors": "1", "isDefault": "1"},
        {"allianceCoatLayoutID": "9", "comment1": "nomad", "eventID": "72", "noofColors": "2", "effects": "413&1000"},
    ],
    "allianceCoatColors": [{"allianceCoatColorID": "1", "color": "0xDBDACA"}],
    "mainquests": [{"mainQuestID": "3", "IDsForAnnounced": "93", "IDsForRunning": "95", "IDsForDone": "106"}],
}

# Which GameData table each enum's values index.
TABLE_OF: dict[str, str] = {
    "Building": "buildings",
    "ConstructionItem": "construction_items",
    "DifficultyType": "difficulty_types",
    "EquipmentGroup": "equipment_groups",
    "Event": "events",
    "LootBox": "loot_boxes",
    "LootBoxType": "loot_box_types",
    "QuestId": "quests",
    "DailyQuestId": "daily_quests",
    "Research": "researches",
    "Unit": "units",
    "Tool": "tools",
    "Effect": "effects",
    "EffectType": "effect_types",
    "CurrencyId": "currencies",
    "General": "generals",
    "GeneralAbility": "general_abilities",
    "GeneralSkill": "general_skills",
    "LegendSkill": "legend_skills",
    "RaidBoss": "raid_bosses",
    "GlobalEffect": "global_effects",
    "Gem": "gems",
    "SceatSkill": "sceat_skills",
    "Achievement": "achievements",
    "Horse": "horses",
    "Title": "titles",
    "AllianceCrestLayout": "alliance_crest_layouts",
    "AllianceCrestColor": "alliance_crest_colors",
}
"""Which GameData table each enum's values index; ``Currency`` keys and ``MainQuest`` (no table) aside."""


def _cached_game_data() -> GameData | None:
    cache = default_cache_dir() / CACHE_FILENAME_TEMPLATE.format(version=ids.ITEMS_VERSION)
    return GameData._read_cache(cache, ids.ITEMS_VERSION)


class TestPackage:
    def test_every_enum_is_exported_from_gamedata(self):
        assert {e.__name__ for e in ENUMS} == set(TABLE_OF) | {"Currency", "MainQuest"}
        for enum in ENUMS:
            assert getattr(gamedata, enum.__name__) is enum
        assert gamedata.ITEMS_VERSION == ids.ITEMS_VERSION

    def test_no_member_is_an_alias(self):
        for enum in ENUMS:
            assert len(list(enum)) == len(enum.__members__), enum.__name__

    def test_every_file_names_the_version_it_came_from(self):
        header = f"# Generated by scripts/generate_gamedata_ids.py from items {ids.ITEMS_VERSION}; do not edit.\n"
        files = sorted(IDS_DIR.glob("*.py"))
        assert files
        for path in files:
            assert path.read_text().startswith(header), path.name

    def test_known_ids(self):
        assert ids.Currency.GENERALS_XP_250 == "GXP1"
        assert ids.General.TORIL == 101
        assert ids.Unit.MEAD_RANGER_L6 == 211
        assert (ids.GlobalEffect.SPEED_BOOST_2, ids.GlobalEffect.SPEED_BOOST_11) == (2, 11)
        assert ids.CurrencyId[ids.Currency.KHAN_TABLETS.name] == 1

    def test_the_suite_fixtures_name_the_same_ids(self):
        payload = dict(IDS_PAYLOAD)
        payload["units"] = [*payload["units"], *PAYLOAD["units"]]
        data = GameData.parse(ids.ITEMS_VERSION, payload)
        checked = 0
        for table in gen.tables(data, committed_texts()):
            enum = getattr(ids, table.enum)
            for name, value in gen.members(table):
                if name in enum.__members__:
                    assert enum[name].value == value, f"{table.enum}.{name}"
                    checked += 1
        assert checked >= 20

    def test_every_value_is_in_the_items_data(self):
        data = _cached_game_data()
        if data is None:
            pytest.skip(f"no cached items v{ids.ITEMS_VERSION}")
            return
        for enum in ENUMS:
            if enum is ids.Currency:
                keys = {row.json_key for row in data.currencies.values()}
                assert {m.value for m in enum} <= keys
                continue
            if enum is ids.MainQuest:
                assert {m.value for m in enum} == {int(row["mainQuestID"]) for row in data.raw("mainquests")}
                continue
            table = getattr(data, TABLE_OF[enum.__name__])
            assert {m.value for m in enum} == set(table), enum.__name__

    def test_regenerating_from_the_same_items_changes_nothing(self):
        # The full items file is ~20 MB and not in the repo; point EMPIRE_CORE_ITEMS_JSON at it.
        path = os.environ.get("EMPIRE_CORE_ITEMS_JSON")
        if not path:
            pytest.skip("EMPIRE_CORE_ITEMS_JSON is not set")
            return
        payload = json.loads(Path(path).read_text())
        data = GameData.parse(gen.items_version(Path(path), payload), payload)
        if data.version != ids.ITEMS_VERSION:
            pytest.skip(f"{path} is items v{data.version}, not v{ids.ITEMS_VERSION}")
        committed = {file.name: file.read_text() for file in IDS_DIR.glob("*.py")}
        assert gen.render(data, committed_texts()) == committed


@pytest.fixture
def lookup_data() -> GameData:
    return GameData.parse(ids.ITEMS_VERSION, IDS_PAYLOAD)


class TestMemberData:
    def test_fixed_columns_the_name_does_not_say_are_baked_in(self):
        unit = ids.Unit.VETERAN_SABERSLASHER
        assert (unit.value, unit.level, unit.role) == (5, -1, "melee")
        assert (ids.Unit.MEAD_RANGER_L6.level, ids.Unit.MEAD_RANGER_L6.role) == (6, "ranged")
        assert ids.General.TORIL.rarity_id == 4
        assert ids.GeneralSkill.TORIL_ASPECTOFTHE_DRAGON_L1.general_id == ids.General.TORIL
        assert ids.Currency.KHAN_TABLETS.currency_id == ids.CurrencyId.KHAN_TABLETS
        assert ids.CurrencyId.KHAN_TABLETS.json_key == ids.Currency.KHAN_TABLETS
        assert (ids.Building.KEEP_L1.value, ids.Building.KEEP_L1.group, ids.Building.KEEP_L1.level) == (
            171,
            "Building",
            1,
        )
        assert (ids.Research.STRENGTH_TRAINING_L1.group_id, ids.Research.STRENGTH_TRAINING_L1.level) == (41, 1)
        assert ids.ConstructionItem.BARRACKS_COST_G1_L1.rareness_id == 1
        assert (ids.EquipmentGroup.ATTACK_PVP.wearer_id, ids.EquipmentGroup.ATTACK_PVP.slot_id) == (2, 6)
        assert ids.LootBox.MYSTERY_BOX_BRONZE_R1.rarity == 1
        assert (ids.QuestId.BUY_RUBIES.series_id, ids.QuestId.SPEND_CURRENCY1.event_id) == (159, 129)
        assert ids.DailyQuestId.COUNT_DUNGEONS_7.trigger_kingdom_id == Kingdom.GREEN
        assert any(tool.category == "Defence" for tool in ids.Tool)

    def test_columns_the_name_says_are_not_baked_in(self):
        for member, dropped in [
            (ids.Unit.MEAD_RANGER_L6, "unit_type"),
            (ids.Tool.PREMIUMSTAKES, "tool_type"),
            (ids.General.TORIL, "row_name"),
            (ids.Building.KEEP_L1, "building_type"),
            (ids.LegendSkill.GATE_REDUCTION_T0_G1_L1, "effect_type"),
        ]:
            assert not hasattr(member, dropped), (member, dropped)

    @pytest.mark.parametrize(
        "enum",
        ["EffectType", "RaidBoss", "GlobalEffect", "Event", "DifficultyType", "LootBoxType"],
        ids=lambda name: name,
    )
    def test_an_enum_without_columns_is_plain(self, enum):
        text = Path(str(sys.modules[getattr(ids, enum).__module__].__file__)).read_text()
        assert "__new__" not in text and "from __future__" not in text
        assert f"class {enum}(IntEnum):" in text

    def test_baked_columns_match_the_generated_rows(self):
        payload = dict(IDS_PAYLOAD)
        payload["units"] = [*payload["units"], *PAYLOAD["units"]]
        data = GameData.parse(ids.ITEMS_VERSION, payload)
        for table in gen.tables(data, committed_texts()):
            enum = getattr(ids, table.enum)
            for row in table.rows:
                member = enum._value2member_map_.get(row.value)
                if member is not None:
                    assert tuple(getattr(member, a.name) for a in table.attrs) == row.attrs, member

    def test_members_are_their_values(self):
        unit, currency, event = ids.Unit.MEAD_RANGER_L6, ids.Currency.KHAN_TABLETS, ids.Event.NOMAD_INVASION
        assert unit == 211 and hash(unit) == hash(211) and {211: "x"}[unit] == "x"
        assert event == 5 and isinstance(event, int)
        assert currency == "KT" and hash(currency) == hash("KT")
        for member in (unit, currency, event):
            assert pickle.loads(pickle.dumps(member)) is member
            assert copy.copy(member) is member and copy.deepcopy(member) is member
        assert json.dumps([unit, currency, event]) == '[211, "KT", 5]'
        assert ids.Unit(211) is unit and ids.Currency("KT") is currency and ids.Event(5) is event

    def test_members_go_on_the_wire_as_plain_values(self):
        request = SetGeneralAbilitiesRequest(
            general_id=ids.General.TORIL,
            abilities=[SelectedAbility(slot_id=0, ability_id=ids.GeneralAbility.POWER_SURGE_L1)],
        )
        payload = request.to_payload()
        assert payload == {"GID": 101, "SAIDS": [[0, 10011]]}
        assert type(payload["GID"]) is int and type(payload["SAIDS"][0][1]) is int

        class Typed(BaseModel):
            unit: ids.Unit
            currency: ids.Currency
            event: ids.Event

        typed = Typed.model_validate({"unit": 211, "currency": "KT", "event": 5})
        assert typed.unit is ids.Unit.MEAD_RANGER_L6 and typed.event is ids.Event.NOMAD_INVASION
        assert typed.model_dump(mode="json") == {"unit": 211, "currency": "KT", "event": 5}

    def test_game_data_lookups_take_members(self, lookup_data):
        assert lookup_data.get_unit(ids.Unit.MEAD_RANGER_L6) is lookup_data.units[211]
        assert lookup_data.currency(ids.Currency.KHAN_TABLETS) is lookup_data.currencies[1]
        assert lookup_data.generals.get(ids.General.TORIL) is lookup_data.generals[101]

    def test_the_enums_load_lazily(self):
        code = (
            "import sys, empire_core, empire_core.gamedata as g\n"
            "heavy = [f'empire_core.gamedata.ids.{m}' for m in ('units', 'tools', 'effects', 'buildings', 'quests')]\n"
            "assert not any(m in sys.modules for m in heavy)\n"
            "import empire_core.gamedata.ids.events\n"
            "assert not any(m in sys.modules for m in heavy)\n"
            "g.Unit\n"
            "assert 'empire_core.gamedata.ids.units' in sys.modules\n"
            "assert 'empire_core.gamedata.ids.tools' not in sys.modules\n"
        )
        subprocess.run([sys.executable, "-c", code], check=True)

    def test_the_package_init_is_what_the_generator_writes(self):
        tables = gen.tables(GameData.parse(ids.ITEMS_VERSION, IDS_PAYLOAD))
        assert (IDS_DIR / "__init__.py").read_text() == gen.render_init(ids.ITEMS_VERSION, tables)

    def test_the_package_still_lists_and_imports_every_enum(self):
        names = set(ids.__all__)
        assert names <= set(dir(ids))
        from empire_core.gamedata.ids import Tool, Unit

        assert (ids.Unit, ids.Tool) == (Unit, Tool)
        with pytest.raises(AttributeError):
            ids.NotAnEnum  # type: ignore[attr-defined]  # noqa: B018


class TestTables:
    def test_every_table_is_keyed_by_its_enum(self, lookup_data):
        d = lookup_data
        assert d.buildings[ids.Building.KEEP_L1].building_id is ids.Building.KEEP_L1
        assert d.researches[ids.Research.STRENGTH_TRAINING_L1].label == "recruitment speed"
        assert d.events[ids.Event.NOMAD_INVASION].event_type == "NomadInvasion"
        assert d.loot_boxes[ids.LootBox.MYSTERY_BOX_BRONZE_R1].name == "MysteryBoxBronze"
        assert d.loot_box_types[ids.LootBoxType.MYSTERY_BOX].key_payout_threshold == 10
        assert d.equipment_groups[ids.EquipmentGroup.ATTACK_PVP].slot_id == 6
        assert d.difficulty_types[ids.DifficultyType.EASY_PLUS].name == "easyPlus"
        assert d.quests[ids.QuestId.BUY_RUBIES].series_id == 159
        assert d.daily_quests[ids.DailyQuestId.LOGIN].trigger_kingdom == -1
        for enum_name, field in TABLE_OF.items():
            enum = getattr(ids, enum_name)
            for key in getattr(d, field):
                assert type(key) is (enum if key in enum._value2member_map_ else int), (field, key)

    def test_a_plain_id_indexes_a_table(self, lookup_data):
        assert lookup_data.buildings[171] is lookup_data.buildings[ids.Building.KEEP_L1]
        assert lookup_data.quests.get(3047) is lookup_data.quests[ids.QuestId.BUY_RUBIES]

    def test_a_row_the_enum_lacks_is_kept_by_its_plain_id_without_a_warning(self, caplog):
        payload = {"buildings": [{"wodID": "999999", "name": "Future", "level": "1"}]}
        with caplog.at_level(logging.WARNING):
            data = GameData.parse(ids.ITEMS_VERSION, payload)
        assert type(next(iter(data.buildings))) is int
        assert data.buildings[999999].name == "Future"
        assert not caplog.records

    def test_a_row_without_an_id_is_left_out_and_the_last_of_one_id_kept(self):
        rows = [{"eventType": "NoId"}, "junk", {"eventID": "x"}, {"eventID": "5", "eventType": "A"}]
        rows += [{"eventID": 5, "eventType": "B"}, {"eventID": "7abc", "eventType": "C"}]
        events = GameData.parse(ids.ITEMS_VERSION, {"events": rows}).events
        assert {key: row.event_type for key, row in events.items()} == {5: "B", 7: "C"}

    def test_tables_survive_the_cache(self, tmp_path):
        payload = {
            **IDS_PAYLOAD,
            "buildings": [*IDS_PAYLOAD["buildings"], {"wodID": "999999", "name": "Future", "sortOrder": "0"}],
            "titles": [{"titleID": "0", "topX": "0", "effects": "504&20"}],
        }
        lookup_data = GameData.parse(ids.ITEMS_VERSION, payload)
        cache = tmp_path / "items.trimmed.json"
        lookup_data._write_cache(cache)
        again = GameData._read_cache(cache, lookup_data.version)
        assert again is not None
        assert lookup_data.buildings[171].name == "Keep"
        # one side has read a table, the other not: equality is the fields and the rows
        assert again == lookup_data
        for field in [*TABLE_OF.values(), "titles", "scaling_camps"]:
            assert getattr(again, field) == getattr(lookup_data, field), field
        assert again.titles[0].top_x == 0 and again.buildings[999999].sort_order == 0
        assert set(again.buildings) == {171, 172, 301, 401, 501, 999999}
        assert type(again.quests[3047].quest_id) is ids.QuestId
        assert type(again.buildings[401].group) is BuildingGroup
        assert type(again.quests[3047].conditions[0].condition_type) is QuestConditionType
        assert type(next(k for k in again.buildings if k == 999999)) is int

    def test_the_fingerprint_covers_the_game_data_tables(self, monkeypatch):
        # A cache from before a table or column was added reads back with it empty
        from empire_core.gamedata import data as module

        before = module._schema_fingerprint()

        class Wider(GameData):
            added: dict[int, dict] = {}

        monkeypatch.setattr(module, "GameData", Wider)
        assert module._schema_fingerprint() != before
        monkeypatch.undo()
        assert {BuildingDef, QuestDef, QuestCondition, TitleDef, ScalingCampDef} <= set(module._CACHED_MODELS)


class TestGenerator:
    @pytest.fixture
    def items(self) -> GameData:
        return GameData.parse("786.03", IDS_PAYLOAD)

    def members(self, items: GameData, enum: str) -> dict[str, object]:
        table = next(t for t in gen.tables(items) if t.enum == enum)
        return dict(gen.members(table))

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("MeadRanger", "MEAD_RANGER"),
            ("CooldownReductionRBC", "COOLDOWN_REDUCTION_RBC"),
            ("relicOffensiveMeleeBonusPVP", "RELIC_OFFENSIVE_MELEE_BONUS_PVP"),
            ("DecoCatalyst1", "DECO_CATALYST1"),
        ],
    )
    def test_camel_case_becomes_upper_snake(self, text, expected):
        assert gen.to_snake(text) == expected

    def test_identifiers_are_valid_and_public(self):
        assert gen.identifier("3rd place!", "U") == "U_3RD_PLACE"
        assert gen.identifier("", "U") == "U"
        assert gen.identifier("a-b  c", "U") == "A_B_C"
        assert gen.identifier("None", "U") == "NONE"

    def test_units_carry_their_level_and_colliding_ones_their_id(self, items):
        assert self.members(items, "Unit") == {
            "OGERMACE_7": 7,
            "OGERMACE_68": 68,
            "MEAD_RANGER_L6": 211,
            "MEAD_RANGER_L7": 212,
        }
        assert self.members(items, "Tool") == {
            "ELITE_COMBO_RAM_113": 113,
            "ELITE_COMBO_RAM_564": 564,
            "PREMIUMSTAKES_L2": 646,
        }

    def test_every_member_of_a_colliding_group_is_suffixed(self, items):
        assert self.members(items, "GlobalEffect") == {
            "COOLDOWN_REDUCTION_RBC": 1,
            "SPEED_BOOST_2": 2,
            "SPEED_BOOST_11": 11,
        }

    def test_skills_name_their_general_and_level(self, items):
        assert self.members(items, "GeneralSkill") == {
            "TORIL_ASPECTOFTHE_DRAGON_L1": 10110201,
            "TORIL_ASPECTOFTHE_DRAGON_L2": 10110202,
            "G102_ASPECTOFTHE_DRAGON_L1": 10210201,
        }
        assert self.members(items, "GeneralAbility") == {"POWER_SURGE_L1": 10011, "POWER_SURGE_L2": 10012}
        assert self.members(items, "LegendSkill") == {"GATE_REDUCTION_T0_G1_L1": 1, "GATE_REDUCTION_T0_G1_L2": 2}

    def test_new_tables_are_named_from_their_name_columns(self, items):
        assert self.members(items, "Building") == {
            "KEEP_L1": 171,
            "KEEP_L2": 172,
            "DECO_SUPPLIES1_L1": 301,
            "GUARD_L0": 401,
            "CASTLEWALL_L1": 501,
        }
        assert self.members(items, "Research") == {"REKRUTIERUNGSGESCHW_G1_L1": 1, "RECRUITMENT_SPEED_G41_L1": 256}
        assert self.members(items, "Event") == {"NOMAD_INVASION": 5, "PAYMENTREWARD_6": 6, "PAYMENTREWARD_74": 74}
        assert self.members(items, "LootBox") == {"MYSTERY_BOX_BRONZE_R1": 1}
        assert self.members(items, "EquipmentGroup") == {"ATTACK_PVP": 102}
        assert self.members(items, "DifficultyType") == {"EASY_PLUS": 2}
        assert self.members(items, "ConstructionItem") == {"BARRACKS_COST_G1_L1": 1}

    def test_tables_the_game_names_nothing_of_fall_back_on_notes_conditions_and_ids(self, items):
        assert self.members(items, "Gem") == {"GEM_12": 12, "GEM_55": 55}
        assert self.members(items, "SceatSkill") == {"SCEAT_G1_L1": 41}
        assert self.members(items, "Achievement") == {"ACHIEVEMENT_POINTS_L1": 1, "DEFEAT_NOMAD_ON_DIFFICULTY_L6": 1107}
        assert self.members(items, "Horse") == {"WARHORSE_STABLE1": 1002}
        assert self.members(items, "Title") == {"TITLE_0": 0}
        assert self.members(items, "AllianceCrestLayout") == {"FREE": 1, "NOMAD": 9}
        assert self.members(items, "AllianceCrestColor") == {"COLOR_1": 1}
        assert self.members(items, "MainQuest") == {"MAIN_QUEST_3": 3}

    def test_unnamed_tables_are_named_from_the_text_the_game_shows(self):
        texts = {
            "gem_unique_12": "Lizard's eye",
            "gem_effect_name_gemFameDefenseBonus": "Gem of the glorious defender: {0}",
            "dialog_legendTemple_sceat_1_name": "New heights",
            "achievementName_373": "Nomad vanquisher",
            "playerTitle_0": "Knight",
            "allianceCoat_Layout_name_9": "Nomad's Wrath Emblem",
            "mainquest_3_title": "The lovely Beatrice",
        }
        named = {
            "Gem": {"LIZARDS_EYE": 12, "GEM_OF_THE_GLORIOUS_DEFENDER_L6": 55},
            "SceatSkill": {"NEW_HEIGHTS_L1": 41},
            "Achievement": {"ACHIEVEMENT_POINTS_L1": 1, "NOMAD_VANQUISHER_L6": 1107},
            "Title": {"KNIGHT": 0},
            "AllianceCrestLayout": {"FREE": 1, "NOMADS_WRATH_EMBLEM": 9},
            "MainQuest": {"THE_LOVELY_BEATRICE": 3},
        }
        for enum, members in named.items():
            assert self.text_members(IDS_PAYLOAD, texts, enum) == members, enum

    def test_a_gem_that_always_triggers_and_one_reusing_a_look_have_their_own_texts(self):
        payload = {
            "effects": [{"effectID": "1", "name": "fameDefenseBonus", "effectTypeID": "0"}],
            "gems": [
                {"gemID": "5", "gemLevelID": "3", "effects": "1&10"},
                {"gemID": "6", "gemLevelID": "0", "reuseAssetOfGemID": "12"},
            ],
        }
        texts = {
            "gem_effect_name_gemFameDefenseBonus_100": "Gem of glory: {0}",
            "gem_unique_12": "Lizard's eye",
            "gem_unique_6": "Not its name",
        }
        assert self.text_members(payload, texts, "Gem") == {"GEM_OF_GLORY_L3": 5, "LIZARDS_EYE": 6}

    def test_research_names_are_unique_by_group_and_level(self):
        # Two groups share a note; group and level keep them apart, and a row without a note still gets a name
        payload = {
            "researches": [
                {"researchID": "10", "comment2": "Refined Lumber", "groupID": "7", "level": "1"},
                {"researchID": "11", "comment2": "Refined Lumber", "groupID": "8", "level": "1"},
                {"researchID": "12", "groupID": "9", "level": "2"},
            ]
        }
        table = next(t for t in gen.tables(GameData.parse("786.03", payload)) if t.enum == "Research")
        assert dict(gen.members(table)) == {
            "REFINED_LUMBER_G7_L1": 10,
            "REFINED_LUMBER_G8_L1": 11,
            "RESEARCH_G9_L2": 12,
        }
        assert gen.collided(table) == 0

    def test_currencies_by_key_and_by_id_share_names(self, items):
        assert self.members(items, "Currency") == {"KT": "KT", "DD": "DD"}
        assert self.members(items, "CurrencyId") == {"KT": 1, "DD": 100000}

    def text_members(self, payload: dict[str, Any], texts: dict[str, str], enum: str) -> dict[str, object]:
        table = next(t for t in gen.tables(GameData.parse("786.03", payload), gen.Texts(texts)) if t.enum == enum)
        return dict(gen.members(table))

    def test_currencies_are_named_from_their_english_name(self):
        payload = {
            "currencies": [
                {"currencyID": "1001", "Name": "1MinSkip", "JSONKey": "MS1", "assetName": "1MinSkip"},
                {"currencyID": "10001", "Name": "ShardToril", "JSONKey": "STL"},
                {"currencyID": "7003", "Name": "GenXP1000", "JSONKey": "GXP3", "assetName": "GenXP1000"},
                {"currencyID": "100001", "Name": "DecoCatalyst1", "JSONKey": "DC1", "assetName": "DecoCatalyst"},
                {"currencyID": "100002", "Name": "DecoCatalyst2", "JSONKey": "DC2", "assetName": "DecoCatalyst"},
                {"currencyID": "8", "Name": "CastlePassageToken", "JSONKey": "CPT"},
            ]
        }
        texts = {
            "currency_name_1minskip": "Skip 1 minute",
            "currency_name_ShardToril": "Toril's general shard",
            "currency_name_GenXP1000": "1,000 generals XP",
            "currency_name_DecoCatalyst": "Decoration catalyst",
        }
        named = {
            "SKIP_1_MINUTE": "MS1",
            "TORILS_GENERAL_SHARD": "STL",
            "GENERALS_XP_1000": "GXP3",
            "DC1": "DC1",
            "DC2": "DC2",
            "CPT": "CPT",
        }
        assert self.text_members(payload, texts, "Currency") == named
        by_id = self.text_members(payload, texts, "CurrencyId")
        assert by_id == {name: int(row["currencyID"]) for name, row in zip(named, payload["currencies"], strict=True)}

    def test_researches_are_named_from_their_title_unless_they_unlock_recipes(self):
        payload = {
            "effects": [
                {"effectID": "107", "name": "recruitSpeedBoost", "effectTypeID": "19"},
                {"effectID": "700", "name": "enableCraftingRecipes", "effectTypeID": "170"},
            ],
            "researches": [
                {
                    "researchID": "256",
                    "comment2": "recruitment speed",
                    "groupID": "41",
                    "level": "1",
                    "effects": "107&-5",
                },
                {
                    "researchID": "257",
                    "comment2": "recruitment speed",
                    "groupID": "41",
                    "level": "2",
                    "effects": "107&-6",
                },
                {"researchID": "900", "comment2": "Beefstorage", "groupID": "193", "level": "1", "effects": "700&3"},
                {"researchID": "10001", "comment2": "UNWALKABLE 001", "groupID": "1001", "level": "1"},
            ],
        }
        texts = {"research_41_title": "Strength training", "research_193_title": "Not a recipe's name"}
        assert self.text_members(payload, texts, "Research") == {
            "STRENGTH_TRAINING_L1": 256,
            "STRENGTH_TRAINING_L2": 257,
            "BEEFSTORAGE_G193_L1": 900,
            "UNWALKABLE_001_G1001_L1": 10001,
        }

    def test_a_title_two_research_groups_share_falls_back_on_the_id(self):
        payload = {
            "researches": [
                {"researchID": "10", "groupID": "7", "level": "1"},
                {"researchID": "11", "groupID": "8", "level": "1"},
            ]
        }
        texts = {"research_7_title": "Genius", "research_8_title": "Genius"}
        assert self.text_members(payload, texts, "Research") == {"GENIUS_L1_10": 10, "GENIUS_L1_11": 11}

    def test_the_texts_used_are_the_snapshot(self):
        texts = gen.Texts({"@metadata": {"versionNo": "1"}, "Currency_Name_KhanTablet": "Khan tablets", "unused": "x"})
        assert texts.get("currency_name_KhanTablet") == "Khan tablets"
        assert texts.get("missing") is None
        assert json.loads(texts.snapshot()) == {"currency_name_KhanTablet": "Khan tablets"}

    def test_output_is_deterministic_and_importable(self, items, tmp_path, monkeypatch):
        first = gen.render(items)
        reversed_payload = {key: list(reversed(rows)) for key, rows in IDS_PAYLOAD.items()}
        assert gen.render(GameData.parse("786.03", reversed_payload)) == first

        package = tmp_path / "fake_ids"
        gen.write(first, package)
        spec = importlib.util.spec_from_file_location(
            "fake_ids", package / "__init__.py", submodule_search_locations=[str(package)]
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, "fake_ids", module)
        spec.loader.exec_module(module)
        assert module.GlobalEffect.SPEED_BOOST_11 == 11
        assert issubclass(module.Currency, str) and issubclass(module.Currency, Enum)
        assert module.ITEMS_VERSION == "786.03"

    def test_output_is_ruff_clean(self, items, tmp_path):
        ruff = shutil.which("ruff")
        if ruff is None:
            pytest.skip("ruff is not installed")
            return
        files = gen.render(items)
        long_name = "A" * 90
        wide = gen.Table(
            "wide",
            "Wide",
            "W",
            "Rows too long for one line.",
            "none",
            [
                gen.Row(long_name, 1, "1", ("x" * 40, 2)),
                gen.Row("SHORT", 2, "2", ("y", 3)),
                gen.Row("QUOTED", 3, "3", ('say "hi" and \'bye\' "now"', 4)),
                gen.Row("APOSTROPHE", 4, "4", ("it's a \\ path", 5)),
            ],
            (gen.Attr("first_column_with_a_long_name", "str", "Long."), gen.Attr("second_long_column", "int", "Too.")),
        )
        plain = gen.Table("plain", "Plain", "P", "No columns.", "none", [gen.Row("ONLY", 1, "1")])
        files["wide.py"] = gen.render_module("786.03", [(wide, gen.members(wide)), (plain, gen.members(plain))])
        files["plain.py"] = gen.render_module("786.03", [(plain, gen.members(plain))])
        assert "__new__" not in files["plain.py"] and "    ONLY = 1\n" in files["plain.py"]
        assert f"    {long_name} = (\n" in files["wide.py"] and "    SHORT = 2, " in files["wide.py"]
        assert """    QUOTED = 3, 'say "hi" and \\'bye\\' "now"', 4\n""" in files["wide.py"]
        gen.write(files, tmp_path)
        subprocess.run([ruff, "format", "--check", "--config", str(ROOT / "pyproject.toml"), str(tmp_path)], check=True)
        subprocess.run([ruff, "check", "--config", str(ROOT / "pyproject.toml"), str(tmp_path)], check=True)

    def test_items_version_comes_from_the_file(self, tmp_path):
        payload = {"versionInfo": {"version": {"@value": "786.03"}}}
        assert gen.items_version(tmp_path / "whatever.json", payload) == "786.03"
        assert gen.items_version(tmp_path / "items_v785.01.json", {}) == "785.01"
        with pytest.raises(SystemExit):
            gen.items_version(tmp_path / "items.json", {})


class TestCheck:
    @pytest.fixture
    def items_file(self, tmp_path) -> Path:
        path = tmp_path / "items_v786.03.json"
        path.write_text(json.dumps(IDS_PAYLOAD))
        return path

    @pytest.fixture(autouse=True)
    def texts_file(self, tmp_path) -> Path:
        path = tmp_path / "lang_en.json"
        path.write_text(
            json.dumps({"currency_name_KhanTablet": "Khan tablets", "research_41_title": "Strength training"})
        )
        return path

    def run(self, items_file: Path, out: Path, *extra: str) -> int:
        texts, snapshot = out.parent / "lang_en.json", out.parent / "snapshot.json"
        return gen.main(
            ["--items", str(items_file), "--out", str(out), "--texts", str(texts), "--snapshot", str(snapshot), *extra]
        )

    def test_the_snapshot_keeps_only_the_texts_names_used(self, items_file, tmp_path):
        out = tmp_path / "ids"
        assert self.run(items_file, out) == 0
        assert json.loads((tmp_path / "snapshot.json").read_text()) == {
            "currency_name_KhanTablet": "Khan tablets",
            "research_41_title": "Strength training",
        }
        assert "    KHAN_TABLETS = " in (out / "currencies.py").read_text()

    def test_generating_from_the_snapshot_changes_nothing(self, items_file, tmp_path):
        out = tmp_path / "ids"
        assert self.run(items_file, out) == 0
        (tmp_path / "lang_en.json").write_text((tmp_path / "snapshot.json").read_text())
        assert self.run(items_file, out, "--check") == 0

    def test_check_notices_a_renamed_text(self, items_file, tmp_path):
        out = tmp_path / "ids"
        assert self.run(items_file, out) == 0
        snapshot = (tmp_path / "snapshot.json").read_text()
        (tmp_path / "lang_en.json").write_text(json.dumps({"currency_name_KhanTablet": "Khan slabs"}))
        names = tmp_path / "names.md"
        assert self.run(items_file, out, "--check", "--diff-names", str(names)) == 1
        assert "- `Currency.KHAN_TABLETS` -> `Currency.KHAN_SLABS`" in names.read_text()
        assert "- `Research.STRENGTH_TRAINING_L1` -> `Research.RECRUITMENT_SPEED_G41_L1`" in names.read_text()
        assert (tmp_path / "snapshot.json").read_text() == snapshot

    def test_check_notices_a_stale_snapshot(self, items_file, tmp_path):
        out = tmp_path / "ids"
        assert self.run(items_file, out) == 0
        (tmp_path / "snapshot.json").write_text("{}\n")
        assert self.run(items_file, out, "--check") == 1

    def test_a_table_whose_enum_is_not_generated_yet_generates(self, items_file, tmp_path, monkeypatch):
        # As before Horse's first generation: the package has no Horse, and HorseStats has not looked it up
        (validator,) = HorseStats.model_fields["wod_id"].metadata
        monkeypatch.setattr(validator.func, "_enum", "Horse")
        monkeypatch.delitem(ids._MODULES, "Horse")
        monkeypatch.delattr(ids, "Horse", raising=False)
        with pytest.raises(AttributeError):
            ids.Horse  # noqa: B018

        out = tmp_path / "ids"
        assert self.run(items_file, out) == 0
        assert "class Horse(IntEnum):" in (out / "horses.py").read_text()
        assert "    WARHORSE_STABLE1 = 1002\n" in (out / "horses.py").read_text()
        assert '"Horse": "horses",' in (out / "__init__.py").read_text()
        with pytest.raises(AttributeError):
            ids.Horse  # noqa: B018

    def test_check_passes_on_what_it_would_write(self, items_file, tmp_path):
        out = tmp_path / "ids"
        assert self.run(items_file, out) == 0
        written = {path.name: path.read_text() for path in out.glob("*.py")}
        assert self.run(items_file, out, "--check") == 0
        assert {path.name: path.read_text() for path in out.glob("*.py")} == written

    @pytest.mark.parametrize("change", ["edit", "extra", "missing", "empty"])
    def test_check_fails_on_any_difference(self, items_file, tmp_path, change):
        out = tmp_path / "ids"
        if change != "empty":
            assert self.run(items_file, out) == 0
        if change == "edit":
            (out / "units.py").write_text("# edited\n")
        elif change == "extra":
            (out / "leftover.py").write_text("")
        elif change == "missing":
            (out / "events.py").unlink()
        before = {path.name: path.read_text() for path in out.glob("*.py")} if out.exists() else {}
        assert self.run(items_file, out, "--check") == 1
        after = {path.name: path.read_text() for path in out.glob("*.py")} if out.exists() else {}
        assert after == before

    def test_name_changes_against_the_committed_package(self, items_file, texts_file, tmp_path):
        out = tmp_path / "ids"
        assert self.run(items_file, out) == 0
        payload = json.loads(items_file.read_text())
        payload["events"] = [
            {"eventID": "5", "eventType": "NomadAttack"},
            {"eventID": "6", "eventType": "Paymentreward"},
            {"eventID": "99", "eventType": "Brandnew"},
        ]
        payload["lootBoxes"] = []
        payload["equipment_groups"] = [{"itemGroupID": "103", "name": "AttackPVP", "wearerID": "2", "slotID": "6"}]
        items_file.write_text(json.dumps(payload))
        names, footer = tmp_path / "names.md", tmp_path / "footer.txt"
        with pytest.raises(SystemExit):
            # The generator refuses an empty table, so LootBox has to keep a row
            self.run(items_file, out, "--check")
        payload["lootBoxes"] = [{"lootBoxID": "2", "name": "MysteryBoxBronze", "rarity": "2"}]
        items_file.write_text(json.dumps(payload))
        assert self.run(items_file, out, "--check", "--diff-names", str(names), "--breaking-footer", str(footer)) == 1

        texts = gen.Texts(json.loads(texts_file.read_text()))
        changes = gen.name_changes(gen.render(GameData.parse("786.03", payload), texts), out)
        assert changes.renamed == [
            ("Event.NOMAD_INVASION", "Event.NOMAD_ATTACK"),
            ("Event.PAYMENTREWARD_6", "Event.PAYMENTREWARD"),
        ]
        assert changes.removed == ["Event.PAYMENTREWARD_74", "LootBox.MYSTERY_BOX_BRONZE_R1"]
        assert changes.changed == ["EquipmentGroup.ATTACK_PVP"]
        assert changes.added == ["Event.BRANDNEW", "LootBox.MYSTERY_BOX_BRONZE_R2"]
        report = names.read_text()
        assert "### Renamed (2)" in report and "- `Event.NOMAD_INVASION` -> `Event.NOMAD_ATTACK`" in report
        assert "### Removed (2)" in report and "### Now another id (1)" in report and "### Added (2)" in report
        assert footer.read_text().startswith("BREAKING CHANGE: Event.NOMAD_INVASION is now Event.NOMAD_ATTACK; ")

    def test_an_unchanged_package_reports_no_names(self, items_file, tmp_path):
        out = tmp_path / "ids"
        assert self.run(items_file, out) == 0
        names, footer = tmp_path / "names.md", tmp_path / "footer.txt"
        assert self.run(items_file, out, "--check", "--diff-names", str(names), "--breaking-footer", str(footer)) == 0
        assert names.read_text() == "No member was added, renamed or removed.\n"
        assert footer.read_text() == ""

    @pytest.mark.parametrize("version", ["786.03\nx", "7'86", "", "786."])
    def test_a_malformed_version_is_refused(self, tmp_path, version):
        path = tmp_path / "items.json"
        path.write_text(json.dumps({**IDS_PAYLOAD, "versionInfo": {"version": {"@value": version or " "}}}))
        with pytest.raises(SystemExit, match="not dotted digits"):
            gen.main(["--items", str(path), "--out", str(tmp_path / "ids")])

    def test_the_committed_package_is_current(self):
        path = os.environ.get("EMPIRE_CORE_ITEMS_JSON")
        if not path:
            pytest.skip("EMPIRE_CORE_ITEMS_JSON is not set")
            return
        assert gen.main(["--items", path, "--texts", str(SNAPSHOT), "--check"]) == 0


class TestStaleness:
    def test_is_current(self):
        assert ids.is_current(GameData(version=ids.ITEMS_VERSION))
        assert not ids.is_current(GameData(version="0.01"))

    @pytest.fixture
    def load(self, monkeypatch, tmp_path):
        monkeypatch.setattr("empire_core.gamedata.data._warned_versions", set())
        monkeypatch.setattr("empire_core.gamedata.cdn.fetch_items_data", lambda version: PAYLOAD)

        def load(version: str) -> GameData:
            monkeypatch.setattr("empire_core.gamedata.cdn.get_items_version", lambda: version)
            return GameData.load(cache_dir=tmp_path)

        return load

    def stale_warnings(self, caplog) -> list[str]:
        return [
            r.getMessage() for r in caplog.records if "empire_core.gamedata.ids was generated from" in r.getMessage()
        ]

    def test_load_warns_once_when_the_ids_are_from_another_version(self, load, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.gamedata.data"):
            load("0.01")
            load("0.01")

        (message,) = self.stale_warnings(caplog)
        assert "v0.01" in message and f"v{ids.ITEMS_VERSION}" in message

    def test_load_is_quiet_for_the_version_the_ids_came_from(self, load, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.gamedata.data"):
            load(ids.ITEMS_VERSION)

        assert self.stale_warnings(caplog) == []


def test_every_combat_effect_type_is_a_generated_effect_type():
    # CombatEffectType keeps the client's EffectTypeEnum names; the generated enum is named from the table
    from empire_core.enums import CombatEffectType
    from empire_core.gamedata.ids import EffectType

    missing = [member.name for member in CombatEffectType if member.value not in EffectType._value2member_map_]
    assert missing == []
