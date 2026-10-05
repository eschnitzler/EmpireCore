"""
Map areas, kingdom scans and finding map objects, enemy castles and Berimond towers.

Reading the map moves the session off the castle it had joined: a
castle-scoped read after a scan fails with NOT_IN_OWNED_CASTLE until the
castle is joined again. ``client.army`` methods join it themselves; anything
else castle-scoped needs ``client.castle.select`` first.
"""

from __future__ import annotations

import threading
from typing import TypeVar

from empire_core.enums import Kingdom, MapItemType
from empire_core.exceptions import CommandError
from empire_core.map.models.areas import (
    MAX_FINDABLE_ENEMY_INDEX,
    FindNextEnemyCastleRequest,
    FindNextEnemyCastleResponse,
    FindNextMapObjectRequest,
    FindNextMapObjectResponse,
    FindNextTowerRequest,
    FindNextTowerResponse,
    GetMapAreaRequest,
    GetMapAreaResponse,
)
from empire_core.map.models.items import parse_area_rows
from empire_core.map.scanner import MapScanner, ScanResult
from empire_core.protocol.base import BaseRequest
from empire_core.protocol.errors import GGEError
from empire_core.services.base import BaseService

_F = TypeVar("_F", bound=FindNextMapObjectResponse)


class MapService(BaseService):
    """
    Read the world map: areas, kingdom scans and the nearest object of a type.

    Reached as client.map.
    """

    def scan_map_area(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        kingdom: Kingdom = Kingdom.GREEN,
        timeout: float = 5.0,
    ) -> GetMapAreaResponse:
        """
        Scan a specific area of the map.

        The session leaves the castle it had joined; see the module docstring.

        Args:
            x1: Left X coordinate
            y1: Top Y coordinate
            x2: Right X coordinate
            y2: Bottom Y coordinate
            kingdom: Kingdom to scan
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        request = GetMapAreaRequest(kingdom=kingdom, x1=x1, y1=y1, x2=x2, y2=y2)
        return self.request(request, GetMapAreaResponse, timeout=timeout)

    def scan_kingdom(
        self,
        kingdom: Kingdom = Kingdom.GREEN,
        item_types: list[MapItemType] | None = None,
        timeout: float = 300.0,
        request_timeout: float = 5.0,
        chunk_delay: float = 0.0,
        include_unowned_types: set[MapItemType] | None = None,
        *,
        cancel: threading.Event | None = None,
    ) -> ScanResult:
        """Scan a kingdom map. See MapScanner.scan_kingdom; the session leaves its castle."""
        return MapScanner(self.client).scan_kingdom(
            kingdom,
            item_types,
            timeout,
            request_timeout,
            chunk_delay,
            include_unowned_types=include_unowned_types,
            cancel=cancel,
        )

    def scan_chunks(
        self,
        kingdom: Kingdom,
        chunks: list[tuple[int, int]],
        item_types: list[MapItemType] | None = None,
        timeout: float = 300.0,
        request_timeout: float = 5.0,
        chunk_delay: float = 0.0,
        include_unowned_types: set[MapItemType] | None = None,
        *,
        cancel: threading.Event | None = None,
    ) -> ScanResult:
        """Scan an explicit chunk list (no BFS). See MapScanner.scan_chunks; the session leaves its castle."""
        return MapScanner(self.client).scan_chunks(
            kingdom,
            chunks,
            item_types,
            timeout,
            request_timeout,
            chunk_delay,
            include_unowned_types=include_unowned_types,
            cancel=cancel,
        )

    def find_next(
        self,
        area_type: MapItemType,
        kingdom: Kingdom = Kingdom.GREEN,
        *,
        min_level: int = -1,
        max_level: int = -1,
        owner_id: int = -1,
        timeout: float = 5.0,
    ) -> FindNextMapObjectResponse | None:
        """
        Find the nearest map object of an area type, with the map rows around it.

        Args:
            area_type: The area type to look for
            kingdom: The kingdom to look in
            min_level: Lowest level to match, -1 for any
            max_level: Highest level to match, -1 for any
            owner_id: The NPC owner to match, -1 for any
            timeout: Timeout in seconds

        Returns:
            The reply, its rows read in ``kingdom``; None when nothing matches (NO_PLAYER_FOUND)

        Raises:
            CommandError: The server refused for any other reason
        """
        request = FindNextMapObjectRequest(
            area_type=area_type, kingdom=kingdom, min_level=min_level, max_level=max_level, owner_id=owner_id
        )
        return self._find(request, FindNextMapObjectResponse, kingdom, timeout)

    def find_next_enemy_castle(
        self,
        x: int,
        y: int,
        index: int = 0,
        min_level: int = -1,
        max_level: int = -1,
        *,
        kingdom: Kingdom = Kingdom.GREEN,
        timeout: float = 5.0,
    ) -> FindNextEnemyCastleResponse | None:
        """
        Find an enemy castle near a position, with the map rows around it.

        The game's "search enemy" button asks with index 0, 1, 2 ... 9 and
        then 0 again, so each press finds another castle. On a live account
        indexes 0 to 2 found three different players' outposts near the castle
        searched from; the reply also echoes ``N``, which the client does not read.

        Args:
            x: Map x to search from
            y: Map y to search from
            index: Which castle to find, 0 to 9
            min_level: Lowest level to match, -1 for any
            max_level: Highest level to match, -1 for any
            kingdom: The kingdom the rows of the reply are read in; the request names none
            timeout: Timeout in seconds

        Returns:
            The reply; None when nothing matches (NO_PLAYER_FOUND)

        Raises:
            ValueError: ``index`` is not 0 to 9
            CommandError: The server refused for any other reason

        Client: ``C2SFindNextEnemyCastleVO`` (bundle line 55304), sent by
        ``SearchEnemyPanelButton.onButtonClicked`` (bundle line 108075)
        """
        if not 0 <= index <= MAX_FINDABLE_ENEMY_INDEX:
            raise ValueError(f"index must be 0 to {MAX_FINDABLE_ENEMY_INDEX}, got {index}")
        request = FindNextEnemyCastleRequest(x=x, y=y, index=index, min_level=min_level, max_level=max_level)
        return self._find(request, FindNextEnemyCastleResponse, kingdom, timeout)

    def find_next_tower(self, timeout: float = 5.0) -> FindNextTowerResponse | None:
        """
        Find the next Berimond tower, with the map rows around it, read in Berimond.

        Returns:
            The reply; None when nothing matches (NO_PLAYER_FOUND)

        Raises:
            CommandError: The server refused for any other reason, for example
                when no Berimond event runs

        Client: ``C2SFindNextTowerVO`` (bundle line 37533), sent by
        ``SearchEnemyPanelButton.onButtonClicked`` (bundle line 108075) in Berimond
        """
        return self._find(FindNextTowerRequest(), FindNextTowerResponse, Kingdom.BERIMOND, timeout)

    def _find(self, request: BaseRequest, response_type: type[_F], kingdom: Kingdom, timeout: float) -> _F | None:
        """Send a find-next request; None for NO_PLAYER_FOUND, as ``FNMCommand`` reads it (bundle line 40185)."""
        try:
            response = self.request(request, response_type, timeout=timeout)
        except CommandError as e:
            if e.code == GGEError.NO_PLAYER_FOUND:
                return None
            raise
        response.area.items = parse_area_rows([item.raw_data for item in response.area.items], kingdom)[0]
        return response
