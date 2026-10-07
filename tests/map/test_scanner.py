"""Tests for MapScanner chunk math."""

import json
import logging
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from empire_core.enums import Kingdom, MapItemType
from empire_core.exceptions import CommandError, EmpireTimeoutError, NetworkError
from empire_core.map.scanner import MapScanner, scan_kingdom_with
from empire_core.protocol.errors import GGEError
from empire_core.protocol.packet import Packet


class TestChunkBounds:
    def test_adjacent_chunks_do_not_overlap(self):
        scanner = MapScanner.__new__(MapScanner)  # No client needed for bounds math
        x1a, y1a, x2a, y2a = scanner._chunk_bounds(0, 0)
        x1b, y1b, _, _ = scanner._chunk_bounds(1, 0)
        # Inclusive bounds: chunk 0 must end one short of chunk 1's start
        assert x2a == x1b - 1
        assert x2a - x1a + 1 == MapScanner.CHUNK_SIZE

    def test_bounds_scale_with_coordinates(self):
        scanner = MapScanner.__new__(MapScanner)
        x1, y1, x2, y2 = scanner._chunk_bounds(3, 5)
        assert x1 == 3 * MapScanner.CHUNK_SIZE
        assert y1 == 5 * MapScanner.CHUNK_SIZE
        assert x2 == x1 + MapScanner.CHUNK_SIZE - 1
        assert y2 == y1 + MapScanner.CHUNK_SIZE - 1


class _FakeConnection:
    """Serves canned gaa responses keyed by chunk coords.

    Per-chunk overrides let a test simulate the ways a real server
    misbehaves: ``error_codes`` returns a non-zero gaa error code,
    ``raises`` raises a scripted exception per attempt, and ``payloads``
    substitutes a hand-written response body. ``delay`` makes every
    request consume wall-clock time so scan timeouts can be exercised,
    and ``disconnect_on_failure`` drops the connection as it fails.
    """

    def __init__(
        self,
        content_chunks: set[tuple[int, int]],
        error_codes: dict[tuple[int, int], int] | None = None,
        raises: dict[tuple[int, int], list[Exception]] | None = None,
        payloads: dict[tuple[int, int], dict[str, Any]] | None = None,
        delay: float = 0.0,
        disconnect_on_failure: bool = False,
    ):
        self.content_chunks = content_chunks
        self.error_codes = error_codes or {}
        self.error_codes_once = False
        self.raises = raises or {}
        self.payloads = payloads or {}
        self.delay = delay
        self.disconnect_on_failure = disconnect_on_failure
        self.connected = True
        self.room_id = -1
        self.requests: list[tuple[int, int]] = []

    def request(self, data: str, cmd_id: str, timeout: float = 5.0) -> Packet:
        # Recover the chunk coords from the request payload:
        # %xt%{zone}%{cmd}%{reqid}%{payload}% -> payload at index 5
        payload = json.loads(data.split("%")[5])
        cx, cy = payload["AX1"] // MapScanner.CHUNK_SIZE, payload["AY1"] // MapScanner.CHUNK_SIZE
        self.requests.append((cx, cy))

        if self.delay:
            time.sleep(self.delay)

        pending = self.raises.get((cx, cy))
        if pending:
            if self.disconnect_on_failure:
                self.connected = False
            raise pending.pop(0)

        error_code = self.error_codes.get((cx, cy), 0)
        if error_code and self.error_codes_once:
            del self.error_codes[(cx, cy)]
        if error_code:
            if self.disconnect_on_failure:
                self.connected = False
            # Real error responses carry no JSON body, and the packet parser
            # still hands back a dict payload ({"raw": ""}).
            return Packet(raw_data="", is_xml=False, command_id="gaa", error_code=error_code, payload={"raw": ""})

        if (cx, cy) in self.payloads:
            return Packet(raw_data="", is_xml=False, command_id="gaa", payload=self.payloads[(cx, cy)])

        ai = [[1, payload["AX1"] + 5, payload["AY1"] + 5, 900, 42]] if (cx, cy) in self.content_chunks else []
        return Packet(raw_data="", is_xml=False, command_id="gaa", payload={"AI": ai, "OI": []})


class _FakeConfig:
    default_zone = "EmpireEx_21"


class _FakeClient:
    def __init__(
        self,
        content_chunks: set[tuple[int, int]],
        start_chunk: tuple[int, int] = (0, 0),
        **connection_kwargs: Any,
    ):
        self.connection = _FakeConnection(content_chunks, **connection_kwargs)
        self.config = _FakeConfig()
        self.state = _FakeState(start_chunk)

    def request_packet(self, request: Any, response_command: str, timeout: float = 5.0) -> Any:
        frame = request.to_packet(zone=self.config.default_zone, room_id=getattr(self.connection, "room_id", 1))
        return self.connection.request(frame, response_command, timeout=timeout)


class _FakeState:
    """One own castle in the green kingdom, inside ``start_chunk``."""

    def __init__(self, start_chunk: tuple[int, int]):
        cx, cy = start_chunk
        self.castle = SimpleNamespace(
            kingdom_id=Kingdom.GREEN, x=cx * MapScanner.CHUNK_SIZE, y=cy * MapScanner.CHUNK_SIZE
        )

    def get_castles(self) -> list[SimpleNamespace]:
        return [self.castle]


def _make_scanner(fake: _FakeClient) -> MapScanner:
    scanner = MapScanner(fake)
    scanner.RETRY_BACKOFF = 0.0
    return scanner


class TestScanChunks:
    def test_scans_exactly_the_requested_chunks(self):
        fake = _FakeClient(content_chunks={(2, 2)})
        result = _make_scanner(fake).scan_chunks(
            kingdom=Kingdom.GREEN, chunks=[(1, 1), (2, 2), (3, 3)], item_types=[], chunk_delay=0
        )
        assert fake.connection.requests == [(1, 1), (2, 2), (3, 3)]
        assert result.content_chunks == ((2, 2),)
        assert result.failed_chunks == ()
        assert len(result.items) == 1

    def test_deduplicates_and_skips_out_of_range(self):
        fake = _FakeClient(content_chunks=set())
        _make_scanner(fake).scan_chunks(
            kingdom=Kingdom.GREEN,
            chunks=[(1, 1), (1, 1), (-1, 0), (0, MapScanner.MAX_COORD + 1)],
            item_types=[],
            chunk_delay=0,
        )
        assert fake.connection.requests == [(1, 1)]

    def test_kingdom_scan_reports_content_chunks(self):
        # Content only at the start chunk; BFS probes its empty neighborhood.
        fake = _FakeClient(content_chunks={(5, 5)}, start_chunk=(5, 5))
        result = _make_scanner(fake).scan_kingdom(kingdom=Kingdom.GREEN, item_types=[], chunk_delay=0)
        assert result.content_chunks == ((5, 5),)
        # Discovery probed more chunks than had content
        assert len(fake.connection.requests) > 1

    def test_rescan_of_content_chunks_is_cheaper_than_discovery(self):
        content = {(5, 5), (5, 6), (6, 5)}
        discovery_fake = _FakeClient(content_chunks=content, start_chunk=(5, 5))
        discovery = _make_scanner(discovery_fake).scan_kingdom(kingdom=Kingdom.GREEN, item_types=[], chunk_delay=0)
        discovery_requests = len(discovery_fake.connection.requests)

        rescan_fake = _FakeClient(content_chunks=content)
        rescan = _make_scanner(rescan_fake).scan_chunks(
            kingdom=Kingdom.GREEN, chunks=list(discovery.content_chunks), item_types=[], chunk_delay=0
        )
        assert len(rescan_fake.connection.requests) == 3
        assert len(rescan_fake.connection.requests) < discovery_requests
        assert len(rescan.items) == len(discovery.items)

    def test_include_unowned_types_reaches_the_chunk_parser(self):
        """scan_kingdom grew include_unowned_types in 0.29.0; scan_chunks must
        honour it too — the consumer's cached re-scans go through scan_chunks,
        and dropping the flag there silently loses every unowned item (e.g.
        Kings Towers) between discoveries."""
        unowned = [1, 5, 5, -1]  # owner -1: skipped unless explicitly included
        fake = _FakeClient(
            content_chunks=set(),
            payloads={(1, 1): {"AI": [unowned], "OI": []}},
        )
        scanner = _make_scanner(fake)

        excluded = scanner.scan_chunks(
            kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[MapItemType.CASTLE], chunk_delay=0
        )
        assert excluded.items == [], "unowned items must stay excluded by default"

        included = scanner.scan_chunks(
            kingdom=Kingdom.GREEN,
            chunks=[(1, 1)],
            item_types=[MapItemType.CASTLE],
            chunk_delay=0,
            include_unowned_types={MapItemType.CASTLE},
        )
        assert len(included.items) == 1, "include_unowned_types was not passed through"

    def test_service_signatures_match_the_scanner(self):
        """MapService.scan_chunks/scan_kingdom delegate to MapScanner; a
        parameter added to the scanner but not the facade is invisible to
        every consumer and TypeErrors at the real call site — which is
        exactly how include_unowned_types shipped broken in 0.30.2."""
        import inspect

        from empire_core.map.service import MapService

        for name in ("scan_chunks", "scan_kingdom"):
            scanner_params = list(inspect.signature(getattr(MapScanner, name)).parameters)
            facade_params = list(inspect.signature(getattr(MapService, name)).parameters)
            assert facade_params == scanner_params, f"{name}: facade {facade_params} != scanner {scanner_params}"

    def test_chunk_for_position(self):
        scanner = MapScanner.__new__(MapScanner)
        assert scanner.chunk_for_position(0, 0) == (0, 0)
        assert scanner.chunk_for_position(MapScanner.CHUNK_SIZE - 1, 0) == (0, 0)
        assert scanner.chunk_for_position(MapScanner.CHUNK_SIZE, 0) == (1, 0)
        assert scanner.chunk_for_position(455, 545) == (5, 6)


class TestKingdomStartPosition:
    def test_starts_at_the_own_castle_in_that_kingdom(self):
        scanner = _make_scanner(_FakeClient(content_chunks=set(), start_chunk=(5, 6)))
        assert scanner._castle_position(Kingdom.GREEN) == (450, 540)

    def test_there_is_none_without_a_castle_there(self):
        scanner = _make_scanner(_FakeClient(content_chunks=set()))
        assert scanner._castle_position(Kingdom.FIRE) is None

    def test_a_scan_without_a_castle_there_starts_at_the_map_center(self):
        fake = _FakeClient(content_chunks=set())
        _make_scanner(fake).scan_kingdom(Kingdom.FIRE, item_types=[])
        assert fake.connection.requests[0] == _make_scanner(fake).chunk_for_position(650, 650)


class TestServerErrorCodes:
    """A non-zero gaa error code must never look like an empty area."""

    def test_error_code_marks_chunk_failed(self):
        # 95 = COOLING_DOWN: server refused, the area is unknown, not empty.
        fake = _FakeClient(content_chunks={(1, 1), (2, 2)}, error_codes={(2, 2): 95})
        result = _make_scanner(fake).scan_chunks(
            kingdom=Kingdom.GREEN, chunks=[(1, 1), (2, 2)], item_types=[], chunk_delay=0
        )
        assert result.failed_chunks == ((2, 2),)
        assert result.content_chunks == ((1, 1),)
        assert len(result.items) == 1

    def test_error_code_does_not_truncate_kingdom_scan(self):
        # The start chunk errors out; content sits behind it. The scan must
        # report the failure and still expand past it.
        fake = _FakeClient(content_chunks={(5, 6)}, start_chunk=(5, 5), error_codes={(5, 5): 142})
        result = _make_scanner(fake).scan_kingdom(kingdom=Kingdom.GREEN, item_types=[], chunk_delay=0)
        assert (5, 5) in result.failed_chunks
        assert (5, 6) in result.content_chunks

    def test_kingdom_not_unlocked_still_raises(self):
        fake = _FakeClient(content_chunks=set(), error_codes={(1, 1): 337})
        with pytest.raises(CommandError) as excinfo:
            _make_scanner(fake).scan_chunks(kingdom=Kingdom.FIRE, chunks=[(1, 1)], item_types=[], chunk_delay=0)
        assert excinfo.value.code == 337


class TestPartialScanReporting:
    """A truncated scan must be distinguishable from a complete one."""

    def test_timeout_reports_unscanned_queue(self):
        # Each request burns 30ms, so the 50ms budget runs out with chunks
        # still queued by the BFS expansion.
        fake = _FakeClient(content_chunks={(5, 5), (5, 6), (6, 5)}, start_chunk=(5, 5), delay=0.03)
        result = _make_scanner(fake).scan_kingdom(kingdom=Kingdom.GREEN, item_types=[], timeout=0.05, chunk_delay=0)
        assert result.failed_chunks, "timed-out scan reported no failed chunks"
        # Everything reported as failed must be a chunk that was never scanned.
        assert not set(result.failed_chunks) & set(fake.connection.requests)

    def test_connection_loss_reports_unscanned_queue(self):
        # (5, 5) has content so the BFS queues its four neighbours; the next
        # chunk then dies with the connection.
        fake = _FakeClient(
            content_chunks={(5, 5)},
            start_chunk=(5, 5),
            raises={(4, 5): [NetworkError("socket closed")]},
            disconnect_on_failure=True,
        )
        result = _make_scanner(fake).scan_kingdom(kingdom=Kingdom.GREEN, item_types=[], chunk_delay=0)
        assert (4, 5) in result.failed_chunks
        # The neighbours queued behind the dead chunk must not be lost.
        queued_but_unscanned = {(6, 5), (5, 4), (5, 6)}
        assert queued_but_unscanned <= set(result.failed_chunks)

    def test_an_incomplete_scan_warns_with_the_count_and_lists_chunks_at_debug(self, caplog):
        chunks = [(1, y) for y in range(12)]
        fake = _FakeClient(content_chunks=set(), error_codes=dict.fromkeys(chunks, 1))

        with caplog.at_level(logging.DEBUG, logger="empire_core.map.scanner"):
            _make_scanner(fake).scan_chunks(Kingdom.GREEN, chunks, chunk_delay=0)

        summary = [r for r in caplog.records if "incomplete" in r.getMessage()]
        listing = [r for r in caplog.records if "failed chunks" in r.getMessage()]
        assert [(r.levelname, r.getMessage()) for r in summary] == [
            ("WARNING", "Chunk scan incomplete: 12 chunk(s) failed")
        ]
        assert [r.levelname for r in listing] == ["DEBUG"]
        assert "(1, 9)" in listing[0].getMessage() and "(1, 10)" not in listing[0].getMessage()

    def test_complete_scan_reports_no_failures(self):
        fake = _FakeClient(content_chunks={(5, 5)}, start_chunk=(5, 5))
        result = _make_scanner(fake).scan_kingdom(kingdom=Kingdom.GREEN, item_types=[], chunk_delay=0)
        assert result.failed_chunks == ()


class TestMalformedResponses:
    def test_garbage_ai_entry_does_not_abort_scan(self):
        fake = _FakeClient(
            content_chunks=set(),
            payloads={(1, 1): {"AI": [[99, "?", "?", "?"], [1, 95, 95, 900, 42]], "OI": []}},
        )
        result = _make_scanner(fake).scan_chunks(
            kingdom=Kingdom.GREEN, chunks=[(1, 1), (2, 2)], item_types=[], chunk_delay=0
        )
        # The good entry survives, the chunk is not marked failed, and the
        # scan carries on to the next chunk.
        assert [(i.x, i.y, i.owner_id) for i in result.items] == [(95, 95, 42)]
        assert result.failed_chunks == ()
        assert fake.connection.requests == [(1, 1), (2, 2)]

    def test_garbage_ai_entry_is_logged(self, caplog):
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): {"AI": [[99, "?", "?", "?"]], "OI": []}})
        with caplog.at_level(logging.DEBUG, logger="empire_core.map.scanner"):
            _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)
        assert "skipping invalid map item" in caplog.text

    def test_invalid_map_object_is_logged(self, caplog):
        fake = _FakeClient(
            content_chunks=set(),
            payloads={(1, 1): {"AI": [], "OI": [{"OID": 7, "N": ["not", "a", "name"]}]}},
        )
        with caplog.at_level(logging.DEBUG, logger="empire_core.map.scanner"):
            result = _make_scanner(fake).scan_chunks(
                kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0
            )
        assert result.objects == {}
        assert "skipping invalid map object" in caplog.text

    def test_reshaped_ai_entries_warn_instead_of_silent_empty_scan(self, caplog):
        # If GGE reshapes AI entries (list -> dict), every chunk returns
        # ok=True with zero items and failed_chunks=() — that must not look
        # like a successful empty scan with nothing above debug level.
        fake = _FakeClient(
            content_chunks=set(),
            payloads={(1, 1): {"AI": [{"unexpected": "shape"}, {"also": "wrong"}], "OI": []}},
        )
        with caplog.at_level(logging.INFO, logger="empire_core.map.scanner"):
            result = _make_scanner(fake).scan_chunks(
                kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0
            )

        assert result.items == []
        assert result.failed_chunks == ()
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1, "schema drift hidden behind a 'successful' empty scan"
        message = warnings[0].getMessage()
        assert "(1, 1)" in message
        assert "2/2" in message, f"skipped/total counts missing: {message}"
        assert "unexpected" in message, f"sample entry missing: {message}"

    def test_short_entries_are_not_reported_as_drift(self, caplog):
        # The live AI array is mostly short entries like [31, 0, 996] — items
        # with no owner field, skipped by design since long before any of this.
        # Counting them as drift buries the real signal: a production scan
        # logged over a thousand "schema drift?" warnings per chunk for a
        # payload that was entirely normal.
        fake = _FakeClient(
            content_chunks=set(),
            payloads={
                (1, 1): {
                    "AI": [[31, 0, 996], [31, 91, 900], [1, 100, 200, 900, 4242]],
                    "OI": [],
                }
            },
        )
        with caplog.at_level(logging.DEBUG, logger="empire_core.map.scanner"):
            result = _make_scanner(fake).scan_chunks(
                kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0
            )

        assert len(result.items) == 1, "the parseable entry must still be collected"
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warnings == [], f"short entries reported as drift: {[w.getMessage() for w in warnings]}"

    def test_unparseable_long_entries_still_warn(self, caplog):
        # A full-width entry that fails to parse is the real drift signal and
        # must survive the fix above.
        fake = _FakeClient(
            content_chunks=set(),
            payloads={(1, 1): {"AI": [[14, "y", "z", "w"], [31, 0, 996]], "OI": []}},
        )
        with caplog.at_level(logging.WARNING, logger="empire_core.map.scanner"):
            _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "1/2" in warnings[0].getMessage(), warnings[0].getMessage()

    def test_skipped_map_objects_counted_in_drift_warning(self, caplog):
        fake = _FakeClient(
            content_chunks=set(),
            payloads={(1, 1): {"AI": [], "OI": [{"OID": 7, "N": ["not", "a", "name"]}, "junk"]}},
        )
        with caplog.at_level(logging.WARNING, logger="empire_core.map.scanner"):
            _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "2/2" in warnings[0].getMessage()

    def test_drift_warning_truncates_the_sample_entry(self, caplog):
        fake = _FakeClient(
            content_chunks=set(),
            payloads={(1, 1): {"AI": [{"blob": "x" * 5000}], "OI": []}},
        )
        with caplog.at_level(logging.WARNING, logger="empire_core.map.scanner"):
            _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert len(warnings[0].getMessage()) < 600, "sample entry not truncated"

    def test_clean_chunk_emits_no_drift_warning(self, caplog):
        fake = _FakeClient(content_chunks={(1, 1)})
        with caplog.at_level(logging.WARNING, logger="empire_core.map.scanner"):
            _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)

        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


class TestChunkRetry:
    def test_transport_error_recovers_on_retry(self):
        fake = _FakeClient(content_chunks={(1, 1)}, raises={(1, 1): [EmpireTimeoutError("no answer")]})
        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)
        assert fake.connection.requests == [(1, 1), (1, 1)]
        assert result.failed_chunks == ()
        assert len(result.items) == 1

    def test_transport_error_on_retry_marks_chunk_failed(self):
        fake = _FakeClient(
            content_chunks={(1, 1)},
            raises={
                (1, 1): [EmpireTimeoutError("no answer"), NetworkError("still broken"), EmpireTimeoutError("again")]
            },
        )
        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)
        assert fake.connection.requests == [(1, 1)] * 3
        assert result.failed_chunks == ((1, 1),)

    def test_retries_back_off(self, monkeypatch):
        slept: list[float] = []

        def sleep(seconds: float, cancel: threading.Event | None) -> bool:
            slept.append(seconds)
            return False

        monkeypatch.setattr("empire_core.map.scanner.sleep_unless_cancelled", sleep)
        fake = _FakeClient(
            content_chunks={(1, 1)},
            raises={(1, 1): [EmpireTimeoutError("no answer"), EmpireTimeoutError("again")]},
        )
        result = MapScanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[])
        assert slept == [0.5, 1.0], "no pacing by default, only the backoff"
        assert result.failed_chunks == ()

    def test_a_cooldown_refusal_is_retried(self):
        fake = _FakeClient(content_chunks={(1, 1)}, error_codes={(1, 1): 95})
        fake.connection.error_codes_once = True
        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)
        assert fake.connection.requests == [(1, 1), (1, 1)]
        assert result.failed_chunks == ()

    def test_retry_does_not_swallow_programming_errors(self):
        fake = _FakeClient(
            content_chunks={(1, 1)},
            raises={(1, 1): [EmpireTimeoutError("no answer"), TypeError("bug in the retry path")]},
        )
        with pytest.raises(TypeError):
            _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)


class TestUnclaimedOutposts:
    UNCLAIMED = [int(MapItemType.OUTPOST), 630, 205, 14824223, -300, 1, 1, 1, 0, 0, ""]
    OWNED = [int(MapItemType.OUTPOST), 510, 257, 2002, 1001, 1, 1, 1, 0, 0, "OP1"]

    def test_unclaimed_outposts_are_unowned(self):
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): {"AI": [self.UNCLAIMED, self.OWNED], "OI": []}})
        result = _make_scanner(fake).scan_chunks(
            kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[MapItemType.OUTPOST], chunk_delay=0
        )
        assert [(i.location_id, i.owner_id) for i in result.items] == [(2002, 1001)]

    def test_unclaimed_outposts_can_be_included(self):
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): {"AI": [self.UNCLAIMED, self.OWNED], "OI": []}})
        result = _make_scanner(fake).scan_chunks(
            kingdom=Kingdom.GREEN,
            chunks=[(1, 1)],
            item_types=[MapItemType.OUTPOST],
            include_unowned_types={MapItemType.OUTPOST},
            chunk_delay=0,
        )
        assert [i.location_id for i in result.items] == [14824223, 2002]


class TestItemTypeFiltering:
    """Locks in the documented (inverted) item_types sentinel semantics."""

    ROBBER_BARON_AI = {"AI": [[int(MapItemType.DUNGEON), 95, 95, 7]], "OI": []}

    def test_none_means_castles_only(self):
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): self.ROBBER_BARON_AI})
        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=None, chunk_delay=0)
        assert result.items == []

    def test_none_keeps_the_main_castles_of_other_kingdoms(self):
        rows = [[int(MapItemType.KINGDOM_CASTLE), 95, 95, 4242], [int(MapItemType.DUNGEON), 96, 96, 7]]
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): {"AI": rows, "OI": []}})
        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.ICE, chunks=[(1, 1)], item_types=None, chunk_delay=0)
        assert [i.item_type for i in result.items] == [MapItemType.KINGDOM_CASTLE]

    def test_camps_survive_the_unowned_filter(self):
        # A live camp row carries an espionage age of -1 where an owned
        # location carries an id, so the unowned filter must not drop it.
        live_camp = {"AI": [[int(MapItemType.DUNGEON), 95, 95, -1, 297, -100, 0]], "OI": []}
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): live_camp})

        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)

        assert [i.victory_count for i in result.items] == [297]

    def test_event_camps_survive_the_unowned_filter(self):
        # A nomad camp row has no owner field at all; it must not be dropped as "unowned".
        payload = {"AI": [[int(MapItemType.NOMAD_CAMP), 95, 95, -1, 297, -100, 0, 0, -1, 0, 0, 0]], "OI": []}
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): payload})

        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)

        assert [i.item_type for i in result.items] == [MapItemType.NOMAD_CAMP]

    def test_empty_list_means_no_filtering(self):
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): self.ROBBER_BARON_AI})
        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)
        assert [i.item_type for i in result.items] == [MapItemType.DUNGEON]


class TestRelocatingCastles:
    """CastleMapobjectVO.parseAreaInfo (bundle line 18910): a four-field castle row is a plot or a moving castle."""

    def test_a_castle_on_the_move_is_kept_and_a_free_plot_is_not(self):
        rows = [[1, 95, 95, 4242], [1, 96, 96, -1], [12, 97, 97, 4343]]
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): {"AI": rows, "OI": []}})
        result = _make_scanner(fake).scan_chunks(
            kingdom=Kingdom.GREEN,
            chunks=[(1, 1)],
            item_types=[MapItemType.CASTLE, MapItemType.KINGDOM_CASTLE],
            chunk_delay=0,
        )
        assert [(i.x, i.occupier_id, i.is_relocating) for i in result.items] == [(95, 4242, True), (97, 4343, True)]

    def test_free_plots_can_be_included(self):
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): {"AI": [[1, 96, 96, -1]], "OI": []}})
        result = _make_scanner(fake).scan_chunks(
            kingdom=Kingdom.GREEN, chunks=[(1, 1)], include_unowned_types={MapItemType.CASTLE}, chunk_delay=0
        )
        assert [(i.x, i.is_relocating) for i in result.items] == [(96, False)]


class TestScanKingdom:
    """Every item and the result carry the kingdom scanned."""

    def test_items_and_the_result_carry_the_scanned_kingdom(self):
        fake = _FakeClient(content_chunks={(1, 1)})
        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.ICE, chunks=[(1, 1)], chunk_delay=0)
        assert result.kingdom is Kingdom.ICE
        assert [i.kingdom for i in result.items] == [Kingdom.ICE]

    def test_a_row_that_names_its_kingdom_keeps_it(self):
        camp = [int(MapItemType.DUNGEON), 95, 95, -1, 3, 0, int(Kingdom.FIRE)]
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): {"AI": [camp], "OI": []}})
        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)
        assert [i.kingdom for i in result.items] == [Kingdom.FIRE]

    def test_owner_records_without_an_owner_id_are_left_out(self):
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): {"AI": [], "OI": [{"N": "x"}, {"OID": 5}]}})
        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], chunk_delay=0)
        assert list(result.objects) == [5]


def _cancel_after(fake: _FakeClient, requests: int) -> threading.Event:
    """An event the fake server sets as it answers its ``requests``-th gaa."""
    cancel = threading.Event()
    answer = fake.connection.request

    def request(data: str, cmd_id: str, timeout: float = 5.0) -> Packet:
        try:
            return answer(data, cmd_id, timeout)
        finally:
            if len(fake.connection.requests) >= requests:
                cancel.set()

    fake.connection.request = request  # type: ignore[method-assign]
    return cancel


CONTENT = {(5, 5), (5, 6), (6, 5)}


class TestCancellingAScan:
    """A cancel is looked at between chunks: the chunk in flight is answered, never abandoned."""

    def test_a_kingdom_scan_stops_after_the_chunk_in_flight(self):
        fake = _FakeClient(content_chunks=CONTENT, start_chunk=(5, 5))
        cancel = _cancel_after(fake, 3)

        result = _make_scanner(fake).scan_kingdom(kingdom=Kingdom.GREEN, item_types=[], cancel=cancel)

        assert len(fake.connection.requests) == 3
        assert result.failed_chunks
        assert not set(result.failed_chunks) & set(fake.connection.requests)
        assert set(result.content_chunks) <= set(fake.connection.requests)

    def test_a_cancel_before_the_first_chunk_scans_nothing(self):
        fake = _FakeClient(content_chunks=CONTENT, start_chunk=(5, 5))
        cancel = threading.Event()
        cancel.set()

        result = _make_scanner(fake).scan_kingdom(kingdom=Kingdom.GREEN, item_types=[], cancel=cancel)

        assert fake.connection.requests == []
        assert result.failed_chunks == ((5, 5),)

    def test_a_chunk_scan_reports_the_chunks_left(self):
        fake = _FakeClient(content_chunks=CONTENT)
        cancel = _cancel_after(fake, 1)

        result = _make_scanner(fake).scan_chunks(Kingdom.GREEN, [(5, 5), (5, 6), (6, 5)], item_types=[], cancel=cancel)

        assert fake.connection.requests == [(5, 5)]
        assert result.content_chunks == ((5, 5),)
        assert result.failed_chunks == ((5, 6), (6, 5))

    def test_a_cancel_skips_the_retry(self):
        fake = _FakeClient(content_chunks={(1, 1)}, raises={(1, 1): [EmpireTimeoutError("no answer")]})
        cancel = _cancel_after(fake, 1)

        result = MapScanner(fake).scan_chunks(Kingdom.GREEN, [(1, 1), (2, 2)], item_types=[], cancel=cancel)

        assert fake.connection.requests == [(1, 1)]
        assert result.failed_chunks == ((1, 1), (2, 2))

    def test_the_facade_passes_the_cancel_on(self):
        from empire_core.map.service import MapService

        fake = _FakeClient(content_chunks=CONTENT)
        cancel = threading.Event()
        cancel.set()

        result = MapService(fake).scan_chunks(Kingdom.GREEN, [(5, 5)], cancel=cancel)  # type: ignore[arg-type]

        assert (fake.connection.requests, result.failed_chunks) == ([], ((5, 5),))

    def test_a_cancelled_scan_does_not_warn(self, caplog):
        fake = _FakeClient(content_chunks=CONTENT, start_chunk=(5, 5))
        cancel = _cancel_after(fake, 2)

        with caplog.at_level(logging.DEBUG, logger="empire_core.map.scanner"):
            result = _make_scanner(fake).scan_kingdom(item_types=[], cancel=cancel)

        assert result.failed_chunks
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


class TestOnChunk:
    """``on_chunk`` takes each chunk that answered in place of the result."""

    def test_each_chunk_goes_to_the_hook_and_the_result_keeps_none(self):
        fake = _FakeClient(
            content_chunks={(2, 2)},
            payloads={(1, 1): {"AI": [], "OI": [{"OID": 5}]}},
            error_codes={(3, 3): 95},
        )
        seen: list[tuple[tuple[int, int], int, list[int]]] = []

        result = _make_scanner(fake).scan_chunks(
            Kingdom.GREEN,
            [(1, 1), (2, 2), (3, 3)],
            item_types=[],
            on_chunk=lambda chunk, items, objects: seen.append((chunk, len(items), list(objects))),
        )

        assert seen == [((1, 1), 0, [5]), ((2, 2), 1, [])]
        assert (result.items, result.objects) == ([], {})
        assert (result.content_chunks, result.failed_chunks) == (((2, 2),), ((3, 3),))

    def test_a_kingdom_scan_hands_on_every_chunk_it_scans(self):
        fake = _FakeClient(content_chunks=CONTENT, start_chunk=(5, 5))
        chunks: list[tuple[int, int]] = []

        result = _make_scanner(fake).scan_kingdom(
            item_types=[], on_chunk=lambda chunk, items, objects: chunks.append(chunk)
        )

        assert chunks == fake.connection.requests
        assert result.items == []
        assert set(result.content_chunks) == CONTENT

    def test_an_exception_from_the_hook_ends_the_scan(self):
        fake = _FakeClient(content_chunks=CONTENT)

        def stop(chunk: tuple[int, int], items: list[Any], objects: dict[int, Any]) -> None:
            raise RuntimeError("enough")

        with pytest.raises(RuntimeError, match="enough"):
            _make_scanner(fake).scan_chunks(Kingdom.GREEN, [(5, 5), (5, 6)], item_types=[], on_chunk=stop)
        assert fake.connection.requests == [(5, 5)]

    def test_an_exception_from_the_hook_ends_a_kingdom_scan(self):
        fake = _FakeClient(content_chunks=CONTENT, start_chunk=(5, 5))

        def stop(chunk: tuple[int, int], items: list[Any], objects: dict[int, Any]) -> None:
            raise RuntimeError("enough")

        with pytest.raises(RuntimeError, match="enough"):
            _make_scanner(fake).scan_kingdom(item_types=[], on_chunk=stop)
        assert fake.connection.requests == [(5, 5)]

    def test_the_scan_log_counts_the_items_handed_on(self, caplog):
        fake = _FakeClient(content_chunks=CONTENT, start_chunk=(5, 5))

        with caplog.at_level(logging.DEBUG, logger="empire_core.map.scanner"):
            _make_scanner(fake).scan_kingdom(item_types=[], on_chunk=lambda chunk, items, objects: None)

        assert f"found {len(CONTENT)} items" in caplog.text

    def test_the_facade_passes_the_hook_on(self):
        from empire_core.map.service import MapService

        fake = _FakeClient(content_chunks=CONTENT)
        chunks: list[tuple[int, int]] = []

        MapService(fake).scan_chunks(  # type: ignore[arg-type]
            Kingdom.GREEN, [(5, 5)], on_chunk=lambda chunk, items, objects: chunks.append(chunk)
        )

        assert chunks == [(5, 5)]


def _drop_after(fake: _FakeClient, answered: int) -> None:
    """The fake session drops on the request after its ``answered``-th."""
    answer = fake.connection.request

    def request(data: str, cmd_id: str, timeout: float = 5.0) -> Packet:
        if len(fake.connection.requests) >= answered:
            answer(data, cmd_id, timeout)
            fake.connection.connected = False
            raise NetworkError("connection reset")
        return answer(data, cmd_id, timeout)

    fake.connection.request = request  # type: ignore[method-assign]


def _hold_first_replies(fakes: list[_FakeClient]) -> None:
    """Each fake answers its first request only once every fake has sent one, so each takes a chunk."""
    barrier = threading.Barrier(len(fakes))
    for fake in fakes:
        answer = fake.connection.request

        def request(data: str, cmd_id: str, timeout: float = 5.0, answer: Any = answer, fake: Any = fake) -> Packet:
            reply = answer(data, cmd_id, timeout)
            if len(fake.connection.requests) == 1:
                barrier.wait(timeout=5)
            return reply

        fake.connection.request = request  # type: ignore[method-assign]


def _refuse_kingdom(fake: _FakeClient) -> None:
    """The fake's account has not unlocked the kingdom: every chunk of GRID is refused with 337."""
    fake.connection.error_codes = dict.fromkeys(GRID, 337)


GRID = [(x, y) for x in range(2, 8) for y in range(2, 8)]


@pytest.fixture
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MapScanner, "RETRY_BACKOFF", 0.0)


@pytest.mark.usefixtures("no_backoff")
class TestScanningWithSeveralClients:
    """scan_kingdom_with: one scan, its chunks spread over several clients."""

    def test_each_chunk_is_asked_once_and_every_client_takes_some(self):
        fakes = [_FakeClient(content_chunks=set(GRID[::2])) for _ in range(3)]
        _hold_first_replies(fakes)

        result = scan_kingdom_with(fakes, Kingdom.GREEN, item_types=[], chunks=GRID)  # type: ignore[arg-type]

        asked = [chunk for fake in fakes for chunk in fake.connection.requests]
        assert sorted(asked) == sorted(GRID)
        assert all(fake.connection.requests for fake in fakes)
        assert result.failed_chunks == ()
        assert sorted(result.content_chunks) == sorted(GRID[::2])
        assert len(result.items) == len(GRID[::2])

    def test_a_shared_discovery_finds_what_one_client_finds(self):
        content = {(x, y) for x in range(4, 9) for y in range(5, 8)} | {(10, 6)}
        alone = _make_scanner(_FakeClient(content_chunks=content, start_chunk=(5, 5))).scan_kingdom(item_types=[])
        fakes = [_FakeClient(content_chunks=content, start_chunk=(5, 5), delay=0.002) for _ in range(4)]

        shared = scan_kingdom_with(fakes, item_types=[])  # type: ignore[arg-type]

        assert shared.failed_chunks == ()
        assert sorted(shared.content_chunks) == sorted(alone.content_chunks)
        assert sorted((i.x, i.y) for i in shared.items) == sorted((i.x, i.y) for i in alone.items)
        assert shared.kingdom is Kingdom.GREEN

    def test_the_owner_records_of_every_client_are_merged(self):
        owners = {(1, 1): {"AI": [], "OI": [{"OID": 1}]}, (2, 2): {"AI": [], "OI": [{"OID": 2}]}}
        fakes = [_FakeClient(content_chunks=set(), payloads=owners) for _ in range(2)]
        _hold_first_replies(fakes)

        result = scan_kingdom_with(fakes, chunks=[(1, 1), (2, 2)])  # type: ignore[arg-type]

        assert all(fake.connection.requests for fake in fakes)
        assert sorted(result.objects) == [1, 2]

    def test_a_dropped_client_leaves_its_chunks_to_the_others(self):
        fakes = [_FakeClient(content_chunks=set(GRID), delay=0.005) for _ in range(3)]
        _drop_after(fakes[0], 1)

        result = scan_kingdom_with(fakes, item_types=[], chunks=GRID)  # type: ignore[arg-type]

        assert len(fakes[0].connection.requests) == 2
        lost = fakes[0].connection.requests[-1]
        assert lost in fakes[1].connection.requests + fakes[2].connection.requests
        assert result.failed_chunks == ()
        assert sorted(result.content_chunks) == sorted(GRID)

    def test_when_every_client_drops_the_rest_is_failed(self):
        fakes = [_FakeClient(content_chunks=set(GRID), delay=0.002) for _ in range(2)]
        for fake in fakes:
            _drop_after(fake, 3)

        result = scan_kingdom_with(fakes, item_types=[], chunks=GRID)  # type: ignore[arg-type]

        assert len(result.content_chunks) == 6
        assert sorted(result.content_chunks + result.failed_chunks) == sorted(GRID)

    def test_a_chunk_that_fails_goes_to_a_client_that_has_not_tried_it(self):
        first_ask_fails = {(1, 1): 1}
        fakes = [_FakeClient(content_chunks={(1, 1)}, error_codes=first_ask_fails) for _ in range(2)]
        for fake in fakes:
            fake.connection.error_codes_once = True

        result = scan_kingdom_with(fakes, item_types=[], chunks=[(1, 1)])  # type: ignore[arg-type]

        assert [fake.connection.requests for fake in fakes] == [[(1, 1)], [(1, 1)]]
        assert result.failed_chunks == ()
        assert result.content_chunks == ((1, 1),)

    def test_only_a_chunk_every_client_failed_is_failed(self):
        fakes = [_FakeClient(content_chunks=set(), error_codes={(3, 3): 1}, delay=0.002) for _ in range(3)]

        result = scan_kingdom_with(fakes, chunks=[(1, 1), (2, 2), (3, 3), (4, 4)])  # type: ignore[arg-type]

        assert result.failed_chunks == ((3, 3),)
        assert [fake.connection.requests.count((3, 3)) for fake in fakes] == [1, 1, 1]

    def test_a_cancel_stops_every_client_and_reports_the_rest(self):
        fakes = [_FakeClient(content_chunks=set(GRID), delay=0.005) for _ in range(3)]
        cancel = threading.Event()
        answered: list[tuple[int, int]] = []

        def count(chunk: tuple[int, int], items: list[Any], objects: dict[int, Any]) -> None:
            answered.append(chunk)
            if len(answered) == 4:
                cancel.set()

        result = scan_kingdom_with(fakes, item_types=[], chunks=GRID, cancel=cancel, on_chunk=count)  # type: ignore[arg-type]

        asked = {chunk for fake in fakes for chunk in fake.connection.requests}
        assert len(asked) <= 4 + len(fakes)
        assert set(result.failed_chunks) == set(GRID) - asked
        assert not [t for t in threading.enumerate() if t.name.startswith("map-scan-")]

    def test_on_chunk_is_called_one_at_a_time(self):
        fakes = [_FakeClient(content_chunks=set(GRID)) for _ in range(4)]
        inside = threading.Lock()
        overlaps: list[tuple[int, int]] = []
        seen: list[tuple[int, int]] = []

        def hook(chunk: tuple[int, int], items: list[Any], objects: dict[int, Any]) -> None:
            if not inside.acquire(blocking=False):
                overlaps.append(chunk)
                return
            time.sleep(0.001)
            seen.append(chunk)
            inside.release()

        result = scan_kingdom_with(fakes, item_types=[], chunks=GRID, on_chunk=hook)  # type: ignore[arg-type]

        assert overlaps == []
        assert sorted(seen) == sorted(GRID)
        assert (result.items, result.objects) == ([], {})

    def test_an_exception_from_the_hook_stops_every_client_and_is_raised(self):
        fakes = [_FakeClient(content_chunks=set(GRID), delay=0.005) for _ in range(3)]

        def stop(chunk: tuple[int, int], items: list[Any], objects: dict[int, Any]) -> None:
            raise RuntimeError("enough")

        with pytest.raises(RuntimeError, match="enough"):
            scan_kingdom_with(fakes, item_types=[], chunks=GRID, on_chunk=stop)  # type: ignore[arg-type]
        assert sum(len(fake.connection.requests) for fake in fakes) <= 2 * len(fakes)

    def test_a_client_without_the_kingdom_leaves_its_chunks_to_the_others(self):
        fakes = [_FakeClient(content_chunks=set(GRID), delay=0.002) for _ in range(2)]
        _refuse_kingdom(fakes[0])

        result = scan_kingdom_with(fakes, Kingdom.FIRE, item_types=[], chunks=GRID)  # type: ignore[arg-type]

        assert len(fakes[0].connection.requests) == 1
        assert sorted(fakes[1].connection.requests) == sorted(GRID)
        assert result.failed_chunks == ()
        assert sorted(result.content_chunks) == sorted(GRID)

    def test_a_kingdom_no_client_has_unlocked_is_raised(self):
        fakes = [_FakeClient(content_chunks=set(GRID)) for _ in range(2)]
        for fake in fakes:
            _refuse_kingdom(fake)

        with pytest.raises(CommandError) as excinfo:
            scan_kingdom_with(fakes, Kingdom.FIRE, chunks=GRID)  # type: ignore[arg-type]
        assert excinfo.value.error is GGEError.ADDITIONAL_KINGDOM_NOT_UNLOCKED
        assert [len(fake.connection.requests) for fake in fakes] == [1, 1]

    def test_a_kingdom_not_unlocked_is_not_raised_when_another_client_dropped(self):
        fakes = [_FakeClient(content_chunks=set(GRID), delay=0.002) for _ in range(2)]
        _refuse_kingdom(fakes[0])
        _drop_after(fakes[1], 2)

        result = scan_kingdom_with(fakes, Kingdom.FIRE, item_types=[], chunks=GRID)  # type: ignore[arg-type]

        assert sorted(result.content_chunks + result.failed_chunks) == sorted(GRID)

    def test_discovery_starts_at_the_first_client_with_a_castle_there(self):
        content = {(x, y) for x in range(4, 7) for y in range(4, 7)}
        fakes = [_FakeClient(content_chunks=content, start_chunk=(5, 5)) for _ in range(2)]
        fakes[0].state.castle.kingdom_id = Kingdom.FIRE

        result = scan_kingdom_with(fakes, item_types=[])  # type: ignore[arg-type]

        assert sorted(result.content_chunks) == sorted(content)

    def test_no_chunk_reaches_on_chunk_after_it_raised(self):
        fakes = [_FakeClient(content_chunks=set(GRID), delay=0.005) for _ in range(3)]
        calls: list[tuple[int, int]] = []

        def stop(chunk: tuple[int, int], items: list[Any], objects: dict[int, Any]) -> None:
            calls.append(chunk)
            time.sleep(0.02)
            raise RuntimeError("enough")

        with pytest.raises(RuntimeError, match="enough"):
            scan_kingdom_with(fakes, item_types=[], chunks=GRID, on_chunk=stop)  # type: ignore[arg-type]
        assert len(calls) == 1

    def test_an_interrupt_stops_every_client_and_is_raised(self, monkeypatch: pytest.MonkeyPatch):
        fakes = [_FakeClient(content_chunks=set(GRID), delay=0.005) for _ in range(3)]
        delivered: list[tuple[int, int]] = []
        join = threading.Thread.join
        interrupted: list[bool] = []

        def interrupt_once(thread: threading.Thread, timeout: float | None = None) -> None:
            if not interrupted:
                interrupted.append(True)
                raise KeyboardInterrupt
            join(thread, timeout)

        monkeypatch.setattr(threading.Thread, "join", interrupt_once)
        with pytest.raises(KeyboardInterrupt):
            scan_kingdom_with(
                fakes,  # type: ignore[arg-type]
                item_types=[],
                chunks=GRID,
                on_chunk=lambda chunk, items, objects: delivered.append(chunk),
            )
        monkeypatch.undo()

        asked = sum(len(fake.connection.requests) for fake in fakes)
        assert not [t for t in threading.enumerate() if t.name.startswith("map-scan-")]
        assert asked <= 2 * len(fakes)
        assert len(delivered) <= asked

    def test_no_clients_is_refused(self):
        with pytest.raises(ValueError):
            scan_kingdom_with([], chunks=[(1, 1)])

    def test_one_client_twice_is_refused(self):
        fake = _FakeClient(content_chunks=set())

        with pytest.raises(ValueError, match="once"):
            scan_kingdom_with([fake, fake], chunks=[(1, 1)])  # type: ignore[list-item]
        assert fake.connection.requests == []
