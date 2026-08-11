"""Tests for MapScanner chunk math."""

import json
import logging
import time
from typing import Any

import pytest

from empire_core.client.map_scanner import MapScanner
from empire_core.exceptions import CommandError, EmpireTimeoutError, NetworkError
from empire_core.protocol.models.map import Kingdom, MapItemType
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
        self.raises = raises or {}
        self.payloads = payloads or {}
        self.delay = delay
        self.disconnect_on_failure = disconnect_on_failure
        self.connected = True
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
        if error_code:
            if self.disconnect_on_failure:
                self.connected = False
            # Real error responses carry no JSON body, and the packet parser
            # still hands back a dict payload ({"raw": ""}).
            return Packet(raw_data="", is_xml=False, command_id="gaa", error_code=error_code, payload={"raw": ""})

        if (cx, cy) in self.payloads:
            return Packet(raw_data="", is_xml=False, command_id="gaa", payload=self.payloads[(cx, cy)])

        ai = [[1, payload["AX1"] + 5, payload["AY1"] + 5, 42]] if (cx, cy) in self.content_chunks else []
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
        self._start_chunk = start_chunk

    def _get_kingdom_start_position(self, kingdom: Kingdom) -> tuple[int, int]:
        cx, cy = self._start_chunk
        return (cx * MapScanner.CHUNK_SIZE, cy * MapScanner.CHUNK_SIZE)


def _make_scanner(fake: _FakeClient) -> MapScanner:
    return MapScanner(fake)  # type: ignore[arg-type]


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

    def test_chunk_for_position(self):
        scanner = MapScanner.__new__(MapScanner)
        assert scanner.chunk_for_position(0, 0) == (0, 0)
        assert scanner.chunk_for_position(MapScanner.CHUNK_SIZE - 1, 0) == (0, 0)
        assert scanner.chunk_for_position(MapScanner.CHUNK_SIZE, 0) == (1, 0)
        assert scanner.chunk_for_position(455, 545) == (5, 6)


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

    def test_complete_scan_reports_no_failures(self):
        fake = _FakeClient(content_chunks={(5, 5)}, start_chunk=(5, 5))
        result = _make_scanner(fake).scan_kingdom(kingdom=Kingdom.GREEN, item_types=[], chunk_delay=0)
        assert result.failed_chunks == ()


class TestMalformedResponses:
    def test_garbage_ai_entry_does_not_abort_scan(self):
        fake = _FakeClient(
            content_chunks=set(),
            payloads={(1, 1): {"AI": [["?", "?", "?", "?"], [1, 95, 95, 42]], "OI": []}},
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
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): {"AI": [["?", "?", "?", "?"]], "OI": []}})
        with caplog.at_level(logging.DEBUG, logger="empire_core.client.map_scanner"):
            _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)
        assert "skipping invalid map item" in caplog.text

    def test_invalid_map_object_is_logged(self, caplog):
        fake = _FakeClient(
            content_chunks=set(),
            payloads={(1, 1): {"AI": [], "OI": [{"OID": 7, "X": "not-a-number"}]}},
        )
        with caplog.at_level(logging.DEBUG, logger="empire_core.client.map_scanner"):
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
        with caplog.at_level(logging.INFO, logger="empire_core.client.map_scanner"):
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

    def test_skipped_map_objects_counted_in_drift_warning(self, caplog):
        fake = _FakeClient(
            content_chunks=set(),
            payloads={(1, 1): {"AI": [], "OI": [{"OID": 7, "X": "not-a-number"}, "junk"]}},
        )
        with caplog.at_level(logging.WARNING, logger="empire_core.client.map_scanner"):
            _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "2/2" in warnings[0].getMessage()

    def test_drift_warning_truncates_the_sample_entry(self, caplog):
        fake = _FakeClient(
            content_chunks=set(),
            payloads={(1, 1): {"AI": [{"blob": "x" * 5000}], "OI": []}},
        )
        with caplog.at_level(logging.WARNING, logger="empire_core.client.map_scanner"):
            _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert len(warnings[0].getMessage()) < 600, "sample entry not truncated"

    def test_clean_chunk_emits_no_drift_warning(self, caplog):
        fake = _FakeClient(content_chunks={(1, 1)})
        with caplog.at_level(logging.WARNING, logger="empire_core.client.map_scanner"):
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
            raises={(1, 1): [EmpireTimeoutError("no answer"), NetworkError("still broken")]},
        )
        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)
        assert result.failed_chunks == ((1, 1),)

    def test_retry_does_not_swallow_programming_errors(self):
        fake = _FakeClient(
            content_chunks={(1, 1)},
            raises={(1, 1): [EmpireTimeoutError("no answer"), TypeError("bug in the retry path")]},
        )
        with pytest.raises(TypeError):
            _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)


class TestItemTypeFiltering:
    """Locks in the documented (inverted) item_types sentinel semantics."""

    ROBBER_BARON_AI = {"AI": [[int(MapItemType.ROBBER_BARON), 95, 95, 7]], "OI": []}

    def test_none_means_castles_only(self):
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): self.ROBBER_BARON_AI})
        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=None, chunk_delay=0)
        assert result.items == []

    def test_empty_list_means_no_filtering(self):
        fake = _FakeClient(content_chunks=set(), payloads={(1, 1): self.ROBBER_BARON_AI})
        result = _make_scanner(fake).scan_chunks(kingdom=Kingdom.GREEN, chunks=[(1, 1)], item_types=[], chunk_delay=0)
        assert [i.item_type for i in result.items] == [int(MapItemType.ROBBER_BARON)]
