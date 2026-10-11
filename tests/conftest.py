"""Fixtures shared across the test suite."""

from collections.abc import Callable, Generator

import pytest
import requests

from empire_core import texts
from empire_core.gamedata import GameData, troops
from empire_core.gamedata import data as gamedata_data
from empire_core.state.manager import GameState


@pytest.fixture(autouse=True)
def fresh_game_data(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Every test starts with no game data or texts loaded, no failure backoff and its own disk cache,
    and no request reaches the network unless the test stubs it.
    """

    def offline(url: str, *args: object, **kwargs: object) -> None:
        raise requests.ConnectionError(f"the test suite does not reach the network: {url}")

    monkeypatch.setattr(requests, "get", offline)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
    monkeypatch.setattr(gamedata_data, "_loaded", None)
    monkeypatch.setattr(gamedata_data, "_failed_at", None)
    monkeypatch.setattr(troops, "_last_degraded_warning_at", 0.0)
    monkeypatch.setattr(texts, "_texts", {})
    monkeypatch.setattr(texts, "_fetched_at", {})
    monkeypatch.setattr(texts, "_failed_at", {})


@pytest.fixture
def state() -> Generator[GameState, None, None]:
    gs = GameState()
    yield gs
    gs.shutdown()


@pytest.fixture
def stub_game_data_load(monkeypatch: pytest.MonkeyPatch) -> Callable[[GameData], list[GameData]]:
    """
    Make :meth:`GameData.load` hand out the given data as the process's, as a real load
    does; the returned list gets one entry per load.
    """

    def stub(data: GameData) -> list[GameData]:
        loads: list[GameData] = []

        def load(cls: type[GameData], **kwargs: object) -> GameData:
            loads.append(data)
            monkeypatch.setattr(gamedata_data, "_loaded", data)
            return data

        monkeypatch.setattr(GameData, "load", classmethod(load))
        return loads

    return stub
