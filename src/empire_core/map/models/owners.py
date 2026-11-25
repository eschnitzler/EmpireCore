"""Owner records and the pieces they share with movements and player profiles.

A player's crest, Berimond standing, castle positions and alliance crest.

The Berimond and alliance crest blocks are frozen, and an owner record reads equal blocks into
one shared instance (see :class:`Interned`): a crowded map chunk names hundreds of owners, and
the members of one alliance all send its crest.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from contextlib import suppress
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, overload

from pydantic import (
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    TypeAdapter,
    ValidationError,
    field_validator,
)
from pydantic_core import core_schema

from empire_core.enums import CoatOfArmsBackground, SymbolLayout
from empire_core.gamedata import CoatOfArmsSymbolId, EnumOrInt
from empire_core.gamedata.lenient import known
from empire_core.protocol.base import BasePayload, list_or_empty, object_or_none
from empire_core.protocol.js import ClientInt, ClientIntOf, ParseInt, js_int, js_parse_int, js_truthy

if TYPE_CHECKING:
    from empire_core.gamedata import AllianceCrestColor, AllianceCrestLayout, Title


class OwnerCrest(BasePayload):
    """A player's crest: an owner record's ``E``, and your own crest.

    A layout past the last the client knows stays a plain int; the client draws it as the last one
    (``setSymbols`` and ``setBackground``, split.js lines 57253 and 57236).

    Client: ``CrestVO.loadFromParamObject`` (split.js line 57284)
    """

    is_set: bool = Field(
        validation_alias="IS",
        default=False,
        description="False means the tutorial crest is shown",
    )

    @field_validator("is_set", mode="before")
    @classmethod
    def _truthy(cls, value: Any) -> bool:
        return js_truthy(value)

    symbol_type: SymbolLayout | int = Field(
        validation_alias="SPT", default=SymbolLayout.NONE, description="Where the symbols show"
    )
    symbol1: ClientIntOf[CoatOfArmsSymbolId] = Field(
        validation_alias="S1", default=CoatOfArmsSymbolId(0), description="The first symbol, -1 for none"
    )
    symbol1_color: ClientInt = Field(validation_alias="SC1", default=0, description="First symbol's colour")
    symbol2: ClientIntOf[CoatOfArmsSymbolId] = Field(
        validation_alias="S2", default=CoatOfArmsSymbolId(0), description="The second symbol, -1 for none"
    )
    symbol2_color: ClientInt = Field(validation_alias="SC2", default=0, description="Second symbol's colour")
    background_type: CoatOfArmsBackground | int = Field(
        validation_alias="BGT", default=CoatOfArmsBackground.PLAIN, description="How the background splits its colours"
    )
    background_color1: ClientInt = Field(validation_alias="BGC1", default=0, description="First background colour")
    background_color2: ClientInt = Field(validation_alias="BGC2", default=0, description="Second background colour")

    @field_validator("symbol_type", mode="before")
    @classmethod
    def _symbol_layout(cls, value: Any) -> SymbolLayout | int:
        return _layout(SymbolLayout, value)

    @field_validator("background_type", mode="before")
    @classmethod
    def _background(cls, value: Any) -> CoatOfArmsBackground | int:
        return _layout(CoatOfArmsBackground, value)


def _layout(layouts: type[SymbolLayout] | type[CoatOfArmsBackground], value: Any) -> Any:
    return known(layouts, js_int(value), warn=False)


class OwnerFaction(BasePayload):
    """Berimond standing: an owner record's ``FN``. Frozen.

    Client: ``WorldMapOwnerInfoVO.fillFromParamObject`` (split.js line 58409), which reads each key through
    ``parseInt``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    faction_id: ParseInt = Field(validation_alias="FID", default=0, description="Faction id")
    protection_status: ParseInt = Field(validation_alias="PMS", default=0, description="Berimond protection status")
    protection_end_seconds: ParseInt = Field(
        validation_alias="PMT",
        default=0,
        description="Seconds until Berimond protection ends",
    )
    title_id: EnumOrInt["Title"] | None = Field(
        validation_alias="TID",
        default=None,
        description="The gallantry title; None when TID is -1 or not a number",
    )

    @field_validator("title_id", mode="before")
    @classmethod
    def _title(cls, value: Any) -> Any:
        # parseInt(e.FN.TID), looked up by getTitleByTitleID (FactionRankingItem.update, bundle line 95431),
        # which finds no title for -1
        title_id = js_parse_int(value)
        return None if title_id is None or title_id < 0 else title_id


class OwnerCastlePosition(NamedTuple):
    """One of an owner's castles or villages: an entry of ``AP`` or ``VP``, ``[kingdom_id, area_id, x, y, area_type]``.

    ``kingdom_id`` and ``area_id`` are read through the client's ``int()``; ``area_type``
    is None when the entry has none.

    Client: ``MinWorldMapCastleInfoVO.fillFromParamObject`` (bundle line 18459).
    """

    kingdom_id: ClientInt
    area_id: ClientInt
    x: int
    y: int
    area_type: int | None = None


_POSITION = TypeAdapter(OwnerCastlePosition)
_STRIDE = len(OwnerCastlePosition._fields)


class OwnerPositions(Sequence[OwnerCastlePosition]):
    """
    An owner record's castles or villages, its ``AP`` or ``VP``: a read-only sequence of :class:`OwnerCastlePosition`.

    The positions are packed into one tuple of ints and each is built as it is read: a
    kingdom scan reads tens of thousands, and one packed tuple of ints is an object the
    garbage collector stops tracking, where a named tuple per position is one it tracks
    each. It compares equal to a list or tuple of the same positions and serializes as rows.

    Client: ``WorldMapOwnerInfoVO.parsePosList`` (split.js line 58463), one
    ``MinWorldMapCastleInfoVO`` per row (split.js line 67077)
    """

    __slots__ = ("_packed",)

    def __init__(self, positions: Iterable[OwnerCastlePosition] = ()) -> None:
        self._packed: tuple[int | None, ...] = tuple(value for position in positions for value in position)

    @classmethod
    def from_rows(cls, value: Any) -> OwnerPositions:
        """
        Read ``AP`` or ``VP`` rows, as ``WorldMapOwnerInfoVO.parsePosList`` (split.js line 58463) does.

        Only the first five entries of a row are read. A row the server wraps in one
        extra list (seen on AP in Berimond) is unwrapped, which the client does not do;
        a row that still cannot be read (fewer than four entries, or a position that is
        not a number) is skipped instead of failing the record.

        A row of plain ints, the shape live replies carry, is packed as it is; only
        another row goes through pydantic, one call per row.
        """
        if isinstance(value, OwnerPositions):
            return value
        positions = cls()
        if not isinstance(value, (list, tuple)):
            return positions
        packed: list[int | None] = []
        for entry in value:
            if isinstance(entry, (list, tuple)) and len(entry) == 1 and isinstance(entry[0], (list, tuple)):
                entry = entry[0]
            if not isinstance(entry, (list, tuple)) or len(entry) < 4:
                continue
            fields = entry[:_STRIDE]
            if isinstance(entry, OwnerCastlePosition) or set(map(type, fields)) == {int}:
                packed.extend(fields)
                packed.extend([None] * (_STRIDE - len(fields)))
            else:
                with suppress(ValidationError):
                    packed.extend(_POSITION.validate_python(fields))
        positions._packed = tuple(packed)
        return positions

    def __len__(self) -> int:
        return len(self._packed) // _STRIDE

    @overload
    def __getitem__(self, index: int) -> OwnerCastlePosition: ...
    @overload
    def __getitem__(self, index: slice) -> list[OwnerCastlePosition]: ...
    def __getitem__(self, index: int | slice) -> OwnerCastlePosition | list[OwnerCastlePosition]:
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        start = range(len(self))[index] * _STRIDE
        return OwnerCastlePosition._make(self._packed[start : start + _STRIDE])

    def __iter__(self) -> Iterator[OwnerCastlePosition]:
        packed = self._packed
        for start in range(0, len(packed), _STRIDE):
            yield OwnerCastlePosition._make(packed[start : start + _STRIDE])

    def __eq__(self, other: object) -> bool:
        if isinstance(other, OwnerPositions):
            return self._packed == other._packed
        if isinstance(other, (list, tuple)):
            return list(self) == list(other)
        return NotImplemented

    def __repr__(self) -> str:
        return f"OwnerPositions({list(self)!r})"

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls.from_rows,
            json_schema_input_schema=handler.generate_schema(list[OwnerCastlePosition]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda positions: [list(position) for position in positions]
            ),
        )


class AllianceCrest(BasePayload):
    """
    An alliance's crest: a layout and its colours. Frozen.

    Client: ``AllianceCrestVO.fillWithData`` (split.js line 60469); ``fillFromArray``
    (split.js line 60481) reads the same two values from ``[layout_id, color_ids]``; each colour is
    looked up through ``int()`` (``AllianceCrestVO.colors``, split.js line 60424).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    layout_id: EnumOrInt["AllianceCrestLayout"] | None = Field(
        validation_alias="ACLI",
        default=None,
        description="The crest layout; None when the crest names none (0)",
    )
    color_ids: tuple[ClientIntOf[EnumOrInt["AllianceCrestColor"]], ...] = Field(
        validation_alias="ACCS",
        default=(),
        description="The colours, one per layout colour",
    )

    @field_validator("layout_id", mode="before")
    @classmethod
    def _layout(cls, value: Any) -> Any:
        # fillWithData reads int(e.ACLI), so a missing layout is 0, which no layout has
        return js_int(value) or None

    @field_validator("color_ids", mode="before")
    @classmethod
    def _stored_raw(cls, value: Any) -> Any:
        # The client stores ACCS as it arrives, so a missing list is no colours; a tuple is the colours by field name
        return value if isinstance(value, tuple) else list_or_empty(value)


class AllianceEmblem(BasePayload):
    """
    The alliance crest block of an owner record: its ``aee``. Frozen.

    Client: ``WorldMapOwnerInfoVO.fillFromParamObject`` (split.js line 58409)
    reads only ``ACCA``, and only for a player in an alliance.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    crest: AllianceCrest | None = Field(
        validation_alias="ACCA", default=None, description="The alliance's current crest"
    )

    @field_validator("crest", mode="before")
    @classmethod
    def _crest_needs_an_object(cls, value: Any) -> Any:
        return object_or_none(value)


class Interned:
    """
    Marks a frozen block model field whose equal wire blocks are read into one shared instance.

    ``Annotated[OwnerFaction, Interned()]`` reads a block of JSON values once per model and returns
    the same instance for every equal block after it; any other value is read as usual. A shared
    instance equals the one a fresh read would build, keys present included. Each model keeps up
    to ``MAXSIZE`` blocks and forgets them all when full.
    """

    MAXSIZE: ClassVar[int] = 4096
    _shared: ClassVar[dict[type[BasePayload], dict[str, BasePayload]]] = {}

    @classmethod
    def clear(cls) -> None:
        """Forget every shared instance."""
        for shared in cls._shared.values():
            shared.clear()

    def __get_pydantic_core_schema__(self, source: type[BasePayload], handler: GetCoreSchemaHandler) -> Any:
        shared = Interned._shared.setdefault(source, {})

        def read(value: Any, build: core_schema.ValidatorFunctionWrapHandler) -> Any:
            if type(value) is not dict or not _json_only(value):
                return build(value)
            # A text key: the collector never tracks a str
            key = _BLOCK_TEXT(value)
            block = shared.get(key)
            if block is None:
                block = build(value)
                if len(shared) >= Interned.MAXSIZE:
                    shared.clear()
                shared[key] = block
            return block

        return core_schema.no_info_wrap_validator_function(read, handler(source))


_BLOCK_TEXT = json.JSONEncoder(separators=(",", ":"), check_circular=False).encode


def _json_only(value: Any) -> bool:
    """Whether ``value`` holds only JSON values its text tells apart: no floats, tuples or keys that are not text."""
    if type(value) is dict:
        return all(type(key) is str and _json_only(item) for key, item in value.items())
    if type(value) is list:
        return all(map(_json_only, value))
    return value is None or type(value) in (int, str, bool)


__all__ = [
    "AllianceCrest",
    "AllianceEmblem",
    "OwnerCastlePosition",
    "OwnerCrest",
    "OwnerFaction",
    "OwnerPositions",
    "Interned",
]
