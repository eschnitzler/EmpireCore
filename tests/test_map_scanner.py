"""Tests for MapScanner chunk math."""

from empire_core.client.map_scanner import MapScanner


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
