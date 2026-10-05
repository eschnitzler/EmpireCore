"""Kingdom scans: breadth-first discovery and targeted re-scans of known chunks."""

import logging
import threading
import time
from collections import deque
from collections.abc import Iterable
from typing import Any, NamedTuple, Protocol

from empire_core.enums import Kingdom, MapItemType
from empire_core.exceptions import CommandError, EmpireTimeoutError, NetworkError
from empire_core.map.models.areas import GetMapAreaRequest, MapObject
from empire_core.map.models.items import CASTLE_ROW_TYPES, MapAreaItem, castle_row_player
from empire_core.protocol.errors import GGEError
from empire_core.protocol.js import js_int, js_truthy
from empire_core.protocol.packet import Packet
from empire_core.utils.cancel import sleep_unless_cancelled

logger = logging.getLogger(__name__)


def _truncated_repr(value: object, limit: int = 200) -> str:
    """repr() capped at ``limit`` characters, for log-safe payload samples."""
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "...(truncated)"


def _has_no_player(is_plot_row: Any, player_id: Any) -> bool | None:
    """
    Whether a map row is a free castle plot, or names an NPC or nobody as its owner; a camp names no owner.

    ``player_id`` is a plot row's occupier, else the row's owner, before or after
    validation: None when it is not yet an int or None, so only the built row can tell.
    See :attr:`MapAreaItem.is_relocating` and :attr:`MapAreaItem.has_player_owner`.
    """
    if is_plot_row:
        if player_id is None:
            return True
        return player_id <= -1 if type(player_id) is int else None
    if player_id is None:
        return False
    return player_id <= 0 if type(player_id) is int else None


class ScanResult(NamedTuple):
    items: list[MapAreaItem]
    objects: dict[int, MapObject]
    kingdom: Kingdom
    failed_chunks: tuple[tuple[int, int], ...] = ()
    # Chunks that responded successfully AND contained map items. Feed these
    # back into scan_chunks() to re-scan a known region without paying for
    # BFS discovery of the empty boundary again.
    content_chunks: tuple[tuple[int, int], ...] = ()


_Chunk = tuple[int, int]
_TopologyKey = tuple[str, str, Kingdom]


class KingdomTopology:
    """
    The chunks with map content in each kingdom, from complete discoveries, shared by every scanner.

    Keyed by world, the game URL and zone a client logs into, and kingdom:
    the map belongs to the world, not to an account, so every client on a
    world, from a pool or not, reuses one discovery of a kingdom. Only a
    discovery that scanned every chunk it found (no failed chunk, no
    timeout, not cancelled) is stored; when several run at once, the last
    to finish replaces the others.

    A discovery is a BFS from the scanning account's own castle in that
    kingdom (the map center without one) that stops two empty chunks past
    the content it found, so it holds the region connected to that castle.
    An account whose castle lies in a region the stored discovery did not
    reach needs ``scan_kingdom(refresh_topology=True)``, or a topology of
    its own.

    An entry stays until ``refresh_topology=True`` replaces it or
    :meth:`clear`; the client takes the map's size from the game constants
    (``ggc`` ``SX``/``SY``, ``GGCCommand.executeCommand``, bundle line
    120541, and ``nfo``, bundle line 120802, through
    ``ClientConstCastle.setWorldmapSizeViaGGC``, bundle line 985), which the
    library does not read, so a world that grows is not noticed by itself.
    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chunks: dict[_TopologyKey, tuple[_Chunk, ...]] = {}

    def get(self, key: _TopologyKey) -> tuple[_Chunk, ...] | None:
        """The content chunks a complete discovery of ``key`` found, or None."""
        with self._lock:
            return self._chunks.get(key)

    def store(self, key: _TopologyKey, chunks: tuple[_Chunk, ...]) -> None:
        """Keep the content chunks of a complete discovery of ``key``, replacing any before."""
        with self._lock:
            self._chunks[key] = chunks

    def clear(self) -> None:
        """Forget every kingdom, so each next scan_kingdom discovers its map again."""
        with self._lock:
            self._chunks.clear()


#: The process-wide topology every MapScanner uses unless given another.
kingdom_topology = KingdomTopology()


class _ChunkResult(NamedTuple):
    ok: bool
    has_content: bool


class _Connection(Protocol):
    @property
    def connected(self) -> bool: ...

    room_id: int

    def request(self, data: str, cmd_id: str, timeout: float = 5.0) -> Packet: ...


class _Castle(Protocol):
    @property
    def kingdom_id(self) -> Kingdom: ...
    @property
    def x(self) -> int: ...
    @property
    def y(self) -> int: ...


class _State(Protocol):
    def get_castles(self) -> Iterable[_Castle]: ...


class _Config(Protocol):
    game_url: str
    default_zone: str


class _Client(Protocol):
    """What the scanner uses of EmpireClient, which the map area can't import."""

    @property
    def config(self) -> _Config: ...
    @property
    def connection(self) -> _Connection: ...
    def request_packet(self, request: GetMapAreaRequest, response_command: str, timeout: float = 5.0) -> Packet: ...
    @property
    def state(self) -> _State: ...


class MapScanner:
    """Utility class to scan kingdom maps with dynamic boundary detection."""

    CHUNK_SIZE = 90  # Tiles a side; the client asks for at most 100 (GetMapAreaRequest)
    MAX_COORD = 20  # Max chunk coordinate (20 * 90 = 1800, well beyond any map)
    # A chunk whose request times out, fails on the network or is refused with a
    # cooldown is asked again this many times, waiting RETRY_BACKOFF, then twice that.
    CHUNK_RETRIES = 2
    RETRY_BACKOFF = 0.5

    def __init__(self, client: _Client, topology: KingdomTopology = kingdom_topology) -> None:
        self.client = client
        self.topology = topology

    def _chunk_bounds(self, cx: int, cy: int) -> tuple[int, int, int, int]:
        """Convert chunk coords to world bounds (inclusive)."""
        x1 = cx * self.CHUNK_SIZE
        y1 = cy * self.CHUNK_SIZE
        # Bounds are inclusive; ending at x1 + CHUNK_SIZE would re-fetch the
        # first row/column of the next chunk and duplicate boundary items.
        return (x1, y1, x1 + self.CHUNK_SIZE - 1, y1 + self.CHUNK_SIZE - 1)

    def _request_chunk(self, request: GetMapAreaRequest, request_timeout: float) -> Packet:
        """Send a chunk request and wait for the matching gaa response."""
        return self.client.request_packet(request, "gaa", timeout=request_timeout)

    def _get_kingdom_start_position(self, kingdom: Kingdom) -> tuple[int, int]:
        """
        Get a starting position for scanning a kingdom.

        Uses the bot's own castle position in the target kingdom if available.
        Falls back to map center (650, 650) if no castle found.

        Args:
            kingdom: The kingdom to find a starting position for

        Returns:
            (x, y) tuple for the starting position
        """
        if self.client.state:
            # Find a castle in the target kingdom
            for castle in self.client.state.get_castles():
                if castle.kingdom_id == kingdom:
                    return (castle.x, castle.y)

        # No castle in this kingdom - use map center as fallback
        return (650, 650)

    def _unscanned_chunks(self, queue: deque[tuple[int, int]], visited: set[tuple[int, int]]) -> list[tuple[int, int]]:
        """
        Chunks still queued for a scan that was cut short.

        Reported in ``failed_chunks`` so an aborted scan is never mistaken
        for a complete one. Entries the loop would have skipped anyway
        (already visited, duplicated, out of range) are left out.
        """
        remaining: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for cx, cy in queue:
            if (cx, cy) in visited or (cx, cy) in seen:
                continue
            if cx < 0 or cy < 0 or cx > self.MAX_COORD or cy > self.MAX_COORD:
                continue
            seen.add((cx, cy))
            remaining.append((cx, cy))
        return remaining

    def _process_chunk(
        self,
        cx: int,
        cy: int,
        kingdom: Kingdom,
        filter_types: set[MapItemType] | None,
        collected_items: list[MapAreaItem],
        collected_objects: dict[int, MapObject],
        request_timeout: float,
        include_unowned_types: set[MapItemType] | None = None,
        cancel: threading.Event | None = None,
    ) -> _ChunkResult:
        """
        Request a single chunk and process the response.

        Returns (ok, has_content). ``ok=False`` means the request failed
        (as opposed to succeeding with an empty area), or ``cancel`` was set
        before a retry.
        """
        x1, y1, x2, y2 = self._chunk_bounds(cx, cy)
        request = GetMapAreaRequest(kingdom=kingdom, x1=x1, y1=y1, x2=x2, y2=y2)

        for attempt in range(self.CHUNK_RETRIES + 1):
            last = attempt == self.CHUNK_RETRIES
            try:
                response = self._request_chunk(request, request_timeout)
            except (EmpireTimeoutError, NetworkError) as e:
                if not self.client.connection.connected:
                    logger.error(f"Connection lost during scan: {e}")
                    return _ChunkResult(ok=False, has_content=False)
                if last:
                    logger.error(f"Chunk ({cx}, {cy}) failed after {attempt} retries: {e}")
                    return _ChunkResult(ok=False, has_content=False)
                logger.warning(f"Chunk ({cx}, {cy}) request failed: {e}. Retrying...")
            else:
                if last or not GGEError.from_code(response.error_code).is_cooldown:
                    break
                logger.warning(f"Chunk ({cx}, {cy}) refused with a cooldown. Retrying...")
            if sleep_unless_cancelled(self.RETRY_BACKOFF * 2**attempt, cancel):
                return _ChunkResult(ok=False, has_content=False)

        if response.error_code == 337:
            raise CommandError("gaa", 337)  # ADDITIONAL_KINGDOM_NOT_UNLOCKED

        if response.error_code:
            # Any other non-zero code (cooldown, rate limiting, map not
            # available, ...) still parses into a dict payload with no AI
            # array, so without this check the chunk would be mistaken for a
            # legitimately empty area and quietly dropped from the scan.
            error_name = GGEError.from_code(response.error_code).name
            logger.warning(f"Chunk ({cx}, {cy}) failed with server error {error_name} ({response.error_code})")
            return _ChunkResult(ok=False, has_content=False)

        if not isinstance(response.payload, dict):
            return _ChunkResult(ok=False, has_content=False)

        ai_array = response.payload.get("AI", [])
        oi_array = response.payload.get("OI", [])
        has_content = len(ai_array) > 0

        # Collect matching items. One malformed entry must not cost us the
        # whole chunk (or, in scan_kingdom, every chunk collected so far), so
        # parse defensively -- but count and report what was dropped: if the
        # server reshapes these entries, every chunk would otherwise come
        # back ok=True with zero items, and the schema drift would hide
        # behind a "successful" empty scan. Per-entry detail stays at debug;
        # each chunk with skips gets one warning with counts and a sample.
        skipped_objects = 0
        skipped_items = 0
        sample: object = None

        for raw_obj in oi_array:
            if not isinstance(raw_obj, dict):
                skipped_objects += 1
                sample = raw_obj if sample is None else sample
                logger.debug("Chunk (%s, %s): skipping malformed map object %r", cx, cy, raw_obj)
                continue
            if not js_truthy(raw_obj.get("OID")):
                # CastleOtherPlayerData.parseOwnerInfo reads no record without an OID
                continue
            try:
                obj = MapObject.model_validate(raw_obj)
            except Exception as e:
                skipped_objects += 1
                sample = raw_obj if sample is None else sample
                logger.debug("Chunk (%s, %s): skipping invalid map object %r: %s", cx, cy, raw_obj, e)
                continue
            oid = obj.owner_id
            if oid:
                collected_objects[oid] = obj

        for raw_item in ai_array:
            # Short entries are normal, not drift: most of a live AI array is
            # entries like [31, 0, 996] carrying no owner field, and they have
            # always been skipped here. Counting them as suspected drift buried
            # the real signal under a thousand warnings per chunk.
            if isinstance(raw_item, list) and len(raw_item) < 4:
                continue
            if not isinstance(raw_item, list):
                skipped_items += 1
                sample = raw_item if sample is None else sample
                logger.debug("Chunk (%s, %s): skipping malformed map item %r", cx, cy, raw_item)
                continue
            # filter_types is None only when the caller disabled filtering; rows of
            # other types are not read at all
            area_type = js_int(raw_item[0])
            if filter_types is not None and area_type not in filter_types:
                continue
            unowned_wanted = include_unowned_types is not None and area_type in include_unowned_types
            # Free plots and NPC-owned rows are skipped unless their type is explicitly included,
            # decided before the row is built where its ids allow: a chunk holds hundreds of them
            try:
                if area_type in CASTLE_ROW_TYPES:
                    no_player = _has_no_player(*castle_row_player(raw_item))
                    if no_player and not unowned_wanted:
                        continue
                    item = MapAreaItem.from_list(raw_item, kingdom)
                else:
                    values = MapAreaItem.row_values(raw_item, kingdom)
                    no_player = _has_no_player(False, values.get("owner_id"))
                    if no_player and not unowned_wanted:
                        continue
                    item = MapAreaItem(**values)
            except ValueError as e:
                skipped_items += 1
                sample = raw_item if sample is None else sample
                logger.debug("Chunk (%s, %s): skipping invalid map item %r: %s", cx, cy, raw_item, e)
                continue
            if (
                no_player is None
                and not unowned_wanted
                and _has_no_player(item.is_plot_row, item.occupier_id if item.is_plot_row else item.owner_id)
            ):
                continue
            collected_items.append(item)

        if skipped_items or skipped_objects:
            parts = []
            if skipped_items:
                parts.append(f"{skipped_items}/{len(ai_array)} map items")
            if skipped_objects:
                parts.append(f"{skipped_objects}/{len(oi_array)} map objects")
            logger.warning(
                f"Chunk ({cx}, {cy}): skipped {' and '.join(parts)} that did not parse "
                f"(server schema drift?); sample: {_truncated_repr(sample)}"
            )

        return _ChunkResult(ok=True, has_content=has_content)

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
        refresh_topology: bool = False,
    ) -> ScanResult:
        """
        Scan a kingdom map with dynamic boundary detection.
        Uses BFS expansion from the bot's castle position.

        The first scan of a kingdom discovers its map by BFS; once one has
        scanned every chunk it found, later scans of that kingdom on the same
        world, from any client in the process, scan only the chunks it found
        with content, as :meth:`scan_chunks` would (see
        :class:`KingdomTopology`). ``refresh_topology`` discovers the map
        again and replaces what was stored. Scans that find nothing stored
        each discover, at the same time if they run at once, and the last
        complete one is kept. A discovery starts at this account's castle in
        the kingdom, so one stored from another account's castle may miss a
        region not connected to it; ``refresh_topology`` covers that.

        ``item_types`` selects which map items are collected, and its two
        empty-ish values mean opposite things — the sentinel is inverted,
        so read this carefully:

        - ``None`` (the default) is the *most* restrictive: it collects
          player main castles only (``MapItemType.CASTLE``).
        - ``[]`` (empty list) is the *least* restrictive: it disables
          filtering and collects every item type.
        - a non-empty list collects exactly those types.

        In every case free castle plots and rows whose owner is an NPC or
        nobody (``owner_id`` not above 0, such as an unclaimed outpost) are
        skipped unless their type is in ``include_unowned_types``. A castle on
        the move (:attr:`MapAreaItem.is_relocating`) is kept, and so is a row
        that names no owner at all, such as an NPC camp. Rows shorter than
        ``[type, x, y, id]`` (placeholders, inactive event camps) are skipped.
        Every item and ``ScanResult.kingdom`` carry the scanned kingdom.

        A scan moves the session off the castle it had joined; see
        :class:`~empire_core.map.service.MapService`.

        Chunks that fail even after a retry are reported in
        ``ScanResult.failed_chunks`` so callers can tell a partial scan
        from a complete one. The same applies to chunks left unscanned
        when the overall ``timeout`` expires or the connection drops: an
        empty ``failed_chunks`` means the scan really did finish.

        ``chunk_delay`` waits that many seconds before each ``gaa`` request;
        by default there is no wait, as the client does not pace its map
        requests either. A live scan of 289 chunks at about 17 requests a
        second saw no refusal and no dropped connection. A chunk that times
        out, fails on the network or is refused with a cooldown is asked
        again after a short backoff (``CHUNK_RETRIES``, ``RETRY_BACKOFF``).

        Setting ``cancel`` stops the scan before its next chunk and returns
        what it has, the chunks not scanned in ``failed_chunks``, as a timeout
        does. It is looked at between requests, never during one: the chunk
        in flight ends with its reply or ``request_timeout``, so its reply
        cannot reach the next ``gaa`` request, and a cancel takes at most one
        chunk.
        """
        # None means castles only (type 1 = player main castles)
        if item_types is None:
            item_types = [MapItemType.CASTLE]
        config = self.client.config
        key = (config.game_url, config.default_zone, kingdom)
        known = None if refresh_topology else self.topology.get(key)
        if known is None:
            result = self._discover(
                kingdom, item_types, timeout, request_timeout, chunk_delay, include_unowned_types, cancel
            )
            if result.content_chunks and not result.failed_chunks:
                self.topology.store(key, result.content_chunks)
            return result
        logger.debug(f"Scanning kingdom {kingdom!r} over the {len(known)} chunks its discovery found with content")
        return self.scan_chunks(
            kingdom,
            list(known),
            item_types,
            timeout,
            request_timeout,
            chunk_delay,
            include_unowned_types,
            cancel=cancel,
        )

    def _discover(
        self,
        kingdom: Kingdom,
        item_types: list[MapItemType],
        timeout: float,
        request_timeout: float,
        chunk_delay: float,
        include_unowned_types: set[MapItemType] | None,
        cancel: threading.Event | None,
    ) -> ScanResult:
        """Discover a kingdom's map by BFS from the own castle there; see :meth:`scan_kingdom`."""
        start_x, start_y = self._get_kingdom_start_position(kingdom)
        start_cx, start_cy = start_x // self.CHUNK_SIZE, start_y // self.CHUNK_SIZE

        # An empty list means no filtering at all
        filter_types = set(item_types) if item_types else None

        filter_desc = f"types={list(item_types)}" if item_types else "all types"
        logger.debug(f"Scanning kingdom {kingdom!r} from chunk ({start_cx}, {start_cy}) for {filter_desc}...")

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
                failed_chunks.extend(self._unscanned_chunks(queue, visited))
                break

            if chunk_delay > 0:
                sleep_unless_cancelled(chunk_delay, cancel)
            if cancel is not None and cancel.is_set():
                logger.info(f"Kingdom scan cancelled after {total_requests} requests")
                failed_chunks.extend(self._unscanned_chunks(queue, visited))
                break

            cx, cy = queue.popleft()

            if (cx, cy) in visited:
                continue
            if cx < 0 or cy < 0 or cx > self.MAX_COORD or cy > self.MAX_COORD:
                continue

            visited.add((cx, cy))
            total_requests += 1

            # Process this chunk
            result = self._process_chunk(
                cx,
                cy,
                kingdom,
                filter_types,
                collected_items,
                collected_objects,
                request_timeout,
                include_unowned_types=include_unowned_types,
                cancel=cancel,
            )

            if not result.ok:
                failed_chunks.append((cx, cy))
                if not self.client.connection.connected:
                    logger.error("Aborting scan: connection lost")
                    failed_chunks.extend(self._unscanned_chunks(queue, visited))
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
            logger.log(
                logging.DEBUG if cancel is not None and cancel.is_set() else logging.WARNING,
                f"Kingdom scan incomplete: {len(failed_chunks)} chunk(s) failed: {failed_chunks[:10]}",
            )
        logger.debug(
            f"Kingdom {kingdom!r} scan complete. "
            f"Scanned {total_requests} chunks in {elapsed:.1f}s, "
            f"found {len(collected_items)} items. "
            f"Map bounds: x=[{min_x_found * self.CHUNK_SIZE}-{(max_x_found + 1) * self.CHUNK_SIZE}] "
            f"y=[{min_y_found * self.CHUNK_SIZE}-{(max_y_found + 1) * self.CHUNK_SIZE}]"
        )
        return ScanResult(
            items=collected_items,
            objects=collected_objects,
            kingdom=kingdom,
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
        chunk_delay: float = 0.0,
        include_unowned_types: set[MapItemType] | None = None,
        *,
        cancel: threading.Event | None = None,
    ) -> ScanResult:
        """
        Scan an explicit list of chunks — no BFS discovery.

        Use this to re-scan a known region cheaply: run scan_kingdom()
        once to discover the map, then feed its ``content_chunks`` back
        here on subsequent scans. Also useful for targeted scans (e.g.
        only the chunks around known castle coordinates via
        ``chunk_for_position``).

        ``item_types`` behaves exactly as in scan_kingdom(), inverted
        sentinel included: ``None`` (the default) collects player main
        castles only, ``[]`` disables filtering and collects every type,
        and a non-empty list collects exactly those types.
        ``include_unowned_types`` also matches scan_kingdom(): types listed
        there are collected even when they have no player owner.

        Chunks are deduplicated and out-of-range coordinates skipped.
        Unscanned chunks left over when ``timeout`` hits or ``cancel`` is set
        are reported in ``failed_chunks``; ``cancel`` is looked at between
        chunks, as in scan_kingdom().
        """
        # None means castles only; an empty list means no filtering at all.
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

            if chunk_delay > 0:
                sleep_unless_cancelled(chunk_delay, cancel)
            if cancel is not None and cancel.is_set():
                logger.info(f"Chunk scan cancelled after {i} of {len(todo)} chunks")
                failed_chunks.extend(todo[i:])
                break

            result = self._process_chunk(
                cx,
                cy,
                kingdom,
                filter_types,
                collected_items,
                collected_objects,
                request_timeout,
                include_unowned_types=include_unowned_types,
                cancel=cancel,
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
            logger.log(
                logging.DEBUG if cancel is not None and cancel.is_set() else logging.WARNING,
                f"Chunk scan incomplete: {len(failed_chunks)} chunk(s) failed: {failed_chunks[:10]}",
            )
        return ScanResult(
            items=collected_items,
            objects=collected_objects,
            kingdom=kingdom,
            failed_chunks=tuple(failed_chunks),
            content_chunks=tuple(content_chunks),
        )

    def chunk_for_position(self, x: int, y: int) -> tuple[int, int]:
        """Map world coordinates to the chunk that contains them."""
        return (x // self.CHUNK_SIZE, y // self.CHUNK_SIZE)
