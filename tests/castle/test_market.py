"""Sending resources, the market overview, kingdom transfers, mines and resource carts."""

from __future__ import annotations

from empire_core.castle.models.collect import (
    CollectMineResourcesRequest,
    CollectMineResourcesResponse,
    CollectResourceCartRequest,
    CollectResourceCartResponse,
)
from empire_core.castle.models.market import (
    CreateMarketMovementRequest,
    CreateMarketMovementResponse,
    MarketInfoRequest,
    MarketInfoResponse,
)
from empire_core.castle.models.support import SendSupportResponse
from empire_core.castle.models.transfers import KingdomUnitTransferRequest, KingdomUnitTransferResponse
from empire_core.enums import Kingdom, MarketScope, ResourceCartType
from empire_core.protocol.models import parse_response
from tests.service_helpers import conn, make_client, xt_packet

# =============================================================================
# crm
# =============================================================================


class TestSendResources:
    def test_the_request_follows_the_client(self):
        # C2SCreateMarketMovementVO: KID to SD initialised, G set after them
        payload = CreateMarketMovementRequest(
            KID=Kingdom.ICE, SID=1234, TX=10, TY=20, HBW=-1, PTT=1, SD=30, G=[["W", 100]]
        ).to_payload()
        assert payload == {"KID": 2, "SID": 1234, "TX": 10, "TY": 20, "HBW": -1, "PTT": 1, "SD": 30, "G": [["W", 100]]}
        assert list(payload) == ["KID", "SID", "TX", "TY", "HBW", "PTT", "SD", "G"]

    def test_send_resources(self):
        client = make_client()
        assert client.castle.send_resources(1234, 10, 20, {"W": 100, "S": 50}, horses_type=5) is True
        assert conn(client).request_payloads == [
            (
                "crm",
                {"KID": 0, "SID": 1234, "TX": 10, "TY": 20, "HBW": 5, "PTT": 0, "SD": 0, "G": [["W", 100], ["S", 50]]},
            )
        ]

    def test_feathers_send_no_horse(self):
        client = make_client()
        client.castle.send_resources(1234, 10, 20, {"W": 1}, horses_type=5, feathers=True)
        payload = conn(client).request_payloads[0][1]
        assert (payload["HBW"], payload["PTT"]) == (-1, 1)

    def test_the_reply(self):
        reply = parse_response("crm", {"gcu": {"C1": 5}, "grc": {"AID": 1234, "W": 900}, "O": [], "A": {}})
        assert isinstance(reply, CreateMarketMovementResponse)
        assert reply.currencies is not None and reply.currencies.coins == 5
        assert reply.resources is not None and reply.resources.wood == 900


# =============================================================================
# cmi
# =============================================================================


class TestMarketInfo:
    def test_the_request_is_every_kingdom(self):
        # C2SMarketInfoVO: S is SCOPE_ALL_KINGDOMS, KID -1
        payload = MarketInfoRequest().to_payload()
        assert payload == {"S": MarketScope.ALL_KINGDOMS, "KID": -1}
        assert list(payload) == ["S", "KID"]

    def test_the_reply_lists_each_castle(self):
        payload = {
            "C": [
                {"KID": 0, "CID": 1234, "TC": 20, "AC": "15", "W": 100.7, "S": 5, "F": 6, "HONEY": 1, "AE": []},
                "junk",
                {"KID": 2, "CID": 5678, "TC": 5, "AC": 5},
            ]
        }
        client = make_client({"cmi": xt_packet("cmi", payload)})
        castles = client.castle.get_market_info()
        assert conn(client).request_payloads == [("cmi", {"S": 1, "KID": -1})]
        assert [(c.castle_id, c.kingdom_id, c.total_carriages, c.available_carriages) for c in castles] == [
            (1234, 0, 20, 15),
            (5678, 2, 5, 5),
        ]
        assert (castles[0].wood, castles[0].honey, castles[1].wood) == (100, 1, 0)
        assert isinstance(parse_response("cmi", payload), MarketInfoResponse)


# =============================================================================
# kut
# =============================================================================


class TestKingdomUnitTransfer:
    def test_the_request_follows_the_client(self):
        # C2SKingdomUnitTransferVO: SCID, SKID, TKID and CID initialised, A set after them
        payload = KingdomUnitTransferRequest(SCID=1234, SKID=Kingdom.GREEN, TKID=Kingdom.ICE, A=[[1, 5]]).to_payload()
        assert payload == {"SCID": 1234, "SKID": 0, "TKID": 2, "CID": -1, "A": [[1, 5]]}
        assert list(payload) == ["SCID", "SKID", "TKID", "CID", "A"]

    def test_transfer_units_to_kingdom(self):
        client = make_client()
        assert client.castle.transfer_units_to_kingdom(1234, Kingdom.FIRE, [[620, 10]]) is True
        assert conn(client).request_payloads == [
            ("kut", {"SCID": 1234, "SKID": 0, "TKID": 3, "CID": -1, "A": [[620, 10]]})
        ]

    def test_the_reply(self):
        reply = parse_response("kut", {"gcu": {"C1": 1}, "gui": {}, "kpi": {}})
        assert isinstance(reply, KingdomUnitTransferResponse) and reply.currencies is not None


# =============================================================================
# cmr / rcc
# =============================================================================


class TestCollect:
    def test_collect_mine(self):
        assert CollectMineResourcesRequest(OID=42).to_payload() == {"OID": 42}
        client = make_client()
        assert client.castle.collect_mine(42) is True
        assert conn(client).request_payloads == [("cmr", {"OID": 42})]

    def test_the_mine_reply(self):
        reply = parse_response(
            "cmr",
            {
                "gsm": {"M": [{"OID": 42, "RC": 3, "NC": 600, "C1": 250}, None, {"OID": 43, "RC": 0, "NC": -1}]},
                "gcu": {},
            },
        )
        assert isinstance(reply, CollectMineResourcesResponse) and reply.mines is not None
        assert [
            (m.object_id, m.remaining_collection_amount, m.next_collect_seconds, m.coins) for m in reply.mines.mines
        ] == [
            (42, 3, 600, 250),
            (43, 0, -1, None),
        ]

    def test_collect_resource_cart(self):
        # C2SIsoResourceCartCollectVO: RT is the cart's index, wood 0, stone 1, food 2
        assert CollectResourceCartRequest(RT=ResourceCartType.FOOD).to_payload() == {"RT": 2}
        client = make_client()
        assert client.castle.collect_resource_cart(ResourceCartType.STONE) is True
        assert conn(client).request_payloads == [("rcc", {"RT": 1})]

    def test_the_cart_reply(self):
        payload = {
            "RT": 0,
            "A": "500",
            "grc": {"AID": 1, "W": 1500},
            "rci": {"RC": [{"RT": 0, "A": 0, "RS": 3600}, {"RT": 1, "A": 20, "RS": 0}, {"RT": 7, "A": 1}]},
        }
        reply = parse_response("rcc", payload)
        assert isinstance(reply, CollectResourceCartResponse)
        assert (reply.cart_type, reply.amount) == (ResourceCartType.WOOD, 500)
        assert reply.resources is not None and reply.resources.wood == 1500
        assert reply.carts is not None
        assert [(c.cart_type, c.amount, c.remaining_seconds) for c in reply.carts.carts] == [
            (ResourceCartType.WOOD, 0, 3600),
            (ResourceCartType.STONE, 20, 0),
            (None, 1, None),
        ]


def test_the_support_reply_reads_currencies():
    reply = parse_response("cds", {"gcu": {"C2": 4}, "O": [], "A": {}})
    assert isinstance(reply, SendSupportResponse) and reply.currencies is not None and reply.currencies.rubies == 4
