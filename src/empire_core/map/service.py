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

from empire_core.enums import GGEError, Kingdom, MapItemType
from empire_core.exceptions import CommandError
from empire_core.map.models.areas import (
    MAX_AREA_SPAN,
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
from empire_core.map.pacing import MapAreaPacer
from empire_core.map.scanner import ChunkHandler, MapScanner, ScanResult
from empire_core.protocol.base import BaseRequest
from empire_core.services.base import BaseService

_F = TypeVar("_F", bound=FindNextMapObjectResponse)


class MapService(BaseService):
    """
    Read the world map: areas, kingdom scans and the nearest object of a type.

    Reached as client.map.
    """

    def __init__(self, client) -> None:
        super().__init__(client)
        self.pacer = MapAreaPacer(lambda: client.config.map_tiles_per_second)

    def scan_map_area(
        self, x1: int, y1: int, x2: int, y2: int, kingdom: Kingdom = Kingdom.GREEN, *, timeout: float = 5.0
    ) -> GetMapAreaResponse:
        """
        Scan a specific area of the map.

        As the game client does, a side spanning more than 100 tiles past its
        first corner is cut to 100 tiles: ``x2`` becomes ``x1 + 99``, and ``y2`` the
        same way. The session leaves the castle it had joined; see the module docstring.

        Args:
            x1: Left X coordinate
            y1: Top Y coordinate
            x2: Right X coordinate
            y2: Bottom Y coordinate
            kingdom: Kingdom to scan
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleWorldmapData.updateAreaRange`` (bundle line 19006)
        """
        if x2 - x1 > MAX_AREA_SPAN:
            x2 = x1 + MAX_AREA_SPAN - 1
        if y2 - y1 > MAX_AREA_SPAN:
            y2 = y1 + MAX_AREA_SPAN - 1
        request = GetMapAreaRequest(kingdom=kingdom, x1=x1, y1=y1, x2=x2, y2=y2)
        self.pacer.wait(request.tiles)
        return self.request(request, GetMapAreaResponse, timeout=timeout)

    def scan_around(
        self,
        x: int,
        y: int,
        radius: int,
        kingdom: Kingdom,
        item_types: list[MapItemType] | None = None,
        *,
        timeout: float = 5.0,
    ) -> ScanResult:
        """
        The map rows within ``radius`` tiles of ``(x, y)``, nearest first.

        A row is kept when :meth:`MapAreaItem.distance_to` the position is at most
        ``radius``; ``item_types`` keeps only those types, None every type, and rows
        without a player owner are kept too. A box up to 101 tiles a side
        (``radius`` 50) is one ``gaa`` request; a larger one is read chunk by chunk
        through :meth:`scan_chunks`, whose chunks that failed are in
        ``failed_chunks``, and which leaves out position-only rows of three fields.
        Either way each read waits on the account's map pacer. The session leaves
        the castle it had joined; see the module docstring.

        Args:
            x: Map x to measure from
            y: Map y to measure from
            radius: Greatest distance in tiles
            kingdom: Kingdom to scan
            item_types: Area types to keep; None for every type
            timeout: Timeout in seconds of each request

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`,
                for the one request of a small box
        """
        if 2 * radius <= MAX_AREA_SPAN:
            response = self.scan_map_area(x - radius, y - radius, x + radius, y + radius, kingdom, timeout=timeout)
            wanted = set(item_types) if item_types else None
            scan = ScanResult(
                items=[item for item in response.items if wanted is None or item.item_type in wanted],
                objects={owner.owner_id: owner for owner in response.owners if owner.owner_id},
                kingdom=kingdom,
            )
        else:
            scanner = MapScanner(self.client)
            low_x, low_y = scanner.chunk_for_position(x - radius, y - radius)
            high_x, high_y = scanner.chunk_for_position(x + radius, y + radius)
            chunks = [(cx, cy) for cx in range(low_x, high_x + 1) for cy in range(low_y, high_y + 1)]
            scan = scanner.scan_chunks(
                kingdom,
                chunks,
                item_types or [],
                request_timeout=timeout,
                include_unowned_types=set(item_types or MapItemType),
            )
        nearby = sorted(
            (item for item in scan.items if item.distance_to(x, y) <= radius), key=lambda item: item.distance_to(x, y)
        )
        return scan._replace(items=nearby)

    def scan_kingdom(
        self,
        kingdom: Kingdom = Kingdom.GREEN,
        item_types: list[MapItemType] | None = None,
        *,
        request_timeout: float = 5.0,
        chunk_delay: float = 0.0,
        include_unowned_types: set[MapItemType] | None = None,
        cancel: threading.Event | None = None,
        on_chunk: ChunkHandler | None = None,
        timeout: float = 300.0,
    ) -> ScanResult:
        """Scan a kingdom map. See MapScanner.scan_kingdom; the session leaves its castle."""
        return MapScanner(self.client).scan_kingdom(
            kingdom,
            item_types,
            request_timeout=request_timeout,
            chunk_delay=chunk_delay,
            include_unowned_types=include_unowned_types,
            cancel=cancel,
            on_chunk=on_chunk,
            timeout=timeout,
        )

    def scan_chunks(
        self,
        kingdom: Kingdom,
        chunks: list[tuple[int, int]],
        item_types: list[MapItemType] | None = None,
        *,
        request_timeout: float = 5.0,
        chunk_delay: float = 0.0,
        include_unowned_types: set[MapItemType] | None = None,
        cancel: threading.Event | None = None,
        on_chunk: ChunkHandler | None = None,
        timeout: float = 300.0,
    ) -> ScanResult:
        """Scan an explicit chunk list (no BFS). See MapScanner.scan_chunks; the session leaves its castle."""
        return MapScanner(self.client).scan_chunks(
            kingdom,
            chunks,
            item_types,
            request_timeout=request_timeout,
            chunk_delay=chunk_delay,
            include_unowned_types=include_unowned_types,
            cancel=cancel,
            on_chunk=on_chunk,
            timeout=timeout,
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

    def find_next_tower(self, *, timeout: float = 5.0) -> FindNextTowerResponse | None:
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
            if e.error is GGEError.NO_PLAYER_FOUND:
                return None
            raise
        response.area.items = parse_area_rows([item.raw_data for item in response.area.items], kingdom)[0]
        return response
