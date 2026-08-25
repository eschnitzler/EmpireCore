"""Game data loading: classification, coercion, caching."""

import json

import pytest

from empire_core.exceptions import NetworkError
from empire_core.gamedata import GameData, ToolStats, UnitStats

# Entries captured from the live items payload (values arrive as strings).
MEAD_RANGER = {
    "wodID": 211,
    "name": "Barracks",
    "type": "MeadRanger",
    "role": "ranged",
    "level": "6",
    "speed": "34",
    "rangeAttack": "270",
    "meleeDefence": "25",
    "rangeDefence": "42",
    "lootValue": "52",
    "mightValue": "11",
    "meadSupply": "2",
    "healingCostC1": "339",
    "fightType": "0",
}
PREMIUM_STAKES = {
    "wodID": 646,
    "name": "Dworkshop",
    "type": "Premiumstakes",
    "typ": "Defence",
    "slotTypes": "4,9",
    "speed": "22",
    "moatBonus": "80",
    "fightType": "1",
}
NOMAD_BOOST = {
    "wodID": 107,
    "name": "Eventtool",
    "type": "NomadRageTabletBoost",
    "typ": "Attack",
    "slotTypes": "1,2,9",
    "fightType": "0",
}
PAYLOAD = {"units": [MEAD_RANGER, PREMIUM_STAKES, NOMAD_BOOST]}


class TestParsing:
    def test_units_and_tools_are_split_on_slot_types(self):
        data = GameData.parse("783.01", PAYLOAD)

        assert set(data.units) == {211}
        assert set(data.tools) == {646, 107}

    def test_boost_items_are_not_units(self):
        # Sending one of these as an army earns MOVEMENT_HAS_NO_UNITS.
        data = GameData.parse("783.01", PAYLOAD)

        assert data.is_tool(107)
        assert not data.is_unit(107)

    def test_string_values_are_coerced(self):
        unit = GameData.parse("783.01", PAYLOAD).get_unit(211)

        assert unit is not None
        assert (unit.range_attack, unit.melee_defence, unit.range_defence) == (270, 25, 42)
        assert unit.level == 6
        assert unit.mead_supply == 2
        assert unit.is_ranged and not unit.is_melee
        assert unit.attack_value == 270
        assert unit.is_offensive

    def test_tool_slot_types_are_parsed(self):
        tool = GameData.parse("783.01", PAYLOAD).get_tool(646)

        assert tool is not None
        assert tool.slot_types == (4, 9)
        assert tool.fits_slot(9)
        assert not tool.fits_slot(1)
        assert tool.is_defence_tool

    def test_malformed_entry_does_not_lose_the_table(self):
        payload = {"units": [MEAD_RANGER, {"wodID": 5, "role": ["not", "a", "string"]}, {"junk": 1}]}

        data = GameData.parse("783.01", payload)

        assert set(data.units) == {211}

    def test_units_by_role(self):
        data = GameData.parse("783.01", PAYLOAD)
        assert [u.wod_id for u in data.units_by_role("ranged")] == [211]
        assert data.units_by_role("melee") == []


class TestLoading:
    def test_load_writes_and_reuses_the_cache(self, tmp_path, monkeypatch):
        fetches = []

        monkeypatch.setattr("empire_core.gamedata.get_items_version", lambda: "783.01")

        def fake_fetch(version):
            fetches.append(version)
            return PAYLOAD

        monkeypatch.setattr("empire_core.gamedata.fetch_items_data", fake_fetch)

        first = GameData.load(cache_dir=tmp_path)
        second = GameData.load(cache_dir=tmp_path)

        assert fetches == ["783.01"], "the second load must come from the cache"
        assert first.units.keys() == second.units.keys()
        assert second.get_unit(211).range_attack == 270

    def test_refresh_bypasses_the_cache(self, tmp_path, monkeypatch):
        fetches = []
        monkeypatch.setattr("empire_core.gamedata.get_items_version", lambda: "783.01")
        monkeypatch.setattr(
            "empire_core.gamedata.fetch_items_data",
            lambda version: (fetches.append(version), PAYLOAD)[1],
        )

        GameData.load(cache_dir=tmp_path)
        GameData.load(cache_dir=tmp_path, refresh=True)

        assert fetches == ["783.01", "783.01"]

    def test_new_version_invalidates_the_cache(self, tmp_path, monkeypatch):
        versions = iter(["783.01", "784.00"])
        fetches = []
        monkeypatch.setattr("empire_core.gamedata.get_items_version", lambda: next(versions))
        monkeypatch.setattr(
            "empire_core.gamedata.fetch_items_data",
            lambda version: (fetches.append(version), PAYLOAD)[1],
        )

        GameData.load(cache_dir=tmp_path)
        data = GameData.load(cache_dir=tmp_path)

        assert fetches == ["783.01", "784.00"]
        assert data.version == "784.00"

    def test_corrupt_cache_is_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr("empire_core.gamedata.get_items_version", lambda: "783.01")
        monkeypatch.setattr("empire_core.gamedata.fetch_items_data", lambda version: PAYLOAD)
        (tmp_path / "items_v783.01.trimmed.json").write_text("{not json")

        assert GameData.load(cache_dir=tmp_path).get_unit(211) is not None

    def test_unwritable_cache_still_loads(self, tmp_path, monkeypatch):
        monkeypatch.setattr("empire_core.gamedata.get_items_version", lambda: "783.01")
        monkeypatch.setattr("empire_core.gamedata.fetch_items_data", lambda version: PAYLOAD)
        blocker = tmp_path / "blocked"
        blocker.write_text("i am a file, not a directory")

        assert GameData.load(cache_dir=blocker / "sub").get_unit(211) is not None

    def test_version_failure_raises_network_error(self, tmp_path, monkeypatch):
        def boom():
            raise OSError("dns is having a day")

        monkeypatch.setattr("empire_core.gamedata.get_items_version", boom)

        with pytest.raises(NetworkError):
            GameData.load(cache_dir=tmp_path)

    def test_items_failure_raises_network_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("empire_core.gamedata.get_items_version", lambda: "783.01")

        def boom(version):
            raise OSError("connection reset")

        monkeypatch.setattr("empire_core.gamedata.fetch_items_data", boom)

        with pytest.raises(NetworkError):
            GameData.load(cache_dir=tmp_path)

    def test_cache_file_holds_only_the_trimmed_tables(self, tmp_path, monkeypatch):
        monkeypatch.setattr("empire_core.gamedata.get_items_version", lambda: "783.01")
        monkeypatch.setattr("empire_core.gamedata.fetch_items_data", lambda version: PAYLOAD)

        GameData.load(cache_dir=tmp_path)

        cached = json.loads((tmp_path / "items_v783.01.trimmed.json").read_text())
        assert sorted(cached) == ["tools", "units", "version"]


class TestModels:
    def test_hybrid_unit_is_allround(self):
        unit = UnitStats.model_validate({"wodID": 1, "role": "melee", "hybrid": "1"})
        assert unit.is_allround

    def test_tool_category_is_a_name_not_a_number(self):
        # Live values: Combo, Event, Premium, Basic, Elite.
        tool = ToolStats.model_validate({"wodID": 1, "slotTypes": "9", "toolCategory": "Basic"})
        assert tool.tool_category == "Basic"

    def test_delete_after_battle_keeps_its_value(self):
        # Live data uses 1 and 2, so this is not a boolean.
        assert ToolStats.model_validate({"wodID": 1, "deleteToolAfterBattle": "2"}).delete_after_battle == 2
        assert ToolStats.model_validate({"wodID": 1, "deleteToolAfterBattle": "2"}).is_consumed_in_battle
        assert not ToolStats.model_validate({"wodID": 1}).is_consumed_in_battle

    def test_tool_without_slot_types_has_none(self):
        tool = ToolStats.model_validate({"wodID": 1})
        assert tool.slot_types == ()
