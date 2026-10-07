"""Game data loading: classification, coercion, caching."""

import errno
import importlib.util
import json
import logging
import multiprocessing
import os
import sys
import threading
import time
import types
import uuid
from pathlib import Path
from typing import get_args, get_origin

import pytest
from pydantic import BaseModel

from empire_core.enums import Kingdom, ToolCategory, ToolSide, UnitRole
from empire_core.exceptions import AmbiguousLookupError, NetworkError
from empire_core.gamedata import (
    Effect,
    EffectValue,
    GameData,
    ToolStats,
    UnitStats,
    cache,
    cdn,
    parse_ids,
    parse_stacks,
)
from empire_core.gamedata import data as data_module
from empire_core.gamedata.troops import count_troops, get_troop_ids


def _recording_fetch(fetches: list[str]):
    """A fetch_items_data stand-in that notes which versions were asked for."""

    def fetch(version: str) -> dict:
        fetches.append(version)
        return PAYLOAD

    return fetch


def unit_of(data: GameData, wod_id: int) -> UnitStats:
    """The unit, insisting it is there - a missing row is a failure, not a None."""
    unit = data.get_unit(wod_id)
    assert unit is not None, f"no unit {wod_id} in the parsed data"
    return unit


def tool_of(data: GameData, wod_id: int) -> ToolStats:
    """The tool, insisting it is there."""
    tool = data.get_tool(wod_id)
    assert tool is not None, f"no tool {wod_id} in the parsed data"
    return tool


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
        assert (unit.range_attack, unit.melee_defense, unit.range_defense) == (270, 25, 42)
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
        assert tool.is_defense_tool

    def test_malformed_entry_does_not_lose_the_table(self):
        payload = {"units": [MEAD_RANGER, {"wodID": 5, "role": ["not", "a", "string"]}, {"junk": 1}]}

        data = GameData.parse("783.01", payload)

        assert set(data.units) == {211}

    def test_units_by_role(self):
        data = GameData.parse("783.01", PAYLOAD)
        assert [u.wod_id for u in data.units_by_role(UnitRole.RANGED)] == [211]
        assert data.units_by_role(UnitRole.MELEE) == []
        assert data.units[211].role is UnitRole.RANGED and data.units[211].is_ranged

    def test_fixed_text_columns_are_enums_and_a_new_value_is_kept(self, caplog):
        tool = ToolStats.model_validate({"wodID": 1, "typ": "Defence", "toolCategory": "COMBO", "slotTypes": "1"})
        with caplog.at_level(logging.WARNING):
            newer = ToolStats.model_validate({"wodID": 2, "typ": "Siege", "toolCategory": "Mythic"})

        assert (tool.category, tool.tool_category) == (ToolSide.DEFENCE, ToolCategory.COMBO)
        assert tool.is_defense_tool and not tool.is_attack_tool
        assert (newer.category, newer.tool_category) == ("Siege", "mythic")
        assert type(newer.category) is str and not caplog.records


class TestLoading:
    def test_load_writes_and_reuses_the_cache(self, tmp_path, monkeypatch):
        fetches: list[str] = []

        monkeypatch.setattr("empire_core.gamedata.cdn.get_items_version", lambda: "783.01")

        def fake_fetch(version):
            fetches.append(version)
            return PAYLOAD

        monkeypatch.setattr("empire_core.gamedata.cdn.fetch_items_data", fake_fetch)

        first = GameData.load(cache_dir=tmp_path)
        second = GameData.load(cache_dir=tmp_path)

        assert fetches == ["783.01"], "the second load must come from the cache"
        assert first.units.keys() == second.units.keys()
        assert unit_of(second, 211).range_attack == 270

    def test_refresh_bypasses_the_cache(self, tmp_path, monkeypatch):
        fetches: list[str] = []
        monkeypatch.setattr("empire_core.gamedata.cdn.get_items_version", lambda: "783.01")
        monkeypatch.setattr(
            "empire_core.gamedata.cdn.fetch_items_data",
            _recording_fetch(fetches),
        )

        GameData.load(cache_dir=tmp_path)
        GameData.load(cache_dir=tmp_path, refresh=True)

        assert fetches == ["783.01", "783.01"]

    def test_new_version_invalidates_the_cache(self, tmp_path, monkeypatch):
        versions = iter(["783.01", "784.00"])
        fetches: list[str] = []
        monkeypatch.setattr("empire_core.gamedata.cdn.get_items_version", lambda: next(versions))
        monkeypatch.setattr(
            "empire_core.gamedata.cdn.fetch_items_data",
            _recording_fetch(fetches),
        )

        GameData.load(cache_dir=tmp_path)
        data = GameData.load(cache_dir=tmp_path)

        assert fetches == ["783.01", "784.00"]
        assert data.version == "784.00"

    def test_corrupt_cache_is_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr("empire_core.gamedata.cdn.get_items_version", lambda: "783.01")
        monkeypatch.setattr("empire_core.gamedata.cdn.fetch_items_data", lambda version: PAYLOAD)
        (tmp_path / "items_v783.01.trimmed.json").write_text("{not json")

        assert GameData.load(cache_dir=tmp_path).get_unit(211) is not None

    def test_unwritable_cache_still_loads(self, tmp_path, monkeypatch):
        monkeypatch.setattr("empire_core.gamedata.cdn.get_items_version", lambda: "783.01")
        monkeypatch.setattr("empire_core.gamedata.cdn.fetch_items_data", lambda version: PAYLOAD)
        blocker = tmp_path / "blocked"
        blocker.write_text("i am a file, not a directory")

        assert GameData.load(cache_dir=blocker / "sub").get_unit(211) is not None

    def test_version_failure_raises_network_error(self, tmp_path, monkeypatch):
        def boom():
            raise OSError("dns is having a day")

        monkeypatch.setattr("empire_core.gamedata.cdn.get_items_version", boom)

        with pytest.raises(NetworkError):
            GameData.load(cache_dir=tmp_path)

    def test_items_failure_raises_network_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("empire_core.gamedata.cdn.get_items_version", lambda: "783.01")

        def boom(version):
            raise OSError("connection reset")

        monkeypatch.setattr("empire_core.gamedata.cdn.fetch_items_data", boom)

        with pytest.raises(NetworkError):
            GameData.load(cache_dir=tmp_path)

    def test_cache_file_holds_only_the_trimmed_tables(self, tmp_path, monkeypatch):
        monkeypatch.setattr("empire_core.gamedata.cdn.get_items_version", lambda: "783.01")
        monkeypatch.setattr("empire_core.gamedata.cdn.fetch_items_data", lambda version: PAYLOAD)

        GameData.load(cache_dir=tmp_path)

        cached = json.loads((tmp_path / "items_v783.01.trimmed.json").read_text())
        # Trimmed: the combat tables only, never the whole payload.
        assert "version" in cached and "units" in cached and "tools" in cached
        assert "rewards" not in cached and "mainquests" not in cached


def _marking_fetch(downloads: Path, delay: float = 0.0):
    """A fetch_items_data stand-in that leaves one file per download, so other processes are counted too."""

    def fetch(version: str) -> dict:
        downloads.mkdir(exist_ok=True)
        (downloads / uuid.uuid4().hex).touch()
        time.sleep(delay)
        return PAYLOAD

    return fetch


def _load_in_child(cache_dir: str) -> None:
    os._exit(0 if GameData.load(cache_dir=cache_dir).get_unit(211) is not None else 1)


class TestOneLoader:
    """GameData.load is the one items download and cache every reader shares."""

    @pytest.fixture
    def downloads(self, tmp_path, monkeypatch) -> Path:
        monkeypatch.setattr(cdn, "get_items_version", lambda: "783.01")
        monkeypatch.setattr(cdn, "fetch_items_data", _marking_fetch(tmp_path / "downloads", delay=0.05))
        return tmp_path / "downloads"

    def test_loading_and_counting_troops_download_once(self, downloads, tmp_path):
        loaded = GameData.load(cache_dir=tmp_path)

        assert count_troops({211: 4, 646: 2}) == 4
        assert get_troop_ids() == {211}
        assert GameData.load(cache_dir=tmp_path) is loaded
        assert len(list(downloads.iterdir())) == 1

    def test_troops_first_then_load_downloads_once(self, downloads):
        assert get_troop_ids() == {211}

        assert GameData.load() is GameData.loaded()
        assert len(list(downloads.iterdir())) == 1

    def test_a_new_process_reads_the_disk_cache(self, downloads, tmp_path, monkeypatch):
        GameData.load(cache_dir=tmp_path)
        monkeypatch.setattr(data_module, "_loaded", None)

        data = GameData.load(cache_dir=tmp_path)

        assert unit_of(data, 211).range_attack == 270
        assert len(list(downloads.iterdir())) == 1

    def test_a_version_change_downloads_again(self, downloads, tmp_path, monkeypatch):
        first = GameData.load(cache_dir=tmp_path)
        monkeypatch.setattr(cdn, "get_items_version", lambda: "784.00")

        second = GameData.load(cache_dir=tmp_path)

        assert (first.version, second.version) == ("783.01", "784.00")
        assert GameData.loaded() is second
        assert len(list(downloads.iterdir())) == 2
        assert {p.name for p in tmp_path.glob("*.json")} == {
            "items_v783.01.trimmed.json",
            "items_v784.00.trimmed.json",
        }

    def test_a_corrupt_cache_is_downloaded_and_rewritten(self, downloads, tmp_path):
        cache_file = tmp_path / "items_v783.01.trimmed.json"
        cache_file.write_text('{"version": "783.01", "units": {')

        assert GameData.load(cache_dir=tmp_path).get_unit(211) is not None
        assert json.loads(cache_file.read_text())["version"] == "783.01"
        assert len(list(downloads.iterdir())) == 1

    def test_concurrent_threads_share_one_download(self, downloads, tmp_path):
        results: list[GameData] = []
        threads = [threading.Thread(target=lambda: results.append(GameData.load(cache_dir=tmp_path))) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(results) == 6
        assert all(r is results[0] for r in results)
        assert len(list(downloads.iterdir())) == 1

    @pytest.mark.skipif(sys.platform != "linux", reason="forks a process holding threads")
    def test_concurrent_processes_share_one_download(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cdn, "get_items_version", lambda: "783.01")
        monkeypatch.setattr(cdn, "fetch_items_data", _marking_fetch(tmp_path / "downloads", delay=0.3))
        fork = multiprocessing.get_context("fork")
        children = [fork.Process(target=_load_in_child, args=(str(tmp_path / "cache"),)) for _ in range(4)]
        for child in children:
            child.start()
        for child in children:
            child.join(timeout=30)

        assert [child.exitcode for child in children] == [0] * 4
        assert len(list((tmp_path / "downloads").iterdir())) == 1
        assert [p.name for p in (tmp_path / "cache").iterdir() if p.suffix == ".tmp"] == []

    def test_a_failure_backs_off_and_refresh_retries(self, tmp_path, monkeypatch):
        calls: list[str] = []

        def version() -> str:
            calls.append("version")
            return "783.01"

        def boom(version):
            raise OSError("connection reset")

        monkeypatch.setattr(cdn, "get_items_version", version)
        monkeypatch.setattr(cdn, "fetch_items_data", boom)
        with pytest.raises(NetworkError):
            GameData.load(cache_dir=tmp_path)
        with pytest.raises(NetworkError, match="not retried yet"):
            GameData.load(cache_dir=tmp_path)
        assert calls == ["version"]

        monkeypatch.setattr(cdn, "fetch_items_data", lambda version: PAYLOAD)
        assert GameData.load(cache_dir=tmp_path, refresh=True).get_unit(211) is not None

    def test_the_backoff_ends(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cdn, "get_items_version", lambda: "783.01")
        monkeypatch.setattr(cdn, "fetch_items_data", lambda version: PAYLOAD)
        monkeypatch.setattr(data_module, "_failed_at", time.monotonic() - cdn.RETRY_AFTER_FAILURE - 1)

        assert GameData.load(cache_dir=tmp_path).get_unit(211) is not None
        assert data_module._failed_at is None

    def test_the_loaded_data_outlives_a_failed_version_check(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cdn, "get_items_version", lambda: "783.01")
        monkeypatch.setattr(cdn, "fetch_items_data", lambda version: PAYLOAD)
        loaded = GameData.load(cache_dir=tmp_path)
        calls: list[str] = []

        def boom() -> str:
            calls.append("version")
            raise OSError("dns is having a day")

        monkeypatch.setattr(cdn, "get_items_version", boom)

        assert GameData.load(cache_dir=tmp_path) is loaded
        assert GameData.load(cache_dir=tmp_path) is loaded
        assert calls == ["version"]

    def test_the_loaded_data_outlives_a_failed_download_of_a_new_version(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cdn, "get_items_version", lambda: "783.01")
        monkeypatch.setattr(cdn, "fetch_items_data", lambda version: PAYLOAD)
        loaded = GameData.load(cache_dir=tmp_path)

        def boom(version):
            raise OSError("connection reset")

        monkeypatch.setattr(cdn, "get_items_version", lambda: "784.00")
        monkeypatch.setattr(cdn, "fetch_items_data", boom)

        assert GameData.load(cache_dir=tmp_path) is loaded
        assert GameData.loaded() is loaded

    def test_refresh_raises_even_with_data_loaded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cdn, "get_items_version", lambda: "783.01")
        monkeypatch.setattr(cdn, "fetch_items_data", lambda version: PAYLOAD)
        GameData.load(cache_dir=tmp_path)

        def boom(version):
            raise OSError("connection reset")

        monkeypatch.setattr(cdn, "fetch_items_data", boom)

        with pytest.raises(NetworkError):
            GameData.load(cache_dir=tmp_path, refresh=True)

    def test_the_version_is_fetched_outside_the_load_lock(self, tmp_path, monkeypatch):
        asked = threading.Event()

        def version() -> str:
            asked.set()
            return "783.01"

        monkeypatch.setattr(cdn, "get_items_version", version)
        monkeypatch.setattr(cdn, "fetch_items_data", lambda version: PAYLOAD)
        with data_module._load_lock:
            loader = threading.Thread(target=GameData.load, kwargs={"cache_dir": tmp_path})
            loader.start()
            assert asked.wait(timeout=5)
        loader.join(timeout=5)

        assert GameData.loaded() is not None

    def test_a_version_that_is_not_dotted_digits_is_refused(self, tmp_path, monkeypatch):
        class Response:
            text = "itemsVersion=../../outside\n"

            def raise_for_status(self) -> None:
                pass

        monkeypatch.setattr(cdn.requests, "get", lambda url, timeout: Response())

        with pytest.raises(ValueError):
            cdn.get_items_version()
        with pytest.raises(NetworkError):
            GameData.load(cache_dir=tmp_path / "cache")
        assert not (tmp_path / "cache").exists()

    def test_the_version_is_the_text_after_the_first_equals(self, monkeypatch):
        class Response:
            text = "itemsVersion=786.03\n"

            def raise_for_status(self) -> None:
                pass

        monkeypatch.setattr(cdn.requests, "get", lambda url, timeout: Response())

        assert cdn.get_items_version() == "786.03"


class TestCacheLock:
    def test_a_filesystem_without_locks_still_loads(self, tmp_path, monkeypatch):
        def no_locks(fd: int) -> None:
            raise OSError("ENOLCK")

        monkeypatch.setattr(cache, "_acquire", no_locks)
        monkeypatch.setattr(cdn, "get_items_version", lambda: "783.01")
        monkeypatch.setattr(cdn, "fetch_items_data", lambda version: PAYLOAD)

        assert GameData.load(cache_dir=tmp_path).get_unit(211) is not None
        assert (tmp_path / "items_v783.01.trimmed.json").is_file()


def _cache_on_windows(monkeypatch, locking) -> types.ModuleType:
    """A separate copy of the cache module as Windows loads it, with ``msvcrt.locking`` replaced."""
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(LK_LOCK=1, LK_UNLCK=0, locking=locking))
    monkeypatch.setattr(sys, "platform", "win32")
    spec = importlib.util.spec_from_file_location("_cache_on_windows", cache.__file__)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestWindowsLock:
    def test_a_lock_still_held_is_waited_for(self, monkeypatch):
        attempts: list[int] = []

        def locking(fd: int, mode: int, size: int) -> None:
            attempts.append(mode)
            if len(attempts) < 3:
                raise OSError(errno.EDEADLK, "Resource deadlock avoided")

        windows = _cache_on_windows(monkeypatch, locking)
        windows._acquire(5)

        assert attempts == [1, 1, 1]

    def test_any_other_error_loads_without_the_lock(self, tmp_path, monkeypatch):
        attempts: list[int] = []

        def locking(fd: int, mode: int, size: int) -> None:
            attempts.append(mode)
            raise OSError(errno.EACCES, "Permission denied")

        windows = _cache_on_windows(monkeypatch, locking)
        with pytest.raises(OSError):
            windows._acquire(5)
        ran = False
        with windows.locked(tmp_path / "items.lock"):
            ran = True

        assert ran and attempts == [1, 1]


class TestWriteAtomic:
    def test_replaces_the_file_and_leaves_no_temp(self, tmp_path):
        target = tmp_path / "sub" / "items.json"
        cache.write_atomic(target, "old")
        cache.write_atomic(target, "new")

        assert target.read_text() == "new"
        assert [p.name for p in target.parent.iterdir()] == ["items.json"]

    def test_a_failed_write_keeps_the_old_file(self, tmp_path, monkeypatch):
        target = tmp_path / "items.json"
        target.write_text("old")

        def broken_replace(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr(cache.os, "replace", broken_replace)
        with pytest.raises(OSError):
            cache.write_atomic(target, "new")

        assert target.read_text() == "old"
        assert [p.name for p in tmp_path.iterdir()] == ["items.json"]


class TestModels:
    def test_hybrid_unit_is_allround(self):
        unit = UnitStats.model_validate({"wodID": 1, "role": "melee", "hybrid": "1"})
        assert unit.is_allround

    def test_tool_category_is_lowercased_as_the_client_stores_it(self):
        # Live values: Combo, Event, Premium, Basic, Elite.
        # BasicUnitVO.parseXmlNode: getStringAttribute("toolCategory", t).toLowerCase()
        tool = ToolStats.model_validate({"wodID": 1, "slotTypes": "9", "toolCategory": "Basic"})
        assert tool.tool_category == "basic"
        assert ToolStats.model_validate({"wodID": 1}).tool_category == ""

    def test_a_row_without_a_level_reads_minus_one(self):
        # BasicUnitVO.parseXmlNode: parseInt(getValueOrDefault("level", t, "-1"))
        assert UnitStats.model_validate({"wodID": 1}).level == -1
        assert UnitStats.model_validate({"wodID": 1, "level": ""}).level == -1
        assert UnitStats.model_validate({"wodID": 1, "level": "0"}).level == 0
        assert ToolStats.model_validate({"wodID": 1}).level == -1

    def test_unit_defaults_are_the_clients(self):
        unit = UnitStats.model_validate({"wodID": 1})

        assert (unit.unit_type, unit.role, unit.source) == ("", "", "")
        assert (unit.speed, unit.fight_type, unit.loot_value, unit.food_supply) == (0, 0, 0, 0)
        assert not unit.hybrid

    def test_tool_defaults_are_the_clients(self):
        tool = ToolStats.model_validate({"wodID": 1})

        # String(getValueOrDefault("typ", t, "0", true))
        assert tool.category == "0"
        assert (tool.amount_per_wave, tool.speed, tool.raw_wall_bonus) == (-1, 0, 0)
        assert tool.can_attack_npc

    def test_int_columns_read_with_parse_int(self):
        unit = UnitStats.model_validate(
            {"wodID": "211x", "level": "6.9", "meleeAttack": "12abc", "rangeDefence": "nope", "lootValue": " 52"}
        )

        assert (unit.wod_id, unit.level, unit.melee_attack, unit.loot_value) == (211, 6, 12, 52)
        # NaN to the client; the column's default here.
        assert unit.range_defense == 0
        tool = ToolStats.model_validate({"wodID": 1, "wallBonus": "12.5", "amountPerWave": "x"})
        assert (tool.raw_wall_bonus, tool.amount_per_wave) == (12, -1)

    def test_a_row_without_a_numeric_id_is_skipped(self):
        data = GameData.parse("1.0", {"units": [MEAD_RANGER, {"wodID": "x", "name": "Barracks"}, {"wodID": ""}]})

        assert set(data.units) == {211}

    def test_flags_are_true_only_for_one(self):
        # 1 == parseInt(...): any other number is false.
        assert UnitStats.model_validate({"wodID": 1, "hybrid": "1"}).hybrid
        assert not UnitStats.model_validate({"wodID": 1, "hybrid": "2"}).hybrid
        assert not ToolStats.model_validate({"wodID": 1, "canBeUsedToAttackNPC": "0"}).can_attack_npc
        assert not ToolStats.model_validate({"wodID": 1, "canBeUsedToAttackNPC": "2"}).can_attack_npc
        assert ToolStats.model_validate({"wodID": 1, "canBeUsedToAttackNPC": ""}).can_attack_npc

    def test_a_dash_type_reads_as_no_type(self):
        # AVisualVO.parseXmlNode: "-" == this._type && (this._type = "")
        assert UnitStats.model_validate({"wodID": 1, "type": "-"}).unit_type == ""
        assert ToolStats.model_validate({"wodID": 1, "type": "-"}).tool_type == ""

    def test_unparsed_columns_are_not_modeled(self):
        # Nothing in the unit or tool parsers reads these.
        assert "might_value" not in UnitStats.model_fields
        assert "delete_after_battle" not in ToolStats.model_fields

    def test_allowed_targets_keep_nan_pairs_as_a_restriction(self):
        # parseSpaceIdAreaTypeValues pushes NaN pairs; checkIfTargetIsInArray matches none of them.
        tool = ToolStats.model_validate({"wodID": 1, "allowedToAttack": "x+21"})

        assert tool.allowed_targets == ((None, 21),)
        assert not tool.is_allowed_by_attack_target(0, 21)
        extra = ToolStats.model_validate({"wodID": 1, "allowedToAttack": "0+21+5#1+-1"})
        assert extra.allowed_targets == ((0, 21), (1, -1))
        assert extra.is_allowed_by_attack_target(1, 7)

    def test_tool_effects_are_typed_effect_values(self):
        tool = ToolStats.model_validate({"wodID": 1, "effects": "632&275,504&1"})
        assert tool.effects == (
            EffectValue(effect_id=Effect.KILL_DEFENDING_MELEE_TROOPS_YARD, values=((275,),)),
            EffectValue(effect_id=Effect.ATTACK_BOOST_YARD, values=((1,),)),
        )
        assert ToolStats.model_validate({"wodID": 1}).effects == ()

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

    def test_horse_rows_read_what_the_travel_booster_reads(self):
        # HorseTravelboosterVO.parseXmlNode: parseInt boosts, Number cost factors, !!parseInt(isInstantSpyHorse)
        row = {"wodID": 1003, "name": "Horse", "group": "Travelbooster", "type": "3", "unitBoost": "16",
               "marketBoost": "27", "spyBoost": "27", "costFactorC1": "0", "costFactorC2": "2.1",
               "isInstantSpyHorse": "1"}  # fmt: skip
        horse = GameData.parse("783.01", {"horses": [row]}).get_horse(1003)

        assert horse is not None
        assert (horse.group, horse.horse_type, horse.unit_boost, horse.market_boost, horse.spy_boost) == (
            "Travelbooster", "3", 16, 27, 27
        )  # fmt: skip
        assert (horse.cost_factor_c1, horse.cost_factor_c2, horse.is_instant_spy_horse) == (0, 2.1, True)

    def test_horse_columns_left_out_read_as_the_client_reads_them(self):
        horse = GameData.parse("783.01", {"horses": [{"wodID": 1001, "unitBoost": "6.9x", "type": "-"}]}).get_horse(
            1001
        )

        assert horse is not None
        assert (horse.unit_boost, horse.spy_boost, horse.horse_type) == (6, 0, "")
        assert (horse.cost_factor_c1, horse.cost_factor_c2, horse.is_instant_spy_horse) == (0, 0, False)

    def test_default_lords_explain_the_lid_sentinels(self):
        lord = GameData.parse("783.01", FULL_PAYLOAD).get_default_lord(-12)
        assert lord is not None
        assert lord.lord_type == "Treasuremap"

    def test_vip_levels_give_their_free_premium_commanders(self):
        rows = [
            {"vipLevelID": "1", "thresholdMin": "0", "thresholdMax": "299", "bonusLoginKeys": "1"},
            {"vipLevelID": "5", "thresholdMin": "8000", "thresholdMax": "19999", "freePremiumGeneralsPerDay": "25"},
        ]
        data = GameData.parse("786.03", {"viplevels": rows})

        assert [(level.vip_level_id, level.free_premium_commanders_per_day) for level in data.vip_levels.values()] == [
            (1, 0),
            (5, 25),
        ]

    @pytest.mark.parametrize(
        ("points", "level_id"), [(0, 1), (299, 1), (8000, 5), (19999, 5), (500, 5), (900000, 5), (-1, None)]
    )
    def test_vip_level_by_points(self, points: int, level_id: int | None):
        # CastleVIPData.getVIPLevelInfoVOByPoints: the level in range, else the top one above 0 points
        rows = [
            {"vipLevelID": "5", "thresholdMin": "8000", "thresholdMax": "19999"},
            {"vipLevelID": "1", "thresholdMin": "0", "thresholdMax": "299"},
        ]
        level = GameData.parse("786.03", {"viplevels": rows}).vip_level(points)

        assert (level.vip_level_id if level is not None else None) == level_id

    def test_dungeon_defense_is_looked_up_by_victories(self):
        data = GameData.parse("783.01", FULL_PAYLOAD)

        row = data.dungeon_defense(-6, kingdom_id=Kingdom.GREEN)

        assert row is not None
        assert row.units_middle == [(604, 3), (606, 3), (652, 45)]
        assert row.units_left == []
        assert row.total_units() == 51
        assert data.dungeon_defense(-6, kingdom_id=Kingdom.ICE) is None

    def test_camp_tables_share_one_shape(self):
        data = GameData.parse("783.01", FULL_PAYLOAD)

        camps = data.camps["nomadCamps"]

        assert [c.def_strength for c in camps] == [150]
        assert camps[0].defense_unit_ids == (743, 744)
        assert camps[0].defense_tool_ids == (730, 731)

    def test_general_skills_are_modeled_now(self):
        data = GameData.parse("783.01", FULL_PAYLOAD)

        assert data.general_skills[10110201].effects == (EffectValue(effect_id=400, values=((10201,),)),)

    def test_gems_are_keyed_by_gem_id(self):
        payload = dict(
            FULL_PAYLOAD,
            gems=[
                {
                    "gemID": "333",
                    "gemLevelID": "0",
                    "wearerID": "2",
                    "setID": "38",
                    "triggerChance": "100",
                    "effects": "504&20,55&15",
                },
                {"gemID": "334", "gemLevelID": "0", "effects": "33&5"},
                {"gemLevelID": "0", "effects": "33&5"},
            ],
        )

        gems = GameData.parse("783.01", payload).gems

        assert sorted(gems) == [333, 334]
        assert (gems[333].set_id, gems[333].trigger_chance) == (38, 100)
        assert [(e.effect_id, e.value) for e in gems[333].effects] == [(504, 20), (55, 15)]
        # CastleGemVO.parseXML defaults: no set, always triggers.
        assert (gems[334].set_id, gems[334].trigger_chance) == (-1, 100)

    def test_unmodeled_tables_are_kept_raw(self):
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
        tool = tool_of(GameData.parse("test", self.PAYLOAD), 611)

        assert tool.raw_gate_bonus == 10
        assert tool.gate_bonus == 0.10

    def test_caching_does_not_rescale(self, tmp_path, monkeypatch):
        # Scaling inside a validator would divide by 100 again on every load,
        # because the cache stores whatever validation produced.
        monkeypatch.setattr("empire_core.gamedata.cdn.get_items_version", lambda: "1.0")
        monkeypatch.setattr("empire_core.gamedata.cdn.fetch_items_data", lambda version: self.PAYLOAD)

        first = GameData.load(cache_dir=tmp_path)
        second = GameData.load(cache_dir=tmp_path)

        assert tool_of(first, 611).gate_bonus == 0.10
        assert tool_of(second, 611).gate_bonus == 0.10


class TestCacheSchemaFingerprint:
    """A cache written against older tables must not be reused."""

    def test_a_parse_stamps_the_current_fingerprint(self):
        from empire_core.gamedata.data import _schema_fingerprint

        data = GameData.parse("1.0", {"units": []})

        assert data.schema_fingerprint == _schema_fingerprint()

    def test_a_stale_cache_is_ignored(self, tmp_path):
        data = GameData.parse("1.0", {"units": [{"wodID": 1, "name": "Barracks", "role": "melee"}]})
        cache = tmp_path / "items_v1.0.trimmed.json"
        cache.write_text(data.model_dump_json())

        assert GameData._read_cache(cache, "1.0") is not None

        # A cache from a model that had fewer columns.
        stale = data.model_dump()
        stale["schema_fingerprint"] = "0" * 12
        cache.write_text(json.dumps(stale))

        assert GameData._read_cache(cache, "1.0") is None

    def test_a_cache_without_a_fingerprint_is_ignored(self, tmp_path):
        # Every cache written before this existed.
        data = GameData.parse("1.0", {"units": []})
        payload = data.model_dump()
        payload.pop("schema_fingerprint")
        cache = tmp_path / "items_v1.0.trimmed.json"
        cache.write_text(json.dumps(payload))

        assert GameData._read_cache(cache, "1.0") is None

    def test_parsed_values_survive_the_cache(self, tmp_path):
        payload = {
            "units": [
                {"wodID": 1, "name": "Barracks", "role": "melee", "hybrid": "1"},
                {
                    "wodID": 2,
                    "name": "Workshop",
                    "slotTypes": "1",
                    "canBeUsedToAttackNPC": "0",
                    "toolCategory": "Basic",
                },
            ]
        }
        cache = tmp_path / "items_v1.0.trimmed.json"
        GameData.parse("1.0", payload)._write_cache(cache)

        cached = GameData._read_cache(cache, "1.0")

        assert cached is not None
        assert cached.units[1].hybrid and cached.units[1].level == -1
        assert not cached.tools[2].can_attack_npc
        assert (cached.tools[2].tool_category, cached.tools[2].category) == ("basic", "0")

    def test_the_fingerprint_covers_defaults(self, monkeypatch):
        from empire_core.gamedata.data import _schema_fingerprint

        before = _schema_fingerprint()
        monkeypatch.setattr(UnitStats.model_fields["level"], "default", 0)

        assert _schema_fingerprint() != before

    def test_the_fingerprint_covers_the_tool_columns(self):
        # The columns that caused this: a cache predating them read them as
        # their defaults and quietly widened the tool pool.
        from empire_core.gamedata.data import _schema_fingerprint

        assert "raw_allowed_to_attack" in ToolStats.model_fields
        assert "can_attack_npc" in ToolStats.model_fields
        before = _schema_fingerprint()
        assert len(before) == 12


# Rows as the items payload has them, from v786.03.
LOOKUP_PAYLOAD = {
    "units": [
        MEAD_RANGER,
        {**MEAD_RANGER, "wodID": 212, "level": "7"},
        {"wodID": 68, "name": "Eventunit", "type": "Ogermace", "role": "melee", "eventIDs": "64"},
        {"wodID": 7, "name": "Eventunit", "type": "Ogermace", "role": "melee"},
        {"wodID": 113, "name": "Elitetool", "type": "EliteComboRam", "typ": "Attack", "slotTypes": "1"},
        {"wodID": 564, "name": "Eventtool", "type": "EliteComboRam", "typ": "Attack", "slotTypes": "1"},
        {**PREMIUM_STAKES, "level": "2"},
    ],
    "generals": [
        {"generalID": "101", "generalName": "Toril", "generalRarityID": "4", "attackSlots": "101011", "maxLevel": "100"}
    ],
    "generalAbilities": [
        {
            "abilityID": "10011",
            "name": "PowerSurge",
            "abilityGroupID": "1001",
            "level": "1",
            "abilityTriggerID": "2",
            "triggerPerWave": "2",
            "abilityAttackEffectID": "100110",
            "abilityDefenseEffectID": "100115",
            "affectsEnemyArmy": "0",
        },
        {"abilityID": "10012", "name": "PowerSurge", "abilityGroupID": "1001", "level": "2"},
    ],
    "generalSkills": [
        {"skillID": "10110201", "name": "AspectoftheDragon", "generalID": "101", "level": "1", "effects": "400&10201"},
        {"skillID": "10110202", "name": "AspectoftheDragon", "generalID": "101", "level": "2"},
        {"skillID": "10210201", "name": "AspectoftheDragon", "generalID": "102", "level": "1"},
    ],
    "legendskills": [
        {"skillID": "1", "level": "1", "skillTreeID": "0", "skillGroupID": "1", "effectType": "gateReduction"},
        {"skillID": "2", "level": "2", "skillTreeID": "0", "skillGroupID": "1", "effectType": "gateReduction"},
    ],
    "currencies": [
        {"currencyID": "1", "Name": "KhanTablet", "JSONKey": "KT", "assetName": "KhanTablet"},
        {"currencyID": "100000", "Name": "DecoDust", "JSONKey": "DD", "assetName": "DecoDust"},
    ],
    "effecttypes": [{"effectTypeID": "0", "sortCategory": "6", "sortGroup": "9", "name": "fameDefenseBonus"}],
    "raidBosses": [{"raidBossID": "1", "rarity": "2", "name": "Necromancer", "leaguetypeID": "1"}],
    "globalEffects": [
        {"globalEffectID": "1", "name": "CooldownReductionRBC", "effects": "425&50", "boostValue": "50"},
        {"globalEffectID": "2", "name": "SpeedBoost", "effects": "426&60", "boostValue": "60"},
        {"globalEffectID": "11", "name": "SpeedBoost", "effects": "426&1000", "boostValue": "1000"},
    ],
}


class TestNamedLookups:
    @pytest.fixture
    def data(self) -> GameData:
        return GameData.parse("786.03", LOOKUP_PAYLOAD)

    def test_new_tables_are_parsed(self, data):
        assert data.currencies[1].json_key == "KT"
        assert data.currencies[100000].name == "DecoDust"
        ability = data.general_abilities[10011]
        assert (ability.ability_group_id, ability.ability_trigger_id, ability.trigger_per_wave) == (1001, 2, 2)
        assert (ability.ability_attack_effect_id, ability.ability_defense_effect_id) == (100110, 100115)
        assert data.general_abilities[10012].ability_trigger_id == 0
        assert (data.raid_bosses[1].name, data.raid_bosses[1].rarity) == ("Necromancer", 2)

    def test_hits(self, data):
        assert data.general("Toril").general_id == 101
        assert data.general_ability("PowerSurge", 2).ability_id == 10012
        assert data.general_skill(101, "AspectoftheDragon", 2).skill_id == 10110202
        assert data.general_skill(102, "AspectoftheDragon", 1).skill_id == 10210201
        assert data.legend_skill(0, 1, 2).skill_id == 2
        assert data.currency("KT").currency_id == 1
        assert data.effect_type("fameDefenseBonus").effect_type_id == 0
        assert data.raid_boss("Necromancer").raid_boss_id == 1
        assert data.global_effect("CooldownReductionRBC").global_effect_id == 1
        assert data.unit("MeadRanger", 7).wod_id == 212
        assert data.tool("Premiumstakes").wod_id == 646
        assert data.tool("Premiumstakes", 2).level == 2

    def test_misses_return_none(self, data):
        assert data.general("toril") is None
        assert data.general_ability("PowerSurge", 3) is None
        assert data.general_skill(103, "AspectoftheDragon", 1) is None
        assert data.legend_skill(1, 1, 1) is None
        assert data.currency("C1") is None
        assert data.effect_type("nope") is None
        assert data.raid_boss("nope") is None
        assert data.global_effect("nope") is None
        assert data.unit("MeadRanger", 9) is None
        assert data.tool("Premiumstakes", 3) is None

    def test_speed_boost_is_ambiguous(self, data):
        with pytest.raises(AmbiguousLookupError) as caught:
            data.global_effect("SpeedBoost")

        assert caught.value.ids == [2, 11]
        assert isinstance(caught.value, LookupError)

    def test_a_unit_type_across_levels_needs_a_level(self, data):
        with pytest.raises(AmbiguousLookupError) as caught:
            data.unit("MeadRanger")

        assert caught.value.ids == [211, 212]

    def test_event_variants_without_a_level_are_ambiguous(self, data):
        with pytest.raises(AmbiguousLookupError) as caught:
            data.unit("Ogermace")
        assert caught.value.ids == [7, 68]

        with pytest.raises(AmbiguousLookupError) as caught:
            data.tool("EliteComboRam")
        assert caught.value.ids == [113, 564]

    def test_a_tool_without_a_level_reads_minus_one(self, data):
        # BasicUnitVO.parseXmlNode: getValueOrDefault("level", t, "-1")
        assert data.get_tool(113).level == -1

    def test_level_zero_and_no_level_are_different_rows(self):
        # v786.03 has Renegadepiratemelee at levels 0, 1 and 2 and once with no level.
        pirates = [
            {"wodID": wod_id, "name": "Eventunit", "type": "Renegadepiratemelee", "role": "melee", **level}
            for wod_id, level in ((759, {"level": "0"}), (760, {"level": "1"}), (962, {}))
        ]
        data = GameData.parse("786.03", {"units": pirates})

        level_zero = data.unit("Renegadepiratemelee", 0)
        no_level = data.unit("Renegadepiratemelee", -1)
        assert level_zero is not None and level_zero.wod_id == 759
        assert no_level is not None and no_level.wod_id == 962

    def test_the_new_tables_survive_the_cache(self, data, tmp_path):
        cache = tmp_path / "items_v786.03.trimmed.json"
        data._write_cache(cache)

        cached = GameData._read_cache(cache, "786.03")

        assert cached is not None
        currency = cached.currency("DD")
        ability = cached.general_ability("PowerSurge", 1)
        boss = cached.raid_boss("Necromancer")
        assert currency is not None and currency.currency_id == 100000
        assert ability is not None and ability.ability_id == 10011
        assert boss is not None and boss.raid_boss_id == 1

    def test_the_fingerprint_covers_every_cached_table(self):
        from empire_core.gamedata.data import _CACHED_MODELS

        def row_models(annotation) -> set[type]:
            if get_origin(annotation) is None and isinstance(annotation, type) and issubclass(annotation, BaseModel):
                nested = {model for field in annotation.model_fields.values() for model in row_models(field.annotation)}
                return {annotation, *nested}
            return {model for arg in get_args(annotation) for model in row_models(arg)}

        cached = {model for field in GameData.model_fields.values() for model in row_models(field.annotation)}

        assert cached == set(_CACHED_MODELS)


def test_falsy_values_take_the_client_default():
    # CastleXMLUtils.getValueOrDefault returns the default for any falsy value, 0 included
    from empire_core.gamedata.models import CurrencyDef, GeneralAbilityDef, ToolStats, UnitStats

    assert UnitStats.model_validate({"wodID": 1, "level": 0}).level == -1
    assert ToolStats.model_validate({"wodID": 2, "slotTypes": "1", "canBeUsedToAttackNPC": 0}).can_attack_npc is True
    assert GeneralAbilityDef.model_validate({"abilityID": "12abc"}).ability_id == 12
    assert CurrencyDef.model_validate({"currencyID": None}).currency_id == -1


def test_a_cached_level_of_zero_stays_zero(tmp_path):
    # The cache holds parsed ints, so 0 is a real level there, not a missing one
    from empire_core.gamedata import GameData

    data = GameData.parse("9.9", {"units": [{"wodID": "205", "type": "MeadRanger", "level": "0"}]})
    assert data.units[205].level == 0
    cache = tmp_path / "items.json"
    data._write_cache(cache)
    again = GameData._read_cache(cache, "9.9")
    assert again is not None and again.units[205].level == 0


class TestLeagueTypes:
    # Rows of v786.03's leaguetypes table, as the payload has them
    ROWS = [
        {"comment2": "platin", "leaguetypeID": "6", "eventID": "-1", "minLevel": 70, "maxLevel": "1020"},
        {"leaguetypeID": "1", "eventID": "71", "minLevel": 20, "maxLevel": "69"},
        {"leaguetypeID": "1", "eventID": "71", "subType": "1", "minLevel": 70, "maxLevel": "1020"},
        {"leaguetypeID": "1", "eventID": "80", "minLevel": 10, "maxLevel": "69", "countVictoryMin": "16"},
    ]

    @pytest.fixture
    def data(self) -> GameData:
        return GameData.parse("786.03", {"leaguetypes": self.ROWS})

    def test_a_league_is_keyed_by_event_and_sub_type(self, data):
        leagues = {
            "no event": data.league_type(6),
            "event": data.league_type(1, 71),
            "sub type": data.league_type(1, 71, sub_type=1),
            "other event": data.league_type(1, 80),
        }
        levels = {key: (row.min_level, row.max_level) for key, row in leagues.items() if row is not None}
        assert levels == {"no event": (70, 1020), "event": (20, 69), "sub type": (70, 1020), "other event": (10, 69)}

    def test_misses_return_none(self, data):
        assert data.league_type(1) is None
        assert data.league_type(2, 71) is None
        assert data.league_type(1, 71, sub_type=2) is None

    def test_values_are_read_with_parse_int(self):
        data = GameData.parse("786.03", {"leaguetypes": [{"leaguetypeID": "3x", "eventID": "-1", "maxLevel": "9"}]})
        league = data.league_type(3)
        assert league is not None and (league.event_id, league.sub_type, league.max_level) == (-1, 0, 9)

    def test_a_row_without_an_event_matches_no_event(self):
        # AScoreEventVO.generateLeagueLevelsList: parseInt(o.eventID || "") is NaN
        data = GameData.parse("786.03", {"leaguetypes": [{"leaguetypeID": "3", "eventID": ""}]})
        assert data.league_type(3) is None
        assert data.league_brackets[0].event_id is None

    def test_leagues_survive_the_cache(self, data, tmp_path):
        cache = tmp_path / "items_v786.03.trimmed.json"
        data._write_cache(cache)

        cached = GameData._read_cache(cache, "786.03")

        assert cached is not None
        league = cached.league_type(1, 80)
        assert league is not None and (league.min_level, league.max_level, league.victory_min) == (10, 69, 16)

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
    def test_the_file_gets_the_umask_permissions(self, tmp_path):
        previous = os.umask(0o027)
        try:
            cache.write_atomic(tmp_path / "items.json", "{}")
        finally:
            os.umask(previous)

        assert (tmp_path / "items.json").stat().st_mode & 0o777 == 0o640
