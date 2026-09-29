"""Fixtures shared across the test suite."""

from collections.abc import Generator

import pytest

from empire_core.state.manager import GameState


@pytest.fixture
def state() -> Generator[GameState, None, None]:
    gs = GameState()
    yield gs
    gs.shutdown()
