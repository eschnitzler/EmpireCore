"""Synthetic ItemVersions fixtures; no client downloads or game connections."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from empire_core.exceptions import NetworkError
from empire_core.gamedata import GameData, assets

UNIT_PATH = "itemassets/Units/Barracks/Barracks_Unit_Test/Barracks_Unit_Test--123"
TOOL_PATH = "itemassets/Units/Workshop/Workshop_Unit_Test/Workshop_Unit_Test--456"
FALLBACK_PATH = "itemassets/Units/Unknown/Unknown_Unit_Tools/Unknown_Unit_Tools--789"
VERSION = "0123456789abcdef01234"
INDEX_HTML = f'<link id="dll" href="dll/ggs.dll.{VERSION}.js"><script src="dll/ggs.dll.{VERSION}.js"></script>'
JAVASCRIPT = (
    "ItemVersions.prototype.fill=function(){"
    f'this.assets.Barracks_Unit_Test="{UNIT_PATH}",'
    f'this.assets.Workshop_Unit_Test="{TOOL_PATH}",'
    f'this.assets.Unknown_Unit_Tools="{FALLBACK_PATH}"'
    "},ItemVersions}();t.ItemVersions=i"
)


@pytest.fixture
def data() -> GameData:
    return GameData.parse(
        "1",
        {
            "units": [
                {"wodID": "1", "name": "Barracks", "group": "Unit", "type": "Test"},
                {"wodID": "2", "name": "Workshop", "group": "Unit", "type": "Test", "slotTypes": "1"},
                {"wodID": "3", "name": "Unknown", "group": "Unit", "type": "Missing", "slotTypes": "1"},
            ]
        },
    )


@pytest.fixture
def index() -> assets.AssetIndex:
    return assets.AssetIndex.from_javascript(JAVASCRIPT, version=VERSION)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(assets, "_loaded", None)
    monkeypatch.setattr(assets, "_checked_at", 0.0)
    monkeypatch.setattr(assets, "_last_failure", None)
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("unexpected network")))


def test_actual_paths(data: GameData, index: assets.AssetIndex):
    assert data.unit_asset_path(1, index=index) == UNIT_PATH
    assert data.tool_asset_path(2, index=index) == TOOL_PATH


def test_exact_tool_class_fallback(data: GameData, index: assets.AssetIndex):
    missing = assets.AssetIndex({"Unknown_Unit_Tools": FALLBACK_PATH}, version=VERSION)
    assert data.tool_asset_path(2, index=missing) == FALLBACK_PATH
    # A row classified by slotTypes alone is not a ToolUnitVO in the client.
    with pytest.raises(KeyError, match="Unknown_Unit_Missing"):
        data.tool_asset_path(3, index=index)
    with pytest.raises(KeyError, match="Barracks_Unit_Test"):
        data.unit_asset_path(1, index=missing)
    with pytest.raises(KeyError, match="Unknown_Unit_Tools"):
        data.tool_asset_path(2, index=assets.AssetIndex({}, version=VERSION))


@pytest.mark.parametrize("method", [GameData.unit_asset_path, GameData.tool_asset_path])
def test_unknown_id_does_not_load_index(method, data: GameData):
    with pytest.raises(KeyError, match="99999"):
        method(data, 99999)


def test_index_version_and_snapshot(index: assets.AssetIndex):
    changed = assets.AssetIndex.from_javascript(JAVASCRIPT.replace("--123", "--999"), version="abcdef")
    assert changed.path("Barracks_Unit_Test").endswith("--999")
    assert index.path("Barracks_Unit_Test") == UNIT_PATH
    mapping = {"Test": UNIT_PATH}
    snapshot = assets.AssetIndex(mapping, version=VERSION)
    mapping["Test"] = TOOL_PATH
    assert snapshot.path("Test") == UNIT_PATH


def test_parser_scoped_and_bracket_keys():
    javascript = 'this.assets.Other="interfaceassets/other";' + JAVASCRIPT.replace(
        "this.assets.Barracks_Unit_Test", 'this.assets["Barracks_Unit_Test"]'
    )
    index = assets.AssetIndex.from_javascript(javascript, version=VERSION)
    assert index.path("Barracks_Unit_Test") == UNIT_PATH
    with pytest.raises(KeyError):
        index.path("Other")


@pytest.mark.parametrize(
    "javascript",
    [
        "<html>error</html>",
        "ItemVersions.prototype.fill=function(){},ItemVersions}",
        JAVASCRIPT.replace(UNIT_PATH, "../unsafe"),
        JAVASCRIPT.replace("this.assets.Barracks_Unit_Test=", "window.execute="),
    ],
)
def test_malformed_index(javascript: str):
    with pytest.raises(ValueError, match="[Ii]tem[Vv]ersions|asset"):
        assets.AssetIndex.from_javascript(javascript, version=VERSION)


def response(text: str) -> Mock:
    return Mock(text=text)


def test_lazy_loading_version_cache_and_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    get = Mock(side_effect=[response(INDEX_HTML), response(JAVASCRIPT)])
    monkeypatch.setattr(requests, "get", get)
    first = assets.AssetIndex.load(cache_dir=tmp_path)
    assert first.path("Barracks_Unit_Test") == UNIT_PATH
    assert assets.AssetIndex.load(cache_dir=tmp_path) is first
    assert get.call_count == 2
    monkeypatch.setattr(assets, "_loaded", None)
    get.side_effect = [response(INDEX_HTML)]
    assert assets.AssetIndex.load(cache_dir=tmp_path).path("Barracks_Unit_Test") == UNIT_PATH
    assert get.call_count == 3  # Current version checked, DLL reused from disk.
    get.side_effect = [response(INDEX_HTML.replace(VERSION, "abcdef")), response(JAVASCRIPT.replace("--123", "--999"))]
    refreshed = assets.AssetIndex.load(refresh=True, cache_dir=tmp_path)
    assert refreshed.version == "abcdef"
    assert refreshed.path("Barracks_Unit_Test").endswith("--999")


def test_network_failure_backoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    get = Mock(side_effect=requests.ConnectionError("unavailable"))
    monkeypatch.setattr(requests, "get", get)
    for _ in range(2):
        with pytest.raises(NetworkError, match="asset index"):
            assets.AssetIndex.load(cache_dir=tmp_path)
    assert get.call_count == 1


def test_malformed_delivery_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(requests, "get", Mock(return_value=response("<html>maintenance</html>")))
    with pytest.raises(ValueError, match="DLL"):
        assets.AssetIndex.load(cache_dir=tmp_path)


def test_import_does_not_fetch():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from unittest.mock import patch; "
            "guard = patch('requests.get', side_effect=AssertionError('import fetched')); "
            "guard.start(); import empire_core.gamedata.assets",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_missing_index_is_not_a_tool_fallback(data: GameData, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(assets.AssetIndex, "load", Mock(side_effect=NetworkError("asset index unavailable")))
    with pytest.raises(NetworkError, match="unavailable"):
        data.tool_asset_path(2)


def test_malformed_disk_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / f"item-assets-{VERSION}.json").write_text('["not an index"]', encoding="utf-8")
    monkeypatch.setattr(requests, "get", Mock(return_value=response(INDEX_HTML)))
    with pytest.raises(ValueError, match="cached ItemVersions"):
        assets.AssetIndex.load(cache_dir=tmp_path)


def test_corrupt_path_in_disk_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / f"item-assets-{VERSION}.json").write_text('{"Test": "itemassets/../unsafe"}', encoding="utf-8")
    monkeypatch.setattr(requests, "get", Mock(return_value=response(INDEX_HTML)))
    with pytest.raises(ValueError, match="asset path"):
        assets.AssetIndex.load(cache_dir=tmp_path)


def test_failed_refresh_keeps_previous_snapshot(
    index: assets.AssetIndex, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(assets, "_loaded", index)
    monkeypatch.setattr(requests, "get", Mock(side_effect=requests.ConnectionError("unavailable")))
    with pytest.raises(NetworkError):
        assets.AssetIndex.load(refresh=True, cache_dir=tmp_path)
    assert assets.AssetIndex.load(cache_dir=tmp_path) is index


def test_a_new_dll_replaces_the_loaded_index_after_the_check_interval(
    index: assets.AssetIndex, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(assets, "_loaded", index)
    monkeypatch.setattr(assets, "VERSION_CHECK_INTERVAL", 0.0)
    get = Mock(
        side_effect=[response(INDEX_HTML.replace(VERSION, "abcdef")), response(JAVASCRIPT.replace("--123", "--999"))]
    )
    monkeypatch.setattr(requests, "get", get)
    loaded = assets.AssetIndex.load(cache_dir=tmp_path)
    assert loaded.version == "abcdef"
    assert loaded.path("Barracks_Unit_Test").endswith("--999")


def test_the_same_dll_keeps_the_loaded_index(index: assets.AssetIndex, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(assets, "_loaded", index)
    monkeypatch.setattr(assets, "VERSION_CHECK_INTERVAL", 0.0)
    get = Mock(return_value=response(INDEX_HTML))
    monkeypatch.setattr(requests, "get", get)
    assert assets.AssetIndex.load() is index
    assert get.call_count == 1


def test_the_page_is_checked_once_per_interval(index: assets.AssetIndex, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(assets, "_loaded", index)
    get = Mock(return_value=response(INDEX_HTML))
    monkeypatch.setattr(requests, "get", get)
    for _ in range(3):
        assert assets.AssetIndex.load() is index
    assert get.call_count == 1


@pytest.mark.parametrize(
    "get",
    [
        Mock(side_effect=requests.ConnectionError("unavailable")),
        Mock(return_value=response("<html>maintenance</html>")),
    ],
    ids=["unreachable", "maintenance"],
)
def test_an_unreadable_page_keeps_the_loaded_index(
    get: Mock, index: assets.AssetIndex, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(assets, "_loaded", index)
    monkeypatch.setattr(assets, "VERSION_CHECK_INTERVAL", 0.0)
    monkeypatch.setattr(requests, "get", get)
    assert assets.AssetIndex.load() is index
