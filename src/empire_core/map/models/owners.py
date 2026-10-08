"""Owner records and the pieces they share with movements and player profiles.

A player's crest, faction standing, castle positions and alliance crest.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Annotated, Any, NamedTuple

from pydantic import BeforeValidator, Field, TypeAdapter, ValidationError, field_validator

from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, list_or_empty, object_or_none
from empire_core.protocol.js import ClientInt, ParseInt, js_int, js_parse_int, js_truthy

if TYPE_CHECKING:
    from empire_core.gamedata import AllianceCrestColor, AllianceCrestLayout, Title


class OwnerCrest(BasePayload):
    """A player's crest: an owner record's ``E``.

    Client: ``CrestVO.loadFromParamObject`` (bundle line 10587).
    """

    is_set: bool = Field(alias="IS", default=False, description="False means the tutorial crest is shown")

    @field_validator("is_set", mode="before")
    @classmethod
    def _truthy(cls, value: Any) -> bool:
        return js_truthy(value)

    symbol_type: ClientInt = Field(alias="SPT", default=0, description="Symbol layout type")
    symbol1: ClientInt = Field(alias="S1", default=0, description="First symbol id")
    symbol1_color: ClientInt = Field(alias="SC1", default=0, description="First symbol's colour")
    symbol2: ClientInt = Field(alias="S2", default=0, description="Second symbol id")
    symbol2_color: ClientInt = Field(alias="SC2", default=0, description="Second symbol's colour")
    background_type: ClientInt = Field(alias="BGT", default=0, description="Background layout type")
    background_color1: ClientInt = Field(alias="BGC1", default=0, description="First background colour")
    background_color2: ClientInt = Field(alias="BGC2", default=0, description="Second background colour")


class OwnerFaction(BasePayload):
    """Faction event standing: an owner record's ``FN``.

    Client: ``WorldMapOwnerInfoVO.fillFromParamObject`` (bundle line 10794), which reads each key through ``parseInt``.
    """

    faction_id: ParseInt = Field(alias="FID", default=0, description="Faction id")
    protection_status: ParseInt = Field(alias="PMS", default=0, description="Faction protection status")
    protection_end_seconds: ParseInt = Field(
        alias="PMT", default=0, description="Seconds until faction protection ends"
    )
    title_id: EnumOrInt["Title"] | None = Field(
        alias="TID", default=None, description="The faction title; None when TID is not a number"
    )

    @field_validator("title_id", mode="before")
    @classmethod
    def _title(cls, value: Any) -> Any:
        # parseInt(e.FN.TID), looked up by getTitleByTitleID (FactionRankingItem.update, bundle line 95431)
        return js_parse_int(value)


class OwnerCastlePosition(NamedTuple):
    """One of an owner's castles or villages: an entry of ``AP`` or ``VP``, ``[kingdom_id, area_id, x, y, area_type]``.

    A plain named tuple rather than a model: a kingdom scan keeps tens of thousands.
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


def owner_positions(value: Any) -> list[OwnerCastlePosition]:
    """
    An owner record's ``AP`` or ``VP`` rows, as ``WorldMapOwnerInfoVO.parsePosList`` (bundle line 10795) reads them.

    Only the first five entries of a row are read. A row the server wraps in one
    extra list (seen on AP in Berimond) is unwrapped, which the client does not do;
    a row that still cannot be read (fewer than four entries, or a position that is
    not a number) is skipped instead of failing the record.

    A row of plain ints, the shape live replies carry, is taken as it is; only
    another row goes through pydantic, one call per row.
    """
    if not isinstance(value, list):
        return []
    positions: list[OwnerCastlePosition] = []
    for entry in value:
        if isinstance(entry, (list, tuple)) and len(entry) == 1 and isinstance(entry[0], (list, tuple)):
            entry = entry[0]
        if isinstance(entry, OwnerCastlePosition):
            positions.append(entry)
        elif isinstance(entry, (list, tuple)) and len(entry) >= 4:
            fields = entry[:5]
            if set(map(type, fields)) == {int}:
                positions.append(OwnerCastlePosition(*fields))
            else:
                with suppress(ValidationError):
                    positions.append(_POSITION.validate_python(fields))
    return positions


class AllianceCrest(BasePayload):
    """
    An alliance's crest: a layout and its colours.

    Client: ``AllianceCrestVO.fillWithData`` (bundle line 11233); ``fillFromArray``
    (bundle line 11237) reads the same two values from ``[layout_id, color_ids]``; each colour is
    looked up through ``int()`` (bundle line 11216).
    """

    layout_id: EnumOrInt["AllianceCrestLayout"] | None = Field(
        alias="ACLI", default=None, description="The crest layout; None when the crest names none (0)"
    )
    color_ids: list[Annotated[EnumOrInt["AllianceCrestColor"], BeforeValidator(js_int)]] = Field(
        alias="ACCS", default_factory=list, description="The colours, one per layout colour"
    )

    @field_validator("layout_id", mode="before")
    @classmethod
    def _layout(cls, value: Any) -> Any:
        # fillWithData reads int(e.ACLI), so a missing layout is 0, which no layout has
        return js_int(value) or None

    @field_validator("color_ids", mode="before")
    @classmethod
    def _stored_raw(cls, value: Any) -> Any:
        # The client stores ACCS as it arrives, so a missing list is no colours
        return list_or_empty(value)


class AllianceEmblem(BasePayload):
    """
    The alliance crest block of an owner record: its ``aee``.

    Client: ``WorldMapOwnerInfoVO.fillFromParamObject`` (bundle line 10794)
    reads only ``ACCA``, and only for a player in an alliance.
    """

    crest: AllianceCrest | None = Field(alias="ACCA", default=None, description="The alliance's current crest")

    @field_validator("crest", mode="before")
    @classmethod
    def _crest_needs_an_object(cls, value: Any) -> Any:
        return object_or_none(value)


__all__ = [
    "AllianceCrest",
    "AllianceEmblem",
    "OwnerCastlePosition",
    "OwnerCrest",
    "OwnerFaction",
    "owner_positions",
]
