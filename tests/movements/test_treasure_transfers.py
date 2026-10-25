"""Units and goods sent to a season's treasure map (tgt, tut) and the ruby skip of their transfer (tkt)."""

from __future__ import annotations

import pytest

from empire_core.enums import Kingdom, KingdomTransferType, Resource
from empire_core.exceptions import CommandError, UnsendableGoodsError
from empire_core.gamedata import WodAmount
from empire_core.movements import (
    TreasureMapGoodsTransferRequest,
    TreasureMapGoodsTransferResponse,
    TreasureMapTransferSkipRequest,
    TreasureMapTransferSkipResponse,
    TreasureMapUnitTransferRequest,
    TreasureMapUnitTransferResponse,
)
from empire_core.protocol.models import parse_response
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

TMP = {"UA": 0, "TM": [{"MID": 23, "PF": 1}]}


class TestGoodsTransfer:
    def test_the_request_follows_the_client(self):
        # C2STreasuremapGoodsTransferVO: MID, SCID and KID initialised, G set after them
        payload = TreasureMapGoodsTransferRequest(
            map_id=23, source_castle_id=1234, source_kingdom_id=Kingdom.ICE, goods={Resource.WOOD: 100}
        ).to_payload()
        assert payload == {"MID": 23, "SCID": 1234, "KID": 2, "G": [["W", 100]]}
        assert list(payload) == ["MID", "SCID", "KID", "G"]

    def test_the_reply(self):
        reply = parse_response("tgt", {"tmp": TMP})
        assert isinstance(reply, TreasureMapGoodsTransferResponse) and reply.treasure_maps is not None

    def test_transfer_goods_reads_the_source_kingdom(self):
        client = make_client({"tgt": xt_packet("tgt", {"tmp": TMP})}, castles=[(1234, Kingdom.FIRE)])
        client.movements.transfer_goods_to_treasure_map(23, 1234, {Resource.STONE: 300, Resource.FOOD: 5})
        assert conn(client).request_payloads == [
            ("tgt", {"MID": 23, "SCID": 1234, "KID": 3, "G": [["S", 300], ["F", 5]]})
        ]

    def test_only_classic_goods_go(self):
        client = make_client(castles=[(1234, Kingdom.GREEN)])
        with pytest.raises(UnsendableGoodsError):
            client.movements.transfer_goods_to_treasure_map(23, 1234, {Resource.COAL: 1})
        assert conn(client).request_payloads == []

    def test_a_berimond_castle_raises(self):
        # CastleTransferResToSeasonProperties.exceptingKingdomIDs: Berimond
        client = make_client(castles=[(1234, Kingdom.BERIMOND)])
        with pytest.raises(ValueError, match="Berimond"):
            client.movements.transfer_goods_to_treasure_map(23, 1234, {Resource.WOOD: 1})
        assert conn(client).request_payloads == []

    def test_a_refused_transfer_raises(self):
        client = make_client({"tgt": xt_packet("tgt", error_code=8)}, castles=[(1234, Kingdom.GREEN)])
        with pytest.raises(CommandError):
            client.movements.transfer_goods_to_treasure_map(23, 1234, {Resource.WOOD: 1})


class TestUnitTransfer:
    def test_the_request_follows_the_client(self):
        # C2STreasuremapUnitTransferVO: MID, SCID and KID initialised, I set after them
        payload = TreasureMapUnitTransferRequest(
            map_id=23, source_castle_id=1234, source_kingdom_id=Kingdom.GREEN, units=(WodAmount(620, 10),)
        ).to_payload()
        assert payload == {"MID": 23, "SCID": 1234, "KID": 0, "I": [[620, 10]]}
        assert list(payload) == ["MID", "SCID", "KID", "I"]

    def test_the_reply(self):
        reply = parse_response("tut", {"tmp": TMP})
        assert isinstance(reply, TreasureMapUnitTransferResponse) and reply.treasure_maps is not None

    def test_transfer_units(self):
        client = make_client({"tut": xt_packet("tut", {"tmp": TMP})}, castles=[(1234, Kingdom.SANDS)])
        client.movements.transfer_units_to_treasure_map(23, 1234, {620: 10})
        assert conn(client).request_payloads == [("tut", {"MID": 23, "SCID": 1234, "KID": 1, "I": [[620, 10]]})]

    def test_a_berimond_castle_raises(self):
        # CastleTransferTroopsToSeasonProperties.exceptingKingdomID: Berimond
        client = make_client(castles=[(1234, Kingdom.BERIMOND)])
        with pytest.raises(ValueError, match="Berimond"):
            client.movements.transfer_units_to_treasure_map(23, 1234, {620: 10})
        assert conn(client).request_payloads == []


class TestTransferSkip:
    def test_the_request_follows_the_client(self):
        payload = TreasureMapTransferSkipRequest(
            event_id=64, map_id=23, transfer_type=KingdomTransferType.GOODS
        ).to_payload()
        assert payload == {"EID": 64, "MID": 23, "TT": 2} and list(payload) == ["EID", "MID", "TT"]

    def test_the_reply(self):
        reply = parse_response("tkt", {"tmp": TMP, "gcu": {"C1": 10, "C2": 5}})
        assert isinstance(reply, TreasureMapTransferSkipResponse)
        assert reply.treasure_maps is not None and reply.currencies is not None

    def test_skip_names_the_season_of_the_map(self):
        state = logged_in_state(sei={"E": [{"EID": 64, "RS": 600, "UL": {"UL": 1, "MID": 23}}]})
        client = make_client({"tkt": xt_packet("tkt", {"tmp": TMP})}, state=state)
        with pytest.raises(ValueError, match="spend_rubies"):
            client.movements.skip_treasure_map_transfer(23, KingdomTransferType.UNITS)
        with pytest.raises(ValueError, match="No running season event"):
            client.movements.skip_treasure_map_transfer(99, KingdomTransferType.UNITS, spend_rubies=True)
        assert conn(client).request_payloads == []
        client.movements.skip_treasure_map_transfer(23, KingdomTransferType.UNITS, spend_rubies=True)
        assert conn(client).request_payloads == [("tkt", {"EID": 64, "MID": 23, "TT": 1})]
