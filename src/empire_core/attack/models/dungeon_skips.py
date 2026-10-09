"""Dungeon cooldown skips.

Commands:
- msd: Shorten a dungeon's cooldown with a minute skip
- sdc: Skip a dungeon's cooldown
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field, field_serializer, field_validator

from empire_core.enums import Kingdom
from empire_core.gamedata import EnumOrStr
from empire_core.map.models.items import MapAreaItem
from empire_core.protocol.base import BaseRequest, BaseResponse

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

    x: int = Field(validation_alias="X", serialization_alias="X", description="Dungeon map x")
    y: int = Field(validation_alias="Y", serialization_alias="Y", description="Dungeon map y")
    map_id: int = Field(
        validation_alias="MID",
        serialization_alias="MID",
        default=-1,
        description="Treasure-map id, -1 for an ordinary dungeon",
    )
    node_id: int = Field(
        validation_alias="NID",
        serialization_alias="NID",
        default=-1,
        description="Treasure-map node id, -1 for an ordinary dungeon",
    )
    minute_skip: EnumOrStr["Currency"] = Field(
        validation_alias="MST",
        serialization_alias="MST",
        description="The minute skip used, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``; sent as its key",
    )
    kingdom_id: Kingdom = Field(validation_alias="KID", serialization_alias="KID", description="Kingdom id")

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
        serialization_alias="AI",
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

    x: int = Field(validation_alias="X", serialization_alias="X", description="Dungeon map x")
    y: int = Field(validation_alias="Y", serialization_alias="Y", description="Dungeon map y")
    kingdom_id: Kingdom = Field(validation_alias="KID", serialization_alias="KID", description="Kingdom id")
    map_id: int = Field(
        validation_alias="MID",
        serialization_alias="MID",
        default=-1,
        description="Treasure-map id, -1 for an ordinary dungeon",
    )
    node_id: int = Field(
        validation_alias="NID",
        serialization_alias="NID",
        default=-1,
        description="Treasure-map node id, -1 for an ordinary dungeon",
    )


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
        serialization_alias="AI",
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
