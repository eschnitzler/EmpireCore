"""Tests for MapScanner chunk math."""

import json

from empire_core.client.map_scanner import MapScanner
from empire_core.protocol.models.map import Kingdom
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
    """Serves canned gaa responses keyed by chunk coords."""

    def __init__(self, content_chunks: set[tuple[int, int]]):
        self.content_chunks = content_chunks
        self.connected = True
        self.requests: list[tuple[int, int]] = []

    def request(self, data: str, cmd_id: str, timeout: float = 5.0) -> Packet:
        # Recover the chunk coords from the request payload:
        # %xt%{zone}%{cmd}%{reqid}%{payload}% -> payload at index 5
        payload = json.loads(data.split("%")[5])
        cx, cy = payload["AX1"] // MapScanner.CHUNK_SIZE, payload["AY1"] // MapScanner.CHUNK_SIZE
        self.requests.append((cx, cy))

        ai = [[1, payload["AX1"] + 5, payload["AY1"] + 5, 42]] if (cx, cy) in self.content_chunks else []
        return Packet(raw_data="", is_xml=False, command_id="gaa", payload={"AI": ai, "OI": []})


class _FakeConfig:
    default_zone = "EmpireEx_21"


class _FakeClient:
    def __init__(self, content_chunks: set[tuple[int, int]], start_chunk: tuple[int, int] = (0, 0)):
        self.connection = _FakeConnection(content_chunks)
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
        discovery = _make_scanner(discovery_fake).scan_kingdom(
            kingdom=Kingdom.GREEN, item_types=[], chunk_delay=0
        )
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
