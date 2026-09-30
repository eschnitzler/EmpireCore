"""
Map service: map areas and kingdom scans.

Reading the map moves the session off the castle it had joined: a
castle-scoped read after a scan fails with NOT_IN_OWNED_CASTLE until the
castle is joined again. ``client.army`` methods join it themselves; anything
else castle-scoped needs ``client.castle.select`` first.
"""

from __future__ import annotations

from empire_core.enums import Kingdom, MapItemType
from empire_core.map.models.areas import GetMapAreaRequest, GetMapAreaResponse
from empire_core.map.scanner import MapScanner, ScanResult
from empire_core.services.base import BaseService, register_service


@register_service("map")
class MapService(BaseService):
    """
    Service for reading the world map.

    Accessible via client.map after auto-registration.
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
        request = GetMapAreaRequest(KID=kingdom, AX1=x1, AY1=y1, AX2=x2, AY2=y2)
        return self.request(request, GetMapAreaResponse, timeout=timeout)

    def scan_kingdom(
        self,
        kingdom: Kingdom = Kingdom.GREEN,
        item_types: list[MapItemType] | None = None,
        timeout: float = 300.0,
        request_timeout: float = 5.0,
        chunk_delay: float = 0.2,
        include_unowned_types: set[MapItemType] | None = None,
    ) -> ScanResult:
        """Scan a kingdom map. See MapScanner.scan_kingdom; the session leaves its castle."""
        return MapScanner(self.client).scan_kingdom(
            kingdom,
            item_types,
            timeout,
            request_timeout,
            chunk_delay,
            include_unowned_types=include_unowned_types,
        )

    def scan_chunks(
        self,
        kingdom: Kingdom,
        chunks: list[tuple[int, int]],
        item_types: list[MapItemType] | None = None,
        timeout: float = 300.0,
        request_timeout: float = 5.0,
        chunk_delay: float = 0.2,
        include_unowned_types: set[MapItemType] | None = None,
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
        )
