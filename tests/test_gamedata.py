"""Game data loading: classification, coercion, caching."""

import json

import pytest

from empire_core.exceptions import NetworkError
from empire_core.gamedata import GameData, ToolStats, UnitStats, parse_ids, parse_stacks

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

        monkeypatch.setattr("empire_core.gamedata.data.get_items_version", lambda: "783.01")

        def fake_fetch(version):
            fetches.append(version)
            return PAYLOAD

        monkeypatch.setattr("empire_core.gamedata.data.fetch_items_data", fake_fetch)

        first = GameData.load(cache_dir=tmp_path)
        second = GameData.load(cache_dir=tmp_path)

        assert fetches == ["783.01"], "the second load must come from the cache"
        assert first.units.keys() == second.units.keys()
        assert second.get_unit(211).range_attack == 270

    def test_refresh_bypasses_the_cache(self, tmp_path, monkeypatch):
        fetches = []
        monkeypatch.setattr("empire_core.gamedata.data.get_items_version", lambda: "783.01")
        monkeypatch.setattr(
            "empire_core.gamedata.data.fetch_items_data",
            lambda version: (fetches.append(version), PAYLOAD)[1],
        )

        GameData.load(cache_dir=tmp_path)
        GameData.load(cache_dir=tmp_path, refresh=True)

        assert fetches == ["783.01", "783.01"]

    def test_new_version_invalidates_the_cache(self, tmp_path, monkeypatch):
        versions = iter(["783.01", "784.00"])
        fetches = []
        monkeypatch.setattr("empire_core.gamedata.data.get_items_version", lambda: next(versions))
        monkeypatch.setattr(
            "empire_core.gamedata.data.fetch_items_data",
            lambda version: (fetches.append(version), PAYLOAD)[1],
        )

        GameData.load(cache_dir=tmp_path)
        data = GameData.load(cache_dir=tmp_path)

        assert fetches == ["783.01", "784.00"]
        assert data.version == "784.00"

    def test_corrupt_cache_is_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr("empire_core.gamedata.data.get_items_version", lambda: "783.01")
        monkeypatch.setattr("empire_core.gamedata.data.fetch_items_data", lambda version: PAYLOAD)
        (tmp_path / "items_v783.01.trimmed.json").write_text("{not json")

        assert GameData.load(cache_dir=tmp_path).get_unit(211) is not None

    def test_unwritable_cache_still_loads(self, tmp_path, monkeypatch):
        monkeypatch.setattr("empire_core.gamedata.data.get_items_version", lambda: "783.01")
        monkeypatch.setattr("empire_core.gamedata.data.fetch_items_data", lambda version: PAYLOAD)
        blocker = tmp_path / "blocked"
        blocker.write_text("i am a file, not a directory")

        assert GameData.load(cache_dir=blocker / "sub").get_unit(211) is not None

    def test_version_failure_raises_network_error(self, tmp_path, monkeypatch):
        def boom():
            raise OSError("dns is having a day")

        monkeypatch.setattr("empire_core.gamedata.data.get_items_version", boom)

        with pytest.raises(NetworkError):
            GameData.load(cache_dir=tmp_path)

    def test_items_failure_raises_network_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("empire_core.gamedata.data.get_items_version", lambda: "783.01")

        def boom(version):
            raise OSError("connection reset")

        monkeypatch.setattr("empire_core.gamedata.data.fetch_items_data", boom)

        with pytest.raises(NetworkError):
            GameData.load(cache_dir=tmp_path)

    def test_cache_file_holds_only_the_trimmed_tables(self, tmp_path, monkeypatch):
        monkeypatch.setattr("empire_core.gamedata.data.get_items_version", lambda: "783.01")
        monkeypatch.setattr("empire_core.gamedata.data.fetch_items_data", lambda version: PAYLOAD)

        GameData.load(cache_dir=tmp_path)

        cached = json.loads((tmp_path / "items_v783.01.trimmed.json").read_text())
        # Trimmed: the combat tables only, never the whole payload.
        assert "version" in cached and "units" in cached and "tools" in cached
        assert "rewards" not in cached and "quests" not in cached


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


# Rows captured from the live payload.
EFFECT = {"effectID": "2101", "name": "relicOffensiveMeleeBonus", "effectTypeID": "23", "capID": "1001"}
EFFECT_TYPE = {"effectTypeID": "23", "name": "offensiveMeleeBonus"}
HORSE = {"wodID": 1001, "name": "Horse", "comment2": "Horse", "type": "1", "unitBoost": "6"}
DEFAULT_LORD = {"lordID": "-12", "type": "Treasuremap", "wearerID": "2"}
DUNGEON = {"countVictories": "-6", "kID": "0", "lordID": "-21", "unitsM": "604+3#606+3#652+45"}
NOMAD_CAMP = {
    "countVictory": "1",
    "defStrength": "150",
    "defenceUnits": "743,744",
    "defenceTools": "730,731",
    "wallBonus": "0",
    "gateBonus": "0",
    "lordID": "-21",
    "guards": "5",
}
FULL_PAYLOAD = {
    "units": [MEAD_RANGER, PREMIUM_STAKES, NOMAD_BOOST],
    "effects": [EFFECT],
    "effecttypes": [EFFECT_TYPE],
    "horses": [HORSE],
    "lords": [DEFAULT_LORD],
    "dungeons": [DUNGEON],
    "nomadCamps": [NOMAD_CAMP],
    "generalSkills": [{"skillID": "10110201", "effects": "400&10201"}],
    "rewards": [{"noise": "should not be stored"}],
}


class TestEncodings:
    def test_parse_stacks(self):
        assert parse_stacks("604+3#606+3#652+45") == [(604, 3), (606, 3), (652, 45)]

    def test_parse_stacks_tolerates_junk(self):
        assert parse_stacks("604+3##bad#606+2") == [(604, 3), (606, 2)]
        assert parse_stacks(None) == []

    def test_parse_ids(self):
        assert parse_ids("743,744") == (743, 744)
        assert parse_ids("") == ()


class TestCombatTables:
    def test_effects_resolve_to_their_type_name(self):
        data = GameData.parse("783.01", FULL_PAYLOAD)
        assert data.effect_type_name(2101) == "offensiveMeleeBonus"
        assert data.effect_type_name(999999) == ""

    def test_horses_are_indexed_by_hbw_value(self):
        horse = GameData.parse("783.01", FULL_PAYLOAD).get_horse(1001)
        assert horse is not None
        assert horse.unit_boost == 6

    def test_default_lords_explain_the_lid_sentinels(self):
        lord = GameData.parse("783.01", FULL_PAYLOAD).get_default_lord(-12)
        assert lord is not None
        assert lord.lord_type == "Treasuremap"

    def test_dungeon_defence_is_looked_up_by_victories(self):
        data = GameData.parse("783.01", FULL_PAYLOAD)

        row = data.dungeon_defence(-6, kingdom_id=0)

        assert row is not None
        assert row.units_middle == [(604, 3), (606, 3), (652, 45)]
        assert row.units_left == []
        assert row.total_units() == 51
        assert data.dungeon_defence(-6, kingdom_id=2) is None

    def test_camp_tables_share_one_shape(self):
        data = GameData.parse("783.01", FULL_PAYLOAD)

        camps = data.camps["nomadCamps"]

        assert [c.def_strength for c in camps] == [150]
        assert camps[0].defence_unit_ids == (743, 744)
        assert camps[0].defence_tool_ids == (730, 731)

    def test_general_skills_are_modelled_now(self):
        data = GameData.parse("783.01", FULL_PAYLOAD)

        assert data.general_skills[10110201].raw_effects == "400&10201"

    def test_unmodelled_tables_are_kept_raw(self):
        payload = dict(FULL_PAYLOAD, bossdungeons=[{"kID": "2", "countVictories": "-1"}])

        data = GameData.parse("783.01", payload)

        assert data.raw("bossdungeons")[0]["kID"] == "2"
        assert data.raw("nothing_here") == []

    def test_noise_tables_are_not_stored(self):
        data = GameData.parse("783.01", FULL_PAYLOAD)
        assert "rewards" not in data.raw_tables


class TestToolScalingRoundTrip:
    """Scaled values must survive the disk cache unchanged."""

    PAYLOAD = {
        "units": [
            {"wodID": 611, "name": "Workshop", "type": "Ram", "typ": "Attack", "slotTypes": "1,9", "gateBonus": "10"}
        ]
    }

    def test_a_percent_column_reads_as_a_fraction(self):
        tool = GameData.parse("test", self.PAYLOAD).get_tool(611)

        assert tool.raw_gate_bonus == 10
        assert tool.gate_bonus == 0.10

    def test_caching_does_not_rescale(self, tmp_path, monkeypatch):
        # Scaling inside a validator would divide by 100 again on every load,
        # because the cache stores whatever validation produced.
        monkeypatch.setattr("empire_core.gamedata.data.get_items_version", lambda: "1.0")
        monkeypatch.setattr("empire_core.gamedata.data.fetch_items_data", lambda version: self.PAYLOAD)

        first = GameData.load(cache_dir=tmp_path)
        second = GameData.load(cache_dir=tmp_path)

        assert first.get_tool(611).gate_bonus == 0.10
        assert second.get_tool(611).gate_bonus == 0.10
