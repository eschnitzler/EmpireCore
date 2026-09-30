"""Tests for the map service."""

from __future__ import annotations

from typing import get_type_hints

import pytest

from empire_core.enums import Kingdom, MapItemType
from empire_core.exceptions import CommandError
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


class TestFindNext:
    REPLY = {
        "gaa": {"AI": [[29, 700, 710, -1, 4, 100, 0, 0, -1, 110, 110, 0]], "OI": []},
        "X": 700,
        "Y": 710,
    }

    def test_sends_the_client_keys_and_reads_the_rows_in_the_kingdom_asked(self):
        client = make_client({"fnm": xt_packet("fnm", self.REPLY)})
        response = client.map.find_next(MapItemType.SAMURAI_CAMP, Kingdom.ICE, owner_id=-700)
        assert conn(client).request_payloads == [("fnm", {"T": 29, "KID": 2, "LMIN": -1, "LMAX": -1, "NID": -700})]
        assert response is not None
        found = response.found()
        assert found is not None and (found.victory_count, found.kingdom) == (4, Kingdom.ICE)

    def test_no_match_is_none(self):
        client = make_client({"fnm": xt_packet("fnm", error_code=153)})
        assert client.map.find_next(MapItemType.NOMAD_CAMP) is None

    def test_another_refusal_raises(self):
        client = make_client({"fnm": xt_packet("fnm", error_code=21)})
        with pytest.raises(CommandError):
            client.map.find_next(MapItemType.NOMAD_CAMP)
