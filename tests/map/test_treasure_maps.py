"""Treasure maps: the tmp, thi, tbm, tfm and tcn models, the maps kept in state, and client.map's treasure map calls."""

from __future__ import annotations

import pytest

from empire_core.enums import CollectableKind, TreasureMapProgress
from empire_core.exceptions import CommandError
from empire_core.gamedata import TreasureMapId, TreasureMapNodeId, Unit
from empire_core.map import (
    NO_TREASURE_MAP,
    BuyTreasureMapPiecesRequest,
    BuyTreasureMapPiecesResponse,
    FinishTreasureMapRequest,
    FinishTreasureMapResponse,
    GetTreasureMapsRequest,
    TreasureHuntInfoResponse,
    TreasureMapsResponse,
    TreasureNodeClickResponse,
)
from empire_core.protocol.models import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

# A TM row as TreasureMapVO.loadFromParamObject reads it
MAP_ROW = {
    "MID": 23,
    "N": [
        {"NID": 1, "A": 1, "CD": 0},
        {"NID": 2, "A": 0, "CD": 120, "G": [["W", 500]], "C1C2": 40, "SC2": 30, "WC2": 20},
    ],
    "PF": 3,
    "PT": 2,
    "RT": {"RS": 600, "G": [["S", 1000], ["F", 200]]},
    "UT": {"RS": 300, "I": [[Unit.SWORDMAN.value, 50]]},
    "S": {"MU": 400, "U": 150, "MRF": 9000, "MRW": 8000, "MRS": 7000, "F": 100, "W": 200, "S": 300},
    "M": 85,
    "I": [[Unit.SWORDMAN.value, 100]],
    "RS": 86400,
}


def tmp(*rows: dict, full: bool = False) -> dict:
    return {"UA": 1 if full else 0, "TM": list(rows)}


class TestModels:
    def test_the_requests_follow_the_client(self):
        assert GetTreasureMapsRequest().to_payload() == {"MID": -1}
        assert GetTreasureMapsRequest(map_id=23).to_payload() == {"MID": 23}
        payload = BuyTreasureMapPiecesRequest(amount=2, map_id=50).to_payload()
        assert payload == {"A": 2, "MID": 50} and list(payload) == ["A", "MID"]
        assert FinishTreasureMapRequest(map_id=50).to_payload() == {"MID": 50}

    def test_a_map_row(self):
        reply = parse_response("tmp", tmp(MAP_ROW, full=True))
        assert isinstance(reply, TreasureMapsResponse) and reply.is_full_list
        (treasure_map,) = reply.maps
        assert (treasure_map.map_id, treasure_map.pieces_found, treasure_map.morality) == (23, 3, 85)
        assert treasure_map.progress is TreasureMapProgress.DESTROYED_DUNGEON
        assert treasure_map.units == {Unit.SWORDMAN: 100}
        assert treasure_map.remaining_seconds(treasure_map.received_at) == 86400
        node = treasure_map.node(TreasureMapNodeId(2))
        assert node is not None and not node.defeated
        assert (node.coins_in_rubies, node.stone_in_rubies, node.wood_in_rubies) == (40, 30, 20)
        assert [(good.kind, good.amount) for good in node.paid_goods] == [(CollectableKind.WOOD, 500)]
        assert node.remaining_cooldown_seconds(node.received_at + 20) == pytest.approx(100)
        assert treasure_map.node(TreasureMapNodeId(1)).defeated  # type: ignore[union-attr]

    def test_the_transfers_and_storage(self):
        (treasure_map,) = parse_response("tmp", tmp(MAP_ROW)).maps  # type: ignore[union-attr]
        goods = treasure_map.goods_transfer
        assert goods is not None and goods.remaining_seconds(goods.received_at + 100) == pytest.approx(500)
        assert [(good.kind, good.amount) for good in goods.goods] == [
            (CollectableKind.STONE, 1000),
            (CollectableKind.FOOD, 200),
        ]
        assert treasure_map.unit_transfer is not None and treasure_map.unit_transfer.units == {Unit.SWORDMAN: 50}
        storage = treasure_map.storage
        assert (storage.food_capacity, storage.wood_capacity, storage.stone_capacity) == (9000, 8000, 7000)
        assert (storage.food, storage.wood, storage.stone, storage.free_unit_slots) == (100, 200, 300, 250)

    def test_a_bare_row_reads_as_the_client_defaults_it(self):
        # parseGoodsTransfer and parseTroopsTransfer drop a falsy block, parseStorage zeroes a missing one,
        # and RS 0 or -1 leaves no end
        (treasure_map,) = parse_response("tmp", tmp({"MID": "7", "RT": 0, "RS": 0})).maps  # type: ignore[union-attr]
        assert treasure_map.map_id == 7 and treasure_map.nodes == ()
        assert treasure_map.goods_transfer is None and treasure_map.unit_transfer is None
        assert treasure_map.storage.unit_capacity == 0 and treasure_map.pieces_found == 0
        assert treasure_map.remaining_seconds() is None

    def test_the_replies_that_carry_a_tmp(self):
        reply = parse_response("tcn", {"tmp": tmp(MAP_ROW)})
        assert isinstance(reply, TreasureNodeClickResponse) and reply.treasure_maps is not None
        finished = parse_response("tfm", {"thi": {"MID": 51}, "tmp": tmp(full=True)})
        assert isinstance(finished, FinishTreasureMapResponse)
        assert finished.treasure_hunt is not None and finished.treasure_hunt.map_id == 51
        assert isinstance(parse_response("tbm", {}), BuyTreasureMapPiecesResponse)
        hunt = parse_response("thi", {"MID": -1})
        assert isinstance(hunt, TreasureHuntInfoResponse) and hunt.map_id == NO_TREASURE_MAP

    def test_map_and_node_ids_are_typed_and_none_stays_minus_one_without_a_warning(self, caplog):
        reply = TreasureMapsResponse.model_validate(tmp(MAP_ROW, full=True))
        (treasure_map,) = reply.maps
        assert treasure_map.map_id is TreasureMapId.UNDERWORLD_NORMAL
        assert [node.node_id for node in treasure_map.nodes] == [TreasureMapNodeId(1), TreasureMapNodeId(2)]
        assert treasure_map.node(TreasureMapNodeId(2)) is treasure_map.nodes[1]
        hunt = parse_response("thi", {"MID": 51})
        assert isinstance(hunt, TreasureHuntInfoResponse) and hunt.map_id is TreasureMapId.SWINE_KING
        with caplog.at_level("WARNING"):
            assert GetTreasureMapsRequest(map_id=NO_TREASURE_MAP).map_id == -1
            assert TreasureHuntInfoResponse.model_validate({"MID": "-1"}).map_id == -1
        assert not caplog.records


class TestState:
    def test_the_login_brings_the_maps_and_the_hunt(self):
        state = logged_in_state(tmp=tmp(MAP_ROW, full=True), thi={"MID": 50})
        maps = state.get_treasure_maps()
        assert maps is not None and list(maps) == [23]
        assert state.get_treasure_hunt_map_id() == 50
        assert state.get_last_packet_time("tmp") is not None

    def test_a_partial_tmp_updates_the_maps_it_sends(self):
        state = GameState()
        state.update_from_packet("tmp", tmp(MAP_ROW, {"MID": 50, "PF": 1}, full=True))
        # parse_TMP keeps the maps when UA is not 1; a node left out keeps what was known of it,
        # one sent again keeps its paid goods without a G and stays defeated
        state.update_from_packet("tcn", {"tmp": tmp({"MID": 23, "PF": 4, "N": [{"NID": 1, "A": 0}, {"NID": 2}]})})
        maps = state.get_treasure_maps()
        assert maps is not None and set(maps) == {23, 50}
        updated = maps[23]
        assert updated.pieces_found == 4 and updated.goods_transfer is None
        assert updated.node(TreasureMapNodeId(1)).defeated  # type: ignore[union-attr]
        node = updated.node(TreasureMapNodeId(2))
        assert node is not None and [good.amount for good in node.paid_goods] == [500] and node.cooldown_seconds == 0

    def test_a_full_list_replaces_the_maps(self):
        state = GameState()
        state.update_from_packet("tmp", tmp(MAP_ROW, full=True))
        state.update_from_packet("tgt", {"tmp": tmp({"MID": 50}, full=True)})
        assert list(state.get_treasure_maps() or {}) == [50]

    @pytest.mark.parametrize(
        ("command", "payload"),
        [
            ("tut", {"tmp": tmp({"MID": 50})}),
            ("tkt", {"tmp": tmp({"MID": 50}), "gcu": {"C1": 10, "C2": 5}}),
            ("msm", {"tmp": tmp({"MID": 50})}),
        ],
    )
    def test_each_reply_with_a_tmp_updates_the_maps(self, command, payload):
        state = GameState()
        state.update_from_packet(command, payload)
        assert list(state.get_treasure_maps() or {}) == [50]

    def test_tfm_moves_the_hunt_on(self):
        state = GameState()
        state.update_from_packet("thi", {"MID": 50})
        state.update_from_packet("tfm", {"thi": {"MID": 51}, "tmp": tmp({"MID": 51}, full=True)})
        assert state.get_treasure_hunt_map_id() == 51 and list(state.get_treasure_maps() or {}) == [51]

    def test_a_refused_reply_changes_nothing(self):
        state = GameState()
        state.update_from_packet("tcn", {"tmp": tmp({"MID": 50})}, error_code=1)
        state.update_from_packet("thi", {"MID": 50}, error_code=1)
        assert state.get_treasure_maps() is None and state.get_treasure_hunt_map_id() is None

    def test_a_season_that_ends_takes_its_map(self):
        # CastleTreasureMapData.onSpecialEventRemoved drops the map of an ASeasonEventVO
        state = GameState()
        state.update_from_packet("sei", {"E": [{"EID": 64, "RS": 600, "UL": {"UL": 1, "MID": 23}}]})
        state.update_from_packet("tmp", tmp(MAP_ROW, {"MID": 50}, full=True))
        state.update_from_packet("see", {"EID": 64})
        assert list(state.get_treasure_maps() or {}) == [50]

    def test_a_reset_forgets_the_maps(self):
        state = logged_in_state(tmp=tmp(MAP_ROW, full=True), thi={"MID": 50})
        state.reset()
        assert state.get_treasure_maps() is None and state.get_treasure_hunt_map_id() is None


class TestService:
    def test_the_reads_hand_out_the_state(self):
        client = make_client(state=logged_in_state(tmp=tmp(MAP_ROW, full=True), thi={"MID": 50}))
        assert list(client.map.treasure_maps or {}) == [23]
        assert client.map.treasure_hunt_map_id == 50

    def test_get_treasure_maps(self):
        client = make_client({"tmp": xt_packet("tmp", tmp(MAP_ROW, full=True))})
        reply = client.map.get_treasure_maps(23)
        assert conn(client).request_payloads == [("tmp", {"MID": 23})]
        assert [treasure_map.map_id for treasure_map in reply.maps] == [23]

    def test_buy_treasure_map_pieces_needs_consent(self):
        client = make_client({"tbm": xt_packet("tbm", {})})
        with pytest.raises(ValueError, match="spend_rubies"):
            client.map.buy_treasure_map_pieces(50, 2)
        with pytest.raises(ValueError, match="1 piece at least"):
            client.map.buy_treasure_map_pieces(50, 0, spend_rubies=True)
        assert conn(client).request_payloads == []
        client.map.buy_treasure_map_pieces(50, 2, spend_rubies=True)
        assert conn(client).request_payloads == [("tbm", {"A": 2, "MID": 50})]

    def test_a_refused_purchase_raises(self):
        client = make_client({"tbm": xt_packet("tbm", error_code=21)})
        with pytest.raises(CommandError):
            client.map.buy_treasure_map_pieces(50, 1, spend_rubies=True)

    def test_finish_treasure_map(self):
        client = make_client({"tfm": xt_packet("tfm", {"thi": {"MID": 51}, "tmp": tmp(full=True)})})
        reply = client.map.finish_treasure_map(50)
        assert conn(client).request_payloads == [("tfm", {"MID": 50})]
        assert reply.treasure_hunt is not None and reply.treasure_hunt.map_id == 51
