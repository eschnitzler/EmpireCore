import logging
import time
from collections import deque
from typing import TYPE_CHECKING, NamedTuple

from empire_core.exceptions import CommandError, EmpireTimeoutError, NetworkError
from empire_core.protocol.models.map import GetMapAreaRequest, Kingdom, MapAreaItem, MapItemType, MapObject

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class ScanResult(NamedTuple):
    items: list[MapAreaItem]
    objects: dict[int, MapObject]
    failed_chunks: tuple[tuple[int, int], ...] = ()
    # Chunks that responded successfully AND contained map items. Feed these
    # back into scan_chunks() to re-scan a known region without paying for
    # BFS discovery of the empty boundary again.
    content_chunks: tuple[tuple[int, int], ...] = ()


class _ChunkResult(NamedTuple):
    ok: bool
    has_content: bool


class MapScanner:
    """Utility class to scan kingdom maps with dynamic boundary detection."""

    CHUNK_SIZE = 90  # Max allowed by GGE server
    MAX_COORD = 20  # Max chunk coordinate (20 * 90 = 1800, well beyond any map)

    def __init__(self, client: "EmpireClient"):
        self.client = client

    def _chunk_bounds(self, cx: int, cy: int) -> tuple[int, int, int, int]:
        """Convert chunk coords to world bounds (inclusive)."""
        x1 = cx * self.CHUNK_SIZE
        y1 = cy * self.CHUNK_SIZE
        # Bounds are inclusive; ending at x1 + CHUNK_SIZE would re-fetch the
        # first row/column of the next chunk and duplicate boundary items.
        return (x1, y1, x1 + self.CHUNK_SIZE - 1, y1 + self.CHUNK_SIZE - 1)

    def _request_chunk(self, request: GetMapAreaRequest, request_timeout: float):
        """Send a chunk request and wait for the matching gaa response."""
        packet = request.to_packet(zone=self.client.config.default_zone)
        return self.client.connection.request(packet, "gaa", timeout=request_timeout)

    def _process_chunk(
        self,
        cx: int,
        cy: int,
        kingdom: Kingdom,
        filter_types: set[MapItemType] | None,
        collected_items: list[MapAreaItem],
        collected_objects: dict[int, MapObject],
        request_timeout: float,
    ) -> _ChunkResult:
        """
        Request a single chunk and process the response.

        Returns (ok, has_content). ``ok=False`` means the request failed
        (as opposed to succeeding with an empty area).
        """
        x1, y1, x2, y2 = self._chunk_bounds(cx, cy)
        request = GetMapAreaRequest(KID=kingdom, AX1=x1, AY1=y1, AX2=x2, AY2=y2)

        try:
            response = self._request_chunk(request, request_timeout)
        except (EmpireTimeoutError, NetworkError) as e:
            logger.warning(f"Chunk ({cx}, {cy}) request failed: {e}. Retrying...")

            # Check connection before retry
            if not self.client.connection.connected:
                logger.error("Connection lost during scan")
                return _ChunkResult(ok=False, has_content=False)

            # Retry once
            try:
                time.sleep(0.1)  # Wait a bit before retry
                response = self._request_chunk(request, request_timeout)
            except Exception as e2:
                logger.error(f"Chunk ({cx}, {cy}) failed after retry: {e2}")
                return _ChunkResult(ok=False, has_content=False)

        if response.error_code == 337:
            raise CommandError("gaa", 337)  # ADDITIONAL_KINGDOM_NOT_UNLOCKED

        if not isinstance(response.payload, dict):
            return _ChunkResult(ok=False, has_content=False)

        ai_array = response.payload.get("AI", [])
        oi_array = response.payload.get("OI", [])
        has_content = len(ai_array) > 0

        # Collect matching items
        for raw_obj in oi_array:
            if isinstance(raw_obj, dict):
                try:
                    obj = MapObject.model_validate(raw_obj)
                    oid = obj.resolved_owner_id
                    if oid:
                        collected_objects[oid] = obj
                except Exception:
                    continue

        for raw_item in ai_array:
            if isinstance(raw_item, list) and len(raw_item) >= 4:
                item = MapAreaItem.from_list(raw_item)

                # Apply filter (None = collect all)
                if filter_types is None or item.item_type in filter_types:
                    # Skip unowned items (empty locations, unplaced flags, etc)
                    if item.owner_id == -1:
                        continue
                    collected_items.append(item)

        return _ChunkResult(ok=True, has_content=has_content)

    def scan_kingdom(
        self,
        kingdom: Kingdom = Kingdom.GREEN,
        item_types: list[MapItemType] | None = None,
        timeout: float = 300.0,
        request_timeout: float = 5.0,
        chunk_delay: float = 0.2,
    ) -> ScanResult:
        """
        Scan a kingdom map with dynamic boundary detection.
        Uses BFS expansion from the bot's castle position.

        Chunks that fail even after a retry are reported in
        ``ScanResult.failed_chunks`` so callers can tell a partial scan
        from a complete one.

        ``chunk_delay`` paces the ``gaa`` requests. A full-kingdom scan
        issues hundreds of requests back-to-back; sustained multi-minute
        request floods make the server drop the connection, so don't set
        this much lower unless you know the server tolerates it.
        """
        # Get starting position from bot's castle
        start_x, start_y = self.client._get_kingdom_start_position(kingdom)
        start_cx, start_cy = start_x // self.CHUNK_SIZE, start_y // self.CHUNK_SIZE

        # Default to castles (type 1 = player main castles)
        if item_types is None:
            item_types = [MapItemType.CASTLE]

        # Empty list means collect everything
        filter_types = set(item_types) if item_types else None

        filter_desc = f"types={list(item_types)}" if item_types else "all types"
        logger.debug(f"Scanning kingdom {kingdom.name} from chunk ({start_cx}, {start_cy}) for {filter_desc}...")

        # State tracking
        collected_items: list[MapAreaItem] = []
        collected_objects: dict[int, MapObject] = {}
        visited: set[tuple[int, int]] = set()
        failed_chunks: list[tuple[int, int]] = []
        content_chunks: list[tuple[int, int]] = []

        # BFS queue - process one chunk at a time
        queue: deque[tuple[int, int]] = deque([(start_cx, start_cy)])
        enqueued: set[tuple[int, int]] = {(start_cx, start_cy)}
        total_requests = 0
        start_time = time.time()

        # Track boundaries
        min_x_found = start_cx
        max_x_found = start_cx
        min_y_found = start_cy
        max_y_found = start_cy

        while queue:
            if time.time() - start_time > timeout:
                logger.warning(f"Kingdom scan timeout after {total_requests} requests")
                break

            # Pace requests to avoid rate limiting/disconnects
            time.sleep(chunk_delay)

            cx, cy = queue.popleft()

            if (cx, cy) in visited:
                continue
            if cx < 0 or cy < 0 or cx > self.MAX_COORD or cy > self.MAX_COORD:
                continue

            visited.add((cx, cy))
            total_requests += 1

            # Process this chunk
            result = self._process_chunk(
                cx, cy, kingdom, filter_types, collected_items, collected_objects, request_timeout
            )

            if not result.ok:
                failed_chunks.append((cx, cy))
                if not self.client.connection.connected:
                    logger.error("Aborting scan: connection lost")
                    break
            elif result.has_content:
                content_chunks.append((cx, cy))

            # A failed chunk is treated as if it had content so BFS keeps
            # expanding past it instead of silently truncating the region.
            has_content = result.has_content or not result.ok

            # Update bounds tracking
            if has_content:
                min_x_found = min(min_x_found, cx)
                max_x_found = max(max_x_found, cx)
                min_y_found = min(min_y_found, cy)
                max_y_found = max(max_y_found, cy)

            # Add neighbors to queue (BFS expansion)
            neighbors = [(cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)]
            for nx, ny in neighbors:
                if (nx, ny) in enqueued or (nx, ny) in visited:
                    continue
                # Always explore if within 2 chunks of known content
                if min_x_found - 2 <= nx <= max_x_found + 2 and min_y_found - 2 <= ny <= max_y_found + 2:
                    queue.append((nx, ny))
                    enqueued.add((nx, ny))
                # Or if this chunk had content, explore neighbors
                elif has_content:
                    queue.append((nx, ny))
                    enqueued.add((nx, ny))

            # Log progress periodically
            if total_requests % 50 == 0:
                elapsed = time.time() - start_time
                logger.debug(
                    f"Scan progress: {total_requests} chunks, {len(collected_items)} items, {elapsed:.1f}s elapsed"
                )

        elapsed = time.time() - start_time
        if failed_chunks:
            logger.warning(f"Kingdom scan incomplete: {len(failed_chunks)} chunk(s) failed: {failed_chunks[:10]}")
        logger.debug(
            f"Kingdom {kingdom.name} scan complete. "
            f"Scanned {total_requests} chunks in {elapsed:.1f}s, "
            f"found {len(collected_items)} items. "
            f"Map bounds: x=[{min_x_found * self.CHUNK_SIZE}-{(max_x_found + 1) * self.CHUNK_SIZE}] "
            f"y=[{min_y_found * self.CHUNK_SIZE}-{(max_y_found + 1) * self.CHUNK_SIZE}]"
        )
        return ScanResult(
            items=collected_items,
            objects=collected_objects,
            failed_chunks=tuple(failed_chunks),
            content_chunks=tuple(content_chunks),
        )

    def scan_chunks(
        self,
        kingdom: Kingdom,
        chunks: list[tuple[int, int]],
        item_types: list[MapItemType] | None = None,
        timeout: float = 300.0,
        request_timeout: float = 5.0,
        chunk_delay: float = 0.2,
    ) -> ScanResult:
        """
        Scan an explicit list of chunks — no BFS discovery.

        Use this to re-scan a known region cheaply: run scan_kingdom()
        once to discover the map, then feed its ``content_chunks`` back
        here on subsequent scans. Also useful for targeted scans (e.g.
        only the chunks around known castle coordinates via
        ``chunk_for_position``).

        Chunks are deduplicated and out-of-range coordinates skipped.
        Unscanned chunks left over when ``timeout`` hits are reported in
        ``failed_chunks``.
        """
        if item_types is None:
            item_types = [MapItemType.CASTLE]
        filter_types = set(item_types) if item_types else None

        collected_items: list[MapAreaItem] = []
        collected_objects: dict[int, MapObject] = {}
        failed_chunks: list[tuple[int, int]] = []
        content_chunks: list[tuple[int, int]] = []

        todo: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for cx, cy in chunks:
            if (cx, cy) in seen:
                continue
            seen.add((cx, cy))
            if cx < 0 or cy < 0 or cx > self.MAX_COORD or cy > self.MAX_COORD:
                continue
            todo.append((cx, cy))

        start_time = time.time()
        for i, (cx, cy) in enumerate(todo):
            if time.time() - start_time > timeout:
                logger.warning(f"Chunk scan timeout after {i} of {len(todo)} chunks")
                failed_chunks.extend(todo[i:])
                break

            # Pace requests to avoid rate limiting/disconnects
            time.sleep(chunk_delay)

            result = self._process_chunk(
                cx, cy, kingdom, filter_types, collected_items, collected_objects, request_timeout
            )

            if not result.ok:
                failed_chunks.append((cx, cy))
                if not self.client.connection.connected:
                    logger.error("Aborting scan: connection lost")
                    failed_chunks.extend(todo[i + 1 :])
                    break
            elif result.has_content:
                content_chunks.append((cx, cy))

        if failed_chunks:
            logger.warning(f"Chunk scan incomplete: {len(failed_chunks)} chunk(s) failed: {failed_chunks[:10]}")
        return ScanResult(
            items=collected_items,
            objects=collected_objects,
            failed_chunks=tuple(failed_chunks),
            content_chunks=tuple(content_chunks),
        )

    def chunk_for_position(self, x: int, y: int) -> tuple[int, int]:
        """Map world coordinates to the chunk that contains them."""
        return (x // self.CHUNK_SIZE, y // self.CHUNK_SIZE)
