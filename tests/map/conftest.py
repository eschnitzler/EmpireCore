"""Fixtures for the map tests."""

import pytest

from empire_core.map.scanner import kingdom_topology


@pytest.fixture(autouse=True)
def fresh_topology():
    """Every test discovers its kingdoms itself: the process-wide topology would carry one test's map into the next."""
    kingdom_topology.clear()
    yield
    kingdom_topology.clear()
