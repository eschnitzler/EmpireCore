"""Dungeon cooldown skips.

Commands:
- msd: Shorten a dungeon's cooldown with a minute skip
- sdc: Skip a dungeon's cooldown
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from pydantic import Field, field_serializer, field_validator

from empire_core.enums import Kingdom, MapItemType
from empire_core.gamedata import EnumOrStr
from empire_core.map.models.items import MapAreaItem
from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.js import js_number_or_none

if TYPE_CHECKING:
    from empire_core.gamedata import Currency

# =============================================================================
# MSD / SDC - Dungeon cooldown skips
# =============================================================================


def _row_or_none(value: object) -> MapAreaItem | None:
    """The dungeon's map row, or None when there is none the client could read."""
    if isinstance(value, MapAreaItem):
        return value
    if not isinstance(value, list):
        return None
    try:
        return MapAreaItem.from_list(value)
    except ValueError:
        return None


def _wire_integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)) or not str(value).strip():
        return None
    numeric = js_number_or_none(value)
    if numeric is None or not math.isfinite(numeric) or numeric != math.trunc(numeric):
        return None
    return int(numeric)


def _row_coordinates(area: MapAreaItem) -> tuple[int, int] | None:
    # Client: DungeonMapobjectVO.parseAreaInfo (22064) reads coordinates from e[1] and e[2].
    if len(area.raw_data) < 3:
        return None
    x, y = (_wire_integer(area.raw_data[index]) for index in (1, 2))
    return None if x is None or y is None else (x, y)


def _row_kingdom(area: MapAreaItem, fallback: Kingdom) -> int | None:
    # Client: DungeonMapobjectVO.parseAreaInfo (22064); the other map-row parsers name their kingdom too.
    index = {
        MapItemType.DUNGEON: 6,
        MapItemType.TREASURE_DUNGEON: 6,
        MapItemType.BOSS_DUNGEON: 7,
        MapItemType.ISLE_DUNGEON: 3,
    }.get(area.item_type)
    if index is None:
        return int(fallback)
    if len(area.raw_data) <= index:
        return None
    return _wire_integer(area.raw_data[index])


def _matches_target(payload: object, x: int, y: int, kingdom: Kingdom) -> bool:
    if not isinstance(payload, dict) or not isinstance(payload.get("AI"), list):
        return True
    try:
        area = MapAreaItem.from_list(payload["AI"], kingdom=kingdom)
    except ValueError:
        return True
    coordinates = _row_coordinates(area)
    realm = _row_kingdom(area, kingdom)
    return coordinates is None or (coordinates == (x, y) and (realm is None or realm == kingdom))


class MinuteSkipDungeonRequest(BaseRequest):
    """
    Shorten a dungeon's cooldown with a minute-skip item.

    A dungeon is an NPC target, treasure-map dungeons included, that has to
    recover before it can be attacked again. Fields follow the client's key
    order: the constructor initialises X, Y, MID, NID before it sets MST and KID.

    Command: msd
    Client: ``C2SMinuteSkipDungeonVO`` (bundle line 72337), built by
    ``SkippableCooldownMinuteSkipProperties.getMinuteSkipCommand`` (bundle line
    72324); ``CastleMinuteSkipDialog.onScrollItemClick`` passes the currency's
    ``jsonKey`` as ``MST`` (bundle line 7722)
    """

    command = "msd"

    x: int = Field(validation_alias="X", description="Dungeon map x")
    y: int = Field(validation_alias="Y", description="Dungeon map y")
    map_id: int = Field(
        validation_alias="MID",
        default=-1,
        description="Treasure-map id, -1 for an ordinary dungeon",
    )
    node_id: int = Field(
        validation_alias="NID",
        default=-1,
        description="Treasure-map node id, -1 for an ordinary dungeon",
    )
    minute_skip: EnumOrStr["Currency"] = Field(
        validation_alias="MST",
        description="The minute skip used, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``; sent as its key",
    )
    kingdom_id: Kingdom = Field(validation_alias="KID", description="Kingdom id")

    def accepts_reply(self, payload: object) -> bool:
        return _matches_target(payload, self.x, self.y, self.kingdom_id)

    @field_serializer("kingdom_id")
    def _kingdom_id_as_string(self, value: Kingdom) -> str:
        # The client sends it through toString()
        return str(int(value))


class MinuteSkipDungeonResponse(BaseResponse):
    """
    The dungeon's map row after a minute skip.

    Command: msd
    Client: ``MSDCommand.executeCommand`` (bundle line 125782), which parses
    ``AI`` with ``WorldmapObjectFactory.parseWorldMapArea`` (``DungeonMapobjectVO`` for a camp)
    """

    command = "msd"

    area: MapAreaItem | None = Field(
        validation_alias="AI",
        default=None,
        description="The dungeon's updated map row, with its victories and remaining cooldown",
    )

    @field_validator("area", mode="before")
    @classmethod
    def _parse_row(cls, value: object) -> object:
        return _row_or_none(value)


class SkipDungeonCooldownRequest(BaseRequest):
    """
    Skip a dungeon's whole cooldown.

    Command: sdc
    Client: ``C2SSkipDungeonCooldownVO`` (bundle line 46101), built by
    ``SkippableCooldownMinuteSkipProperties.getFullSkipCommand`` (bundle line 72323)
    """

    command = "sdc"

    x: int = Field(validation_alias="X", description="Dungeon map x")
    y: int = Field(validation_alias="Y", description="Dungeon map y")
    kingdom_id: Kingdom = Field(validation_alias="KID", description="Kingdom id")
    map_id: int = Field(
        validation_alias="MID",
        default=-1,
        description="Treasure-map id, -1 for an ordinary dungeon",
    )
    node_id: int = Field(
        validation_alias="NID",
        default=-1,
        description="Treasure-map node id, -1 for an ordinary dungeon",
    )

    def accepts_reply(self, payload: object) -> bool:
        return _matches_target(payload, self.x, self.y, self.kingdom_id)


class SkipDungeonCooldownResponse(BaseResponse):
    """
    The dungeon's map row after its cooldown was skipped.

    Command: sdc
    Client: ``SDCCommand.executeCommand`` (bundle line 122333), which parses
    ``AI`` with ``WorldmapObjectFactory.parseWorldMapArea`` (``DungeonMapobjectVO`` for a camp)
    """

    command = "sdc"

    area: MapAreaItem | None = Field(
        validation_alias="AI",
        default=None,
        description="The dungeon's updated map row, with its victories and remaining cooldown",
    )

    @field_validator("area", mode="before")
    @classmethod
    def _parse_row(cls, value: object) -> object:
        return _row_or_none(value)


__all__ = [
    "MinuteSkipDungeonRequest",
    "MinuteSkipDungeonResponse",
    "SkipDungeonCooldownRequest",
    "SkipDungeonCooldownResponse",
]
