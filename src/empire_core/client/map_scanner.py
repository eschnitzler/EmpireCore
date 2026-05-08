import logging
import time
from typing import TYPE_CHECKING, NamedTuple

from empire_core.protocol.models.map import GetMapAreaRequest, Kingdom, MapAreaItem, MapItemType, MapObject

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class ScanResult(NamedTuple):
    items: list[MapAreaItem]
    objects: dict[int, MapObject]


class MapScanner:
    """Utility class to scan kingdom maps with dynamic boundary detection."""

    CHUNK_SIZE = 90  # Max allowed by GGE server
    MAX_COORD = 20  # Max chunk coordinate (20 * 90 = 1800, well beyond any map)

    def __init__(self, client: "EmpireClient"):
        self.client = client

    def _chunk_bounds(self, cx: int, cy: int) -> tuple[int, int, int, int]:
        """Convert chunk coords to world bounds."""
        x1 = cx * self.CHUNK_SIZE
        y1 = cy * self.CHUNK_SIZE
        return (x1, y1, x1 + self.CHUNK_SIZE, y1 + self.CHUNK_SIZE)

    def _process_chunk(
        self,
        cx: int,
        cy: int,
        kingdom: Kingdom,
        filter_types: set[MapItemType] | None,
        collected_items: list[MapAreaItem],
        collected_objects: dict[int, MapObject],
        request_timeout: float,
    ) -> bool:
        """
        Request a single chunk and process the response.
        Returns True if chunk had content, False if empty.
        """
        x1, y1, x2, y2 = self._chunk_bounds(cx, cy)
        request = GetMapAreaRequest(KID=kingdom, AX1=x1, AY1=y1, AX2=x2, AY2=y2)

        # Send and wait for response
        try:
            self.client.send(request, wait=False)
            response = self.client.connection.wait_for("gaa", timeout=request_timeout)
        except (TimeoutError, RuntimeError) as e:
            logger.warning(f"Chunk ({cx}, {cy}) request failed: {e}. Retrying...")

            # Check connection before retry
            if not self.client.connection.connected:
                logger.error("Connection lost during scan")
                return False

            # Retry once
            try:
                time.sleep(0.1)  # Wait a bit before retry
                self.client.send(request, wait=False)
                response = self.client.connection.wait_for("gaa", timeout=request_timeout)
            except Exception as e2:
                logger.error(f"Chunk ({cx}, {cy}) failed after retry: {e2}")
                return False

        if not isinstance(response.payload, dict):
            return False

        if response.error_code == 337:
            raise RuntimeError("ADDITIONAL_KINGDOM_NOT_UNLOCKED")

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

        return has_content

    def scan_kingdom(
        self,
        kingdom: Kingdom = Kingdom.GREEN,
        item_types: list[MapItemType] | None = None,
        timeout: float = 300.0,
        request_timeout: float = 5.0,
    ) -> ScanResult:
        """
        Scan a kingdom map with dynamic boundary detection.
        Uses BFS expansion from the bot's castle position.
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
        chunk_has_content: dict[tuple[int, int], bool] = {}

        # BFS queue - process one chunk at a time
        queue: list[tuple[int, int]] = [(start_cx, start_cy)]
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

            # Add small delay to prevent rate limiting/disconnects
            time.sleep(0.01)

            cx, cy = queue.pop(0)

            # Skip if already visited or out of bounds
            if (cx, cy) in visited:
                continue
            if cx < 0 or cy < 0 or cx > self.MAX_COORD or cy > self.MAX_COORD:
                continue

            visited.add((cx, cy))
            total_requests += 1

            # Process this chunk
            has_content = self._process_chunk(
                cx, cy, kingdom, filter_types, collected_items, collected_objects, request_timeout
            )
            chunk_has_content[(cx, cy)] = has_content

            # Update bounds tracking
            if has_content:
                min_x_found = min(min_x_found, cx)
                max_x_found = max(max_x_found, cx)
                min_y_found = min(min_y_found, cy)
                max_y_found = max(max_y_found, cy)

            # Add neighbors to queue (BFS expansion)
            neighbors = [(cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)]
            for nx, ny in neighbors:
                if (nx, ny) not in visited:
                    # Always explore if within 2 chunks of known content
                    if min_x_found - 2 <= nx <= max_x_found + 2 and min_y_found - 2 <= ny <= max_y_found + 2:
                        queue.append((nx, ny))
                    # Or if this chunk had content, explore neighbors
                    elif has_content:
                        queue.append((nx, ny))

            # Log progress periodically
            if total_requests % 50 == 0:
                elapsed = time.time() - start_time
                logger.debug(
                    f"Scan progress: {total_requests} chunks, {len(collected_items)} items, {elapsed:.1f}s elapsed"
                )

        elapsed = time.time() - start_time
        logger.debug(
            f"Kingdom {kingdom.name} scan complete. "
            f"Scanned {total_requests} chunks in {elapsed:.1f}s, "
            f"found {len(collected_items)} items. "
            f"Map bounds: x=[{min_x_found * self.CHUNK_SIZE}-{(max_x_found + 1) * self.CHUNK_SIZE}] "
            f"y=[{min_y_found * self.CHUNK_SIZE}-{(max_y_found + 1) * self.CHUNK_SIZE}]"
        )
        return ScanResult(items=collected_items, objects=collected_objects)
