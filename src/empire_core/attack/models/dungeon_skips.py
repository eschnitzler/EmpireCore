"""Dungeon cooldown skips.

Commands:
- msd: Shorten a dungeon's cooldown with a minute skip
- sdc: Skip a dungeon's cooldown
"""

from __future__ import annotations

from pydantic import Field, field_serializer, field_validator

from empire_core.enums import Kingdom
from empire_core.map.models.items import MapAreaItem
from empire_core.protocol.base import BaseRequest, BaseResponse

# =============================================================================
# MSD / SDC - Dungeon cooldown skips
# =============================================================================


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

    x: int = Field(alias="X", description="Dungeon map x")
    y: int = Field(alias="Y", description="Dungeon map y")
    map_id: int = Field(alias="MID", default=-1, description="Treasure-map id, -1 for an ordinary dungeon")
    node_id: int = Field(alias="NID", default=-1, description="Treasure-map node id, -1 for an ordinary dungeon")
    minute_skip: str = Field(
        alias="MST",
        description="JSON key of the minute-skip currency used, MS1 to MS7 in the item data (see SCEItem)",
    )
    kingdom_id: Kingdom = Field(alias="KID", description="Kingdom id")

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
        alias="AI",
        default=None,
        description="The dungeon's updated map row, with its victories and remaining cooldown",
    )

    @field_validator("area", mode="before")
    @classmethod
    def _parse_row(cls, value: object) -> object:
        return MapAreaItem.from_list(value) if isinstance(value, list) else value


class SkipDungeonCooldownRequest(BaseRequest):
    """
    Skip a dungeon's whole cooldown.

    Command: sdc
    Client: ``C2SSkipDungeonCooldownVO`` (bundle line 46101), built by
    ``SkippableCooldownMinuteSkipProperties.getFullSkipCommand`` (bundle line 72323)
    """

    command = "sdc"

    x: int = Field(alias="X", description="Dungeon map x")
    y: int = Field(alias="Y", description="Dungeon map y")
    kingdom_id: Kingdom = Field(alias="KID", description="Kingdom id")
    map_id: int = Field(alias="MID", default=-1, description="Treasure-map id, -1 for an ordinary dungeon")
    node_id: int = Field(alias="NID", default=-1, description="Treasure-map node id, -1 for an ordinary dungeon")


class SkipDungeonCooldownResponse(BaseResponse):
    """
    The dungeon's map row after its cooldown was skipped.

    Command: sdc
    Client: ``SDCCommand.executeCommand`` (bundle line 122333), which parses
    ``AI`` with ``WorldmapObjectFactory.parseWorldMapArea`` (``DungeonMapobjectVO`` for a camp)
    """

    command = "sdc"

    area: MapAreaItem | None = Field(
        alias="AI",
        default=None,
        description="The dungeon's updated map row, with its victories and remaining cooldown",
    )

    @field_validator("area", mode="before")
    @classmethod
    def _parse_row(cls, value: object) -> object:
        return MapAreaItem.from_list(value) if isinstance(value, list) else value


__all__ = [
    "MinuteSkipDungeonRequest",
    "MinuteSkipDungeonResponse",
    "SkipDungeonCooldownRequest",
    "SkipDungeonCooldownResponse",
]
