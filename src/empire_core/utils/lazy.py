"""Exports imported on first use, for the game-data id enums: the largest hold thousands of members."""

import importlib
import sys
from collections.abc import Callable, Iterable
from typing import Any


def lazy_exports(module: str, source: str, names: Iterable[str]) -> Callable[[str], Any]:
    """
    A module ``__getattr__`` that imports each of ``names`` from ``source`` when it is first read.

    The module names them under ``TYPE_CHECKING`` too, so type checkers and the docs see them.
    """
    exported = frozenset(names)

    def __getattr__(name: str) -> Any:
        if name not in exported:
            raise AttributeError(f"module {module!r} has no attribute {name!r}")
        value = getattr(importlib.import_module(source), name)
        setattr(sys.modules[module], name, value)
        return value

    return __getattr__


__all__ = ["lazy_exports"]
