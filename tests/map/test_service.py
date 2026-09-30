"""Tests for the map service."""

from __future__ import annotations

from typing import get_type_hints

from empire_core.enums import Kingdom
from empire_core.map.scanner import ScanResult
from empire_core.map.service import MapService
from tests.service_helpers import conn, make_client, xt_packet


class TestPublicSurfaceIsTyped:
    """The README advertises a fully typed client."""

    def test_scan_methods_return_scan_result(self):
        assert get_type_hints(MapService.scan_kingdom)["return"] is ScanResult
        assert get_type_hints(MapService.scan_chunks)["return"] is ScanResult


class TestScanMapArea:
    def test_rows_carry_the_kingdom_scanned(self):
        client = make_client({"gaa": xt_packet("gaa", {"KID": 2, "AI": [[1, 5, 6, 4242]], "OI": []})})
        response = client.map.scan_map_area(0, 0, 10, 10, kingdom=Kingdom.ICE)
        assert conn(client).request_payloads == [("gaa", {"KID": 2, "AX1": 0, "AY1": 0, "AX2": 10, "AY2": 10})]
        assert [(item.kingdom, item.is_relocating) for item in response.items] == [(Kingdom.ICE, True)]
