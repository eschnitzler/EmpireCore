"""Smoke tests to verify the package imports correctly."""

import empire_core


def test_package_importable() -> None:
    assert empire_core is not None


def test_game_event_exported() -> None:
    from empire_core import GameEvent

    assert GameEvent is not None
