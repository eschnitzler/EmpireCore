"""Fixtures shared across the test suite."""

from collections.abc import Generator

import pytest

from empire_core.gamedata import set_default_game_data
from empire_core.state.manager import GameState


@pytest.fixture(autouse=True)
def _forget_default_game_data() -> Generator[None, None, None]:
    """GameData.load() makes its result the default; no test should see another's."""
    yield
    set_default_game_data(None)


@pytest.fixture
def state() -> Generator[GameState, None, None]:
    gs = GameState()
    yield gs
    gs.shutdown()
