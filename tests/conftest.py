"""Fixtures shared across the test suite."""

from collections.abc import Generator

import pytest

from empire_core.gamedata import data as gamedata_data
from empire_core.gamedata import troops
from empire_core.state.manager import GameState


@pytest.fixture(autouse=True)
def fresh_game_data(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with no game data loaded, no failure backoff and its own disk cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
    monkeypatch.setattr(gamedata_data, "_loaded", None)
    monkeypatch.setattr(gamedata_data, "_failed_at", None)
    monkeypatch.setattr(troops, "_last_degraded_warning_at", 0.0)


@pytest.fixture
def state() -> Generator[GameState, None, None]:
    gs = GameState()
    yield gs
    gs.shutdown()
