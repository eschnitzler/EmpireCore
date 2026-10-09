"""Kingdom scans: breadth-first discovery and targeted re-scans of known chunks."""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from typing import Any, NamedTuple, Protocol

from empire_core.enums import GGEError, Kingdom, MapItemType
from empire_core.exceptions import CommandError, EmpireTimeoutError, NetworkError
from empire_core.map.models.areas import GetMapAreaRequest, MapObject
from empire_core.map.models.items import MapAreaItem
from empire_core.protocol.js import js_int, js_truthy
from empire_core.protocol.packet import Packet
from empire_core.utils.cancel import sleep_unless_cancelled

logger = logging.getLogger(__name__)


def _truncated_repr(value: object, limit: int = 200) -> str:
    """repr() capped at ``limit`` characters, for log-safe payload samples."""
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "...(truncated)"


def _log_incomplete(scan: str, failed_chunks: list[tuple[int, int]], *, cancelled: bool, connection_lost: bool) -> None:
    """
    One line for a scan that left chunks unscanned; the chunks themselves only at DEBUG.

    A cancel was asked for and a lost connection is already reported by the
    session, so neither warns; the chunks are in ``ScanResult.failed_chunks`` either way.
    """
    if not failed_chunks:
        return
    if connection_lost:
        logger.info(f"{scan} stopped by a lost connection: {len(failed_chunks)} chunk(s) not scanned")
    else:
        level = logging.DEBUG if cancelled else logging.WARNING
        logger.log(level, f"{scan} incomplete: {len(failed_chunks)} chunk(s) failed")
    logger.debug(f"{scan} failed chunks, first 10: {failed_chunks[:10]}")


def _has_no_player(is_plot_row: Any, occupier_id: Any, owner_id: Any) -> bool | None:
    """
    Whether a map row is a free castle plot, or names an NPC or nobody as its owner; a camp names no owner.

    Takes a row's values before or after validation: None when an id the
    answer depends on is not yet an int or None, so only the built row can tell.
    See :attr:`MapAreaItem.is_relocating` and :attr:`MapAreaItem.has_player_owner`.
    """
    if is_plot_row:
        if occupier_id is None:
            return True
        return occupier_id <= -1 if type(occupier_id) is int else None
    if owner_id is None:
        return False
    return owner_id <= 0 if type(owner_id) is int else None


class ScanResult(NamedTuple):
    """What a scan read: ``items`` and ``objects`` stay empty when it handed each chunk to ``on_chunk``."""

    items: list[MapAreaItem]
    objects: dict[int, MapObject]
    kingdom: Kingdom
    failed_chunks: tuple[tuple[int, int], ...] = ()
    # Chunks that responded successfully AND contained map items. Feed these
    # back into scan_chunks() to re-scan a known region without paying for
    # BFS discovery of the empty boundary again.
    content_chunks: tuple[tuple[int, int], ...] = ()


ChunkHandler = Callable[[tuple[int, int], list[MapAreaItem], dict[int, MapObject]], None]
"""Called with a chunk, the items kept from it and its owner records by player id; see ``on_chunk``."""


class _ChunkResult(NamedTuple):
    ok: bool
    has_content: bool
    items: list[MapAreaItem]
    objects: dict[int, MapObject]


_FAILED = _ChunkResult(ok=False, has_content=False, items=[], objects={})
_NOT_UNLOCKED = _ChunkResult(ok=False, has_content=False, items=[], objects={})


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


class _Client(Protocol):
    """What the scanner uses of EmpireClient, which the map area can't import."""

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

    def __init__(self, client: _Client) -> None:
        self.client = client

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

    def _castle_position(self, kingdom: Kingdom) -> tuple[int, int] | None:
        """Where the client's first castle in ``kingdom`` stands; None without one."""
        if self.client.state:
            for castle in self.client.state.get_castles():
                if castle.kingdom_id == kingdom:
                    return (castle.x, castle.y)
        return None

    def _process_chunk(
        self,
        cx: int,
        cy: int,
        kingdom: Kingdom,
        filter_types: set[MapItemType] | None,
        request_timeout: float,
        include_unowned_types: set[MapItemType] | None = None,
        cancel: threading.Event | None = None,
    ) -> _ChunkResult:
        """
        Request a single chunk and process the response.

        Returns (ok, has_content). ``ok=False`` means the request failed
        (as opposed to succeeding with an empty area), or ``cancel`` was set
        before a retry; ``_NOT_UNLOCKED`` that this client has not unlocked
        the kingdom.
        """
        x1, y1, x2, y2 = self._chunk_bounds(cx, cy)
        request = GetMapAreaRequest(kingdom=kingdom, x1=x1, y1=y1, x2=x2, y2=y2)

        for attempt in range(self.CHUNK_RETRIES + 1):
            last = attempt == self.CHUNK_RETRIES
            try:
                response = self._request_chunk(request, request_timeout)
            except (EmpireTimeoutError, NetworkError) as e:
                if not self.client.connection.connected:
                    logger.debug(f"Chunk ({cx}, {cy}) lost with the connection: {e}")
                    return _FAILED
                if last:
                    logger.warning(f"Chunk ({cx}, {cy}) failed after {attempt} retries: {e}")
                    return _FAILED
                logger.warning(f"Chunk ({cx}, {cy}) request failed: {e}. Retrying...")
            else:
                if last or not GGEError.from_code(response.error_code).is_cooldown:
                    break
                logger.warning(f"Chunk ({cx}, {cy}) refused with a cooldown. Retrying...")
            if sleep_unless_cancelled(self.RETRY_BACKOFF * 2**attempt, cancel):
                return _FAILED
        else:
            return _FAILED

        if response.error_code == GGEError.ADDITIONAL_KINGDOM_NOT_UNLOCKED:
            return _NOT_UNLOCKED

        if response.error_code:
            # Any other non-zero code (cooldown, rate limiting, map not
            # available, ...) still parses into a dict payload with no AI
            # array, so without this check the chunk would be mistaken for a
            # legitimately empty area and quietly dropped from the scan.
            error_name = GGEError.from_code(response.error_code).name
            logger.warning(f"Chunk ({cx}, {cy}) failed with server error {error_name} ({response.error_code})")
            return _FAILED

        if not isinstance(response.payload, dict):
            return _FAILED

        ai_array = response.payload.get("AI", [])
        oi_array = response.payload.get("OI", [])
        has_content = len(ai_array) > 0
        collected_items: list[MapAreaItem] = []
        collected_objects: dict[int, MapObject] = {}

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
            if filter_types is not None and js_int(raw_item[0]) not in filter_types:
                continue
            # Free plots and NPC-owned rows are skipped unless their type is explicitly included,
            # decided before the row is built where its ids allow: a chunk holds hundreds of them
            try:
                values = MapAreaItem.row_values(raw_item, kingdom)
                unowned_wanted = include_unowned_types is not None and values["item_type"] in include_unowned_types
                no_player = _has_no_player(values.get("is_plot_row"), values.get("occupier_id"), values.get("owner_id"))
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
                and _has_no_player(item.is_plot_row, item.occupier_id, item.owner_id)
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

        return _ChunkResult(ok=True, has_content=has_content, items=collected_items, objects=collected_objects)

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
        on_chunk: ChunkHandler | None = None,
    ) -> ScanResult:
        """
        Scan a kingdom map with dynamic boundary detection.
        Uses BFS expansion from the bot's castle position.

        ``item_types`` selects which map items are collected, and its two
        empty-ish values mean opposite things — the sentinel is inverted,
        so read this carefully:

        - ``None`` (the default) is the *most* restrictive: it collects
          player main castles only, ``MapItemType.CASTLE`` in the green
          kingdom and ``MapItemType.KINGDOM_CASTLE`` in the others.
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
        empty ``failed_chunks`` means the scan really did finish. A dropped
        connection is logged once, as a warning, by the session; the scan
        itself only notes at INFO how many chunks it left.

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

        ``on_chunk`` is called with each chunk that answered, empty ones too,
        as ``on_chunk((cx, cy), items, objects)``, and the scan keeps nothing
        of that chunk: ``ScanResult.items`` and ``ScanResult.objects`` come
        back empty. A caller that keeps only what it needs from each chunk
        holds that, not the whole kingdom's rows and owner records, which
        every full garbage collection walks while they live. A failed chunk
        is not passed on; it is in ``failed_chunks`` as usual. An exception
        raised by ``on_chunk`` ends the scan. The client decides nothing
        here: it reads each chunk into its world map as it arrives.
        """
        return _Scan(
            [self],
            kingdom,
            _filter_types(item_types),
            include_unowned_types,
            timeout=timeout,
            request_timeout=request_timeout,
            chunk_delay=chunk_delay,
            cancel=cancel,
            on_chunk=on_chunk,
        ).run()

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
        on_chunk: ChunkHandler | None = None,
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
        chunks, and ``on_chunk`` takes each chunk in place of the result, as
        in scan_kingdom().
        """
        return _Scan(
            [self],
            kingdom,
            _filter_types(item_types),
            include_unowned_types,
            timeout=timeout,
            request_timeout=request_timeout,
            chunk_delay=chunk_delay,
            cancel=cancel,
            on_chunk=on_chunk,
        ).run(chunks=chunks)

    def chunk_for_position(self, x: int, y: int) -> tuple[int, int]:
        """Map world coordinates to the chunk that contains them."""
        return (x // self.CHUNK_SIZE, y // self.CHUNK_SIZE)


def scan_kingdom_with(
    clients: Sequence[_Client],
    kingdom: Kingdom = Kingdom.GREEN,
    item_types: list[MapItemType] | None = None,
    timeout: float = 300.0,
    request_timeout: float = 5.0,
    chunk_delay: float = 0.0,
    include_unowned_types: set[MapItemType] | None = None,
    *,
    chunks: Iterable[tuple[int, int]] | None = None,
    cancel: threading.Event | None = None,
    on_chunk: ChunkHandler | None = None,
) -> ScanResult:
    """
    Scan one kingdom with several logged-in clients at once, each on its own thread.

    Without ``chunks`` the clients discover the kingdom together, breadth-first
    from the castle there of the first client that has one, as :meth:`MapScanner.scan_kingdom`
    does; with ``chunks`` (say a discovery's ``content_chunks``) they scan
    those, as :meth:`MapScanner.scan_chunks` does. Every other argument means
    what it means there. Each client keeps one request in flight and takes the
    next chunk not yet taken, so the chunks interleave across the clients and
    a slow client takes fewer.

    A chunk that fails on one client, after that client's own retries, is
    asked again by a client that has not tried it. A client whose session
    drops, or whose account has not unlocked the kingdom (a chunk refused with
    ADDITIONAL_KINGDOM_NOT_UNLOCKED), leaves the scan and the others take over
    its chunk. Only a chunk every remaining client has tried, or one left when
    no client remains, the ``timeout`` passes or ``cancel`` is set, ends in
    ``failed_chunks``.

    The result merges every client's chunks: ``items`` and ``content_chunks``
    are in the order the chunks answered, which varies between runs.
    ``on_chunk`` is called from the clients' threads, one call at a time, so
    it needs no lock of its own; an exception it raises stops every client
    after its chunk in flight and is raised here, and no chunk reaches
    ``on_chunk`` after it. An interrupt (``KeyboardInterrupt``) while waiting
    stops the clients the same way, each after the request it has in flight,
    and is raised once they have. Every session leaves the castle it had joined.

    Parsing a chunk's reply holds the GIL, so threads in one process overlap
    their waits for replies but not their parsing; see the map-scanning guide.
    The client decides nothing here: one game client is one session and never
    spreads a scan.

    Raises:
        ValueError: ``clients`` is empty, or names one client twice
        CommandError: Every client left with ADDITIONAL_KINGDOM_NOT_UNLOCKED
    """
    if not clients:
        raise ValueError("scan_kingdom_with needs at least one client")
    if len({id(client) for client in clients}) != len(clients):
        raise ValueError("scan_kingdom_with takes each client once")
    scan = _Scan(
        [MapScanner(client) for client in clients],
        kingdom,
        _filter_types(item_types),
        include_unowned_types,
        timeout=timeout,
        request_timeout=request_timeout,
        chunk_delay=chunk_delay,
        cancel=cancel,
        on_chunk=on_chunk,
    )
    return scan.run(chunks=chunks)


_MAIN_CASTLE_TYPES = frozenset({MapItemType.CASTLE, MapItemType.KINGDOM_CASTLE})
"""A player's main castle in a kingdom (``CastleList.getMainCastleByKingdomID``, bundle line 10861)."""


def _filter_types(item_types: list[MapItemType] | None) -> set[MapItemType] | None:
    """The types a scan keeps: ``None`` asks for main castles only, ``[]`` for every type (None here)."""
    if item_types is None:
        return set(_MAIN_CASTLE_TYPES)
    return set(item_types) or None


class _Scan:
    """
    One scan shared by one or more clients, each taking the next chunk from a shared frontier.

    A chunk that fails on a client goes back to the frontier for a client that
    has not tried it yet; a client whose session drops, or that has not
    unlocked the kingdom, leaves the scan. Only a chunk every remaining client
    has tried ends in ``failed_chunks``. The kingdom not being unlocked is
    raised once every client has left for it.
    """

    WAIT_POLL = 0.05

    def __init__(
        self,
        scanners: Sequence[MapScanner],
        kingdom: Kingdom,
        filter_types: set[MapItemType] | None,
        include_unowned_types: set[MapItemType] | None,
        *,
        timeout: float,
        request_timeout: float,
        chunk_delay: float,
        cancel: threading.Event | None,
        on_chunk: ChunkHandler | None,
    ) -> None:
        self.scanners = scanners
        self.kingdom = kingdom
        self.filter_types = filter_types
        self.include_unowned_types = include_unowned_types
        self.request_timeout = request_timeout
        self.chunk_delay = chunk_delay
        self.cancel = cancel
        self.on_chunk = on_chunk
        self.deadline = time.monotonic() + timeout

        self.lock = threading.Condition()
        self.hook_lock = threading.Lock()
        self.frontier: deque[tuple[int, int]] = deque()
        self.enqueued: set[tuple[int, int]] = set()
        self.tried_by: dict[tuple[int, int], set[int]] = {}
        self.live = set(range(len(scanners)))
        self.not_unlocked: set[int] = set()
        self.active = 0
        self.discovering = False
        self.bounds = (0, 0, 0, 0)
        self.stopped: str | None = None
        self.error: BaseException | None = None

        self.items: list[MapAreaItem] = []
        self.objects: dict[int, MapObject] = {}
        self.failed: list[tuple[int, int]] = []
        self.content: list[tuple[int, int]] = []
        self.requests = 0
        self.items_found = 0

    def run(self, chunks: Iterable[tuple[int, int]] | None = None) -> ScanResult:
        """Scan ``chunks``, or discover the kingdom breadth-first from the first castle a client has there."""
        name = "Kingdom scan" if chunks is None else "Chunk scan"
        if chunks is None:
            x, y = next(
                (position for scanner in self.scanners if (position := scanner._castle_position(self.kingdom))),
                (650, 650),
            )
            start = self.scanners[0].chunk_for_position(x, y)
            self.discovering = True
            self.bounds = (*start, *start)
            chunks = [start]
        for chunk in chunks:
            self._add(chunk)
        logger.debug(
            f"{name} of {self.kingdom!r}: {len(self.frontier)} chunk(s) queued, {len(self.scanners)} client(s)"
        )

        started = time.monotonic()
        if len(self.scanners) == 1:
            self._work(0)
        else:
            threads: list[threading.Thread] = []
            try:
                for index in range(len(self.scanners)):
                    threads.append(
                        threading.Thread(target=self._work, args=(index,), name=f"map-scan-{index}", daemon=True)
                    )
                    threads[-1].start()
                for thread in threads:
                    thread.join()
            except BaseException:
                with self.lock:
                    self.stopped = "interrupted"
                    self.lock.notify_all()
                for thread in threads:
                    thread.join()
                raise
        if self.error is not None:
            raise self.error
        if len(self.not_unlocked) == len(self.scanners):
            raise CommandError("gaa", GGEError.ADDITIONAL_KINGDOM_NOT_UNLOCKED)

        if self.stopped:
            logger.log(
                logging.WARNING if self.stopped == "timed out" else logging.INFO,
                f"{name} {self.stopped} after {self.requests} requests",
            )
        failed = self.failed + list(self.frontier)
        _log_incomplete(name, failed, cancelled=self.stopped == "cancelled", connection_lost=not self.live)
        logger.debug(
            f"{name} of {self.kingdom!r} done: {self.requests} chunks in {time.monotonic() - started:.1f}s, "
            f"found {self.items_found} items"
        )
        return ScanResult(
            items=self.items,
            objects=self.objects,
            kingdom=self.kingdom,
            failed_chunks=tuple(failed),
            content_chunks=tuple(self.content),
        )

    def _add(self, chunk: tuple[int, int]) -> None:
        cx, cy = chunk
        if chunk in self.enqueued or not (0 <= cx <= MapScanner.MAX_COORD and 0 <= cy <= MapScanner.MAX_COORD):
            return
        self.enqueued.add(chunk)
        self.frontier.append(chunk)

    def _work(self, index: int) -> None:
        scanner = self.scanners[index]
        while True:
            if self.chunk_delay > 0:
                sleep_unless_cancelled(self.chunk_delay, self.cancel)
            chunk = self._take(index)
            if chunk is None:
                return
            try:
                result = scanner._process_chunk(
                    *chunk,
                    self.kingdom,
                    self.filter_types,
                    self.request_timeout,
                    include_unowned_types=self.include_unowned_types,
                    cancel=self.cancel,
                )
                if result.ok and self.on_chunk is not None:
                    with self.hook_lock:
                        with self.lock:
                            aborted = self.error is not None or self.stopped == "interrupted"
                        if not aborted:
                            self.on_chunk(chunk, result.items, result.objects)
            except BaseException as e:
                with self.lock:
                    self.active -= 1
                    self.error = self.error or e
                    self.lock.notify_all()
                return
            left = result is _NOT_UNLOCKED or (not result.ok and not scanner.client.connection.connected)
            self._finish(index, chunk, result, left)
            if left:
                return

    def _take(self, index: int) -> tuple[int, int] | None:
        """The next chunk this client has not tried, waiting while another client may still add one; None to stop."""
        with self.lock:
            while True:
                if self.error is not None or self.stopped:
                    return None
                if self.cancel is not None and self.cancel.is_set():
                    self.stopped = "cancelled"
                    return None
                if time.monotonic() > self.deadline:
                    self.stopped = "timed out"
                    return None
                for position, chunk in enumerate(self.frontier):
                    if index not in self.tried_by.get(chunk, ()):
                        del self.frontier[position]
                        self.active += 1
                        self.requests += 1
                        return chunk
                if not self.frontier and not self.active:
                    return None
                self.lock.wait(self.WAIT_POLL)

    def _finish(self, index: int, chunk: tuple[int, int], result: _ChunkResult, left: bool) -> None:
        """Record a chunk's result; ``left`` when its client leaves the scan, its chunk then going to the others."""
        with self.lock:
            self.active -= 1
            if left:
                self.live.discard(index)
            if result is _NOT_UNLOCKED:
                self.not_unlocked.add(index)
                self.frontier.appendleft(chunk)
            elif result.ok:
                self.items_found += len(result.items)
                if self.on_chunk is None:
                    self.items.extend(result.items)
                    self.objects.update(result.objects)
                if result.has_content:
                    self.content.append(chunk)
                self._expand(chunk, result.has_content)
            else:
                self.tried_by.setdefault(chunk, set()).add(index)
                if self.live - self.tried_by[chunk]:
                    self.frontier.appendleft(chunk)
                else:
                    self.failed.append(chunk)
                    if self.live:
                        self._expand(chunk, True)
            if left and self.live:
                for stranded in [c for c in self.frontier if not self.live - self.tried_by.get(c, set())]:
                    self.frontier.remove(stranded)
                    self.failed.append(stranded)
            self.lock.notify_all()

    def _expand(self, chunk: tuple[int, int], has_content: bool) -> None:
        """
        Queue a discovered chunk's neighbours: all of them after content, else those near the content found so far.

        A failed chunk counts as content, so the scan expands past it.
        """
        if not self.discovering:
            return
        cx, cy = chunk
        min_x, min_y, max_x, max_y = self.bounds
        if has_content:
            min_x, min_y, max_x, max_y = min(min_x, cx), min(min_y, cy), max(max_x, cx), max(max_y, cy)
            self.bounds = (min_x, min_y, max_x, max_y)
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if has_content or (min_x - 2 <= nx <= max_x + 2 and min_y - 2 <= ny <= max_y + 2):
                self._add((nx, ny))
