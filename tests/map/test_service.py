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
        assert get_type_hints(MapService.scan_around)["return"] is ScanResult


class TestScanMapArea:
    def test_area_reads_wait_on_the_account_pacer(self, monkeypatch):
        client = make_client({"gaa": xt_packet("gaa", {"KID": 0, "AI": [], "OI": []})})
        waits: list[int] = []

        def wait(tiles: int, cancel: object = None) -> bool:
            waits.append(tiles)
            return False

        monkeypatch.setattr(client.map.pacer, "wait", wait)

        client.map.scan_map_area(0, 0, 89, 89)
        client.map.scan_map_area(0, 0, 9, 9)

        assert waits == [8100, 100]

    def test_the_pacer_follows_the_config_rate(self):
        client = make_client({})
        client.config.map_tiles_per_second = 100.0
        assert client.map.pacer._tiles_per_second() == 100.0

    def test_rows_carry_the_kingdom_scanned(self):
        client = make_client({"gaa": xt_packet("gaa", {"KID": 2, "AI": [[1, 5, 6, 4242]], "OI": []})})
        response = client.map.scan_map_area(0, 0, 10, 10, kingdom=Kingdom.ICE)
        assert conn(client).request_payloads == [("gaa", {"KID": 2, "AX1": 0, "AY1": 0, "AX2": 10, "AY2": 10})]
        assert [(item.kingdom, item.is_relocating) for item in response.items] == [(Kingdom.ICE, True)]


class TestScanMapAreaCap:
    def test_a_side_past_100_tiles_is_cut_as_the_client_cuts_it(self):
        client = make_client({"gaa": xt_packet("gaa", {"KID": 0, "AI": [], "OI": []})})
        client.map.scan_map_area(10, 20, 150, 120)
        assert conn(client).request_payloads == [("gaa", {"KID": 0, "AX1": 10, "AY1": 20, "AX2": 109, "AY2": 120})]


def _dungeon(x: int, y: int) -> list[int]:
    return [2, x, y, -1, 0, -1]


class TestScanAround:
    def test_a_small_box_is_one_paced_request_kept_to_the_circle_nearest_first(self, monkeypatch):
        rows = [_dungeon(502, 502), [1, 503, 503, 4242], _dungeon(500, 501), _dungeon(497, 500)]
        client = make_client({"gaa": xt_packet("gaa", {"KID": 0, "AI": rows, "OI": [{"OID": 4242, "N": "x"}]})})
        waits: list[int] = []

        def wait(tiles, cancel=None):
            waits.append(tiles)
            return False

        monkeypatch.setattr(client.map.pacer, "wait", wait)

        result = client.map.scan_around(500, 500, 3, Kingdom.GREEN)

        assert conn(client).request_payloads == [("gaa", {"KID": 0, "AX1": 497, "AY1": 497, "AX2": 503, "AY2": 503})]
        assert waits == [49]
        assert [(item.x, item.y) for item in result.items] == [(500, 501), (502, 502), (497, 500)]
        assert list(result.objects) == [4242]
        assert (result.kingdom, result.failed_chunks) == (Kingdom.GREEN, ())

    def test_item_types_keep_only_those_types(self):
        rows = [_dungeon(502, 502), [1, 501, 501, 4242]]
        client = make_client({"gaa": xt_packet("gaa", {"KID": 0, "AI": rows, "OI": []})})
        result = client.map.scan_around(500, 500, 3, Kingdom.GREEN, [MapItemType.DUNGEON])
        assert [item.item_type for item in result.items] == [MapItemType.DUNGEON]

    def test_a_101_tile_box_is_still_one_request(self):
        client = make_client({"gaa": xt_packet("gaa", {"KID": 0, "AI": [], "OI": []})})
        client.map.scan_around(500, 500, 50, Kingdom.GREEN)
        assert conn(client).request_payloads == [("gaa", {"KID": 0, "AX1": 450, "AY1": 450, "AX2": 550, "AY2": 550})]

    def test_a_larger_box_is_read_chunk_by_chunk_with_npc_rows_kept(self):
        replies = [
            xt_packet("gaa", {"KID": 0, "AI": [_dungeon(80, 80)], "OI": []}),
            xt_packet("gaa", {"KID": 0, "AI": [_dungeon(50, 170)], "OI": []}),
            xt_packet("gaa", {"KID": 0, "AI": [], "OI": []}),
            xt_packet("gaa", {"KID": 0, "AI": [_dungeon(120, 95), [1, 100, 100, 4242]], "OI": []}),
        ]
        client = make_client({"gaa": replies})
        client.config.map_tiles_per_second = float("inf")

        result = client.map.scan_around(100, 100, 60, Kingdom.GREEN, [MapItemType.DUNGEON])

        assert [payload["AX1"] for _, payload in conn(client).request_payloads] == [0, 0, 90, 90]
        assert [payload["AY1"] for _, payload in conn(client).request_payloads] == [0, 90, 0, 90]
        assert [(item.x, item.y) for item in result.items] == [(120, 95), (80, 80)]
        assert result.failed_chunks == ()

    def test_chunks_past_the_map_edge_are_skipped(self):
        client = make_client({"gaa": xt_packet("gaa", {"KID": 0, "AI": [], "OI": []})})
        client.config.map_tiles_per_second = float("inf")
        client.map.scan_around(10, 10, 60, Kingdom.GREEN)
        assert [(p["AX1"], p["AY1"]) for _, p in conn(client).request_payloads] == [(0, 0)]


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
        request = FindNextEnemyCastleRequest(x=500, y=510, index=3)
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
