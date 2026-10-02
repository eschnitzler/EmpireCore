"""Tests for the map service."""

from __future__ import annotations

from typing import get_type_hints

import pytest

from empire_core.enums import Kingdom, MapItemType
from empire_core.exceptions import CommandError
from empire_core.map.models.areas import (
    FindNextEnemyCastleRequest,
    FindNextEnemyCastleResponse,
    FindNextMapObjectResponse,
    FindNextTowerRequest,
    FindNextTowerResponse,
)
from empire_core.map.scanner import ScanResult
from empire_core.map.service import MapService
from empire_core.protocol.base import parse_response
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


class TestFindNextEnemyCastle:
    REPLY = {
        "gaa": {
            "AI": [[1, 620, 231, 3001, 4001, 1, 1, 1, 0, 0, "Enemy", 0, 0, -1, -1, -1, 0, 0, [], 0]],
            "OI": [],
        },
        "X": 620,
        "Y": 231,
    }

    def test_request_keys_follow_the_vo(self):
        # C2SFindNextEnemyCastleVO initialises X, Y, N, LMIN, LMAX; the levels default to -1
        request = FindNextEnemyCastleRequest(X=500, Y=510, N=3)
        assert list(request.to_payload().items()) == [("X", 500), ("Y", 510), ("N", 3), ("LMIN", -1), ("LMAX", -1)]

    def test_sends_the_position_and_index(self):
        client = make_client({"fec": xt_packet("fec", self.REPLY)})
        response = client.map.find_next_enemy_castle(500, 510, index=2, min_level=10, max_level=40)
        assert conn(client).request_payloads == [("fec", {"X": 500, "Y": 510, "N": 2, "LMIN": 10, "LMAX": 40})]
        assert isinstance(response, FindNextEnemyCastleResponse)
        found = response.found()
        assert found is not None and (found.item_type, found.owner_id) == (MapItemType.CASTLE, 4001)

    def test_reply_is_registered_and_read_as_fnm(self):
        response = parse_response("fec", self.REPLY)
        assert isinstance(response, FindNextEnemyCastleResponse)
        assert isinstance(response, FindNextMapObjectResponse)
        assert (response.x, response.y) == (620, 231)

    @pytest.mark.parametrize("index", [-1, 10])
    def test_index_is_0_to_9(self, index: int):
        client = make_client()
        with pytest.raises(ValueError):
            client.map.find_next_enemy_castle(500, 510, index=index)
        assert conn(client).request_payloads == []

    def test_no_match_is_none(self):
        client = make_client({"fec": xt_packet("fec", error_code=153)})
        assert client.map.find_next_enemy_castle(500, 510) is None


class TestFindNextTower:
    REPLY = {"gaa": {"AI": [[17, 300, 310, -800, 0, [], 60, 5, 2, 17]], "OI": []}, "X": 300, "Y": 310}

    def test_sends_nothing_and_reads_the_rows_in_berimond(self):
        client = make_client({"fnt": xt_packet("fnt", self.REPLY)})
        response = client.map.find_next_tower()
        assert conn(client).request_payloads == [("fnt", {})]
        assert isinstance(response, FindNextTowerResponse)
        found = response.found()
        assert found is not None
        assert (found.item_type, found.kingdom, found.dungeon_level) == (MapItemType.FACTION_TOWER, Kingdom.BERIMOND, 5)

    def test_no_match_is_none(self):
        client = make_client({"fnt": xt_packet("fnt", error_code=153)})
        assert client.map.find_next_tower() is None

    def test_request_sends_nothing(self):
        assert FindNextTowerRequest().to_payload() == {}
