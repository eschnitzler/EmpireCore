"""
Lenient id fields: the enum member for an id the enum knows, the plain value for one it does not.

A client release can send an id the generated enums do not have yet. A field typed
``EnumOrInt[Kingdom]`` keeps such an id as its int instead of failing the packet, and logs a
warning once per id. ``EnumOrInt[Unit, Tool]`` takes a member of either, for an id from a
table two enums share. Name a generated enum by its name in quotes (``EnumOrInt["QuestId"]``, the
enum imported under ``TYPE_CHECKING``) so its module loads only when a value arrives; the
largest of them hold thousands of members.

Inside the items tables ``GameDataId[E]`` and ``GameDataKey[E]`` do the same without the warning:
loading items newer than the enums already warns once for the whole version.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterable
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Any, Union

from pydantic import PlainValidator
from typing_extensions import Never, TypeVar

from empire_core.protocol.js import js_parse_int

logger = logging.getLogger(__name__)

_E = TypeVar("_E", bound=Enum)
_F = TypeVar("_F", bound=Enum, default=Never)

_warned: set[tuple[str, object]] = set()


def known(enums: type[_E] | Iterable[type[_E]], value: Any, *, warn: bool = True) -> _E | Any:
    """
    The member of the first of ``enums`` that has ``value``, else ``value`` itself.

    A value none of them has is logged once per enum name and value, unless ``warn`` is False.
    """
    candidates = [enums] if isinstance(enums, type) else list(enums)
    for enum in candidates:
        member = enum._value2member_map_.get(value)
        if member is not None:
            return member
    if not warn:
        return value
    names = "/".join(enum.__name__ for enum in candidates)
    if (names, value) not in _warned:
        _warned.add((names, value))
        logger.warning("%s has no member %r; kept as the plain value (newer game data?)", names, value)
    return value


class LenientEnum:
    """The validator behind the lenient types: reads the id, then looks its member up."""

    def __init__(
        self,
        enum: type[Enum] | str | tuple[type[Enum] | str, ...],
        base: type[int] | type[str],
        *,
        warn: bool = True,
    ) -> None:
        self._named = enum if isinstance(enum, tuple) else (enum,)
        self._enums: tuple[type[Enum], ...] | None = None
        self.base = base
        self.warn = warn

    @property
    def enums(self) -> tuple[type[Enum], ...]:
        """The enums, in lookup order; one named by a string is looked up among the game-data id enums on first use."""
        if self._enums is None:
            self._enums = tuple(
                getattr(importlib.import_module("empire_core.gamedata.ids"), enum) if isinstance(enum, str) else enum
                for enum in self._named
            )
        return self._enums

    def __call__(self, value: Any) -> Any:
        enums = self.enums
        if isinstance(value, enums):
            return value
        if self.base is int:
            number = js_parse_int(value) if isinstance(value, str) else value
            if isinstance(number, bool) or not isinstance(number, int):
                raise ValueError(f"{value!r} is not an id of {'/'.join(enum.__name__ for enum in enums)}")
            return known(enums, int(number), warn=self.warn)
        if not isinstance(value, str):
            raise ValueError(f"{value!r} is not a key of {'/'.join(enum.__name__ for enum in enums)}")
        return known(enums, value, warn=self.warn)


if TYPE_CHECKING:
    EnumOrInt = Union[_E, _F, int]
    EnumOrStr = Union[_E, str]
    GameDataId = Union[_E, int]
    GameDataKey = Union[_E, str]
else:

    class EnumOrInt:
        """``EnumOrInt[E]``: a member of the IntEnum ``E``, or the plain int of an id ``E`` lacks.

        ``EnumOrInt[E, F]`` looks the id up in ``E``, then in ``F``.
        """

        def __class_getitem__(cls, enum: type[Enum] | str | tuple[type[Enum] | str, ...]) -> Any:
            return Annotated[int, PlainValidator(LenientEnum(enum, int))]

    class EnumOrStr:
        """``EnumOrStr[E]``: a member of the str Enum ``E``, or the plain str of a key ``E`` lacks."""

        def __class_getitem__(cls, enum: type[Enum] | str) -> Any:
            return Annotated[str, PlainValidator(LenientEnum(enum, str))]

    class GameDataId:
        """``GameDataId[E]``: ``EnumOrInt[E]`` for an id inside the items tables, kept without a warning."""

        def __class_getitem__(cls, enum: type[Enum] | str) -> Any:
            return Annotated[int, PlainValidator(LenientEnum(enum, int, warn=False))]

    class GameDataKey:
        """``GameDataKey[E]``: ``EnumOrStr[E]`` for a fixed text column of the items tables, kept without a warning."""

        def __class_getitem__(cls, enum: type[Enum] | str) -> Any:
            return Annotated[str, PlainValidator(LenientEnum(enum, str, warn=False))]


__all__ = ["EnumOrInt", "EnumOrStr", "GameDataId", "GameDataKey", "LenientEnum", "known"]
