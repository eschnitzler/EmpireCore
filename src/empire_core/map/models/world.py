"""The world map's size: the server info (nfo) that names it in sectors, and the size in tiles."""

from __future__ import annotations

from typing import NamedTuple

from pydantic import Field

from empire_core.enums import Kingdom
from empire_core.protocol.base import BaseResponse
from empire_core.protocol.js import ClientInt

SECTOR_SIZE = 13
"""Tiles a side of a map sector. Client: ``WorldConst.SECTOR_WIDTH`` and ``SECTOR_HEIGHT`` (dll line 20003)"""

BERIMOND_SECTORS = (200, 10)
"""Berimond's size in sectors, fixed in the client.

Client: ``FactionConst.MAP_WIDTH_IN_SECTORS`` and ``MAP_HEIGHT_IN_SECTORS`` (dll line 19333)
"""


class MapSize(NamedTuple):
    """A kingdom's map in tiles: x runs from 0 to ``width - 1`` and wraps, y from 0 to ``height - 1``."""

    width: int
    height: int


class ServerInfoResponse(BaseResponse):
    """
    The game server's info, pushed once a connection opens, before login.

    Command: nfo. The client keeps the sector counts as the world map's size;
    ``GGCCommand`` (bundle line 120540) would set it the same way from a ``ggc``
    reply, but nothing in the client sends ``ggc`` and the server does not answer one.

    Client: ``NFOCastleCommand.executeCommand`` (bundle line 120801) calls
    ``ClientConstCastle.setWorldmapSizeViaGGC`` (bundle line 985)
    """

    command = "nfo"

    xml_version_e4k: str = Field(validation_alias="XML_E4K", default="", description="Game data version, E4K")
    xml_version: str = Field(validation_alias="XML_EP", default="", description="Game data version the server runs")
    min_name_size: ClientInt = Field(validation_alias="minNameSize", default=0, description="Shortest player name")
    sector_count_x: ClientInt = Field(validation_alias="sectorCountX", default=0, description="Map width in sectors")
    sector_count_y: ClientInt = Field(validation_alias="sectorCountY", default=0, description="Map height in sectors")

    def map_size(self, kingdom: Kingdom) -> MapSize:
        """
        ``kingdom``'s map in tiles: Berimond's fixed size, every other kingdom's from the sector counts.

        Client: ``SwitchKingdomCommand.execute`` (bundle line 101096); ``ClientConstCastle.WORLD_WIDTH``
        and ``WORLD_HEIGHT`` (bundle line 994) multiply by the sector size
        """
        width, height = BERIMOND_SECTORS if kingdom == Kingdom.BERIMOND else (self.sector_count_x, self.sector_count_y)
        return MapSize(width * SECTOR_SIZE, height * SECTOR_SIZE)
