"""Sending resources, the market overview, kingdom transfers, mines and resource carts."""

from __future__ import annotations

import pytest

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
from empire_core.castle.models.support import (
    GetTravelInfoRequest,
    GetTravelInfoResponse,
    SendSupportResponse,
    SendTroopsRequest,
    SendTroopsResponse,
)
from empire_core.castle.models.transfers import (
    KingdomGoodsTransferRequest,
    KingdomGoodsTransferResponse,
    KingdomUnitTransferRequest,
    KingdomUnitTransferResponse,
    MinuteSkipKingdomTransferRequest,
    MinuteSkipKingdomTransferResponse,
)
from empire_core.commanders import CommanderEffect
from empire_core.enums import GGEError, Kingdom, KingdomTransferType, MarketScope, Resource, ResourceCartType
from empire_core.exceptions import CommandError, UnsendableGoodsError
from empire_core.gamedata import Currency, Tool, Unit, WodAmount
from empire_core.protocol.models import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import (
    COIN_HORSE,
    RUBY_HORSE,
    StubPlayer,
    StubState,
    conn,
    make_client,
    with_horses,
    xt_packet,
)

# =============================================================================
# crm
# =============================================================================


class TestSendResources:
    def test_the_request_follows_the_client(self):
        # C2SCreateMarketMovementVO: KID to SD initialised, G set after them
        payload = CreateMarketMovementRequest(
            kingdom_id=Kingdom.ICE,
            source_castle_id=1234,
            target_x=10,
            target_y=20,
            horse_booster_id=-1,
            feathers=1,
            slowdown=30,
            goods={Resource.WOOD: 100},
        ).to_payload()
        assert payload == {"KID": 2, "SID": 1234, "TX": 10, "TY": 20, "HBW": -1, "PTT": 1, "SD": 30, "G": [["W", 100]]}
        assert list(payload) == ["KID", "SID", "TX", "TY", "HBW", "PTT", "SD", "G"]

    def test_goods_read_as_the_client_s_cost_rows_add_up(self):
        # CollectableParserC2SCosts.createCostsListForServer combines a repeated item before sending
        request = CreateMarketMovementRequest.model_validate(
            {"SID": 1, "TX": 2, "TY": 3, "G": [["W", 100], ["S", 5], ["W", 20]]}
        )

        assert request.goods == {Resource.WOOD: 120, Resource.STONE: 5}
        assert request.to_payload()["G"] == [["W", 120], ["S", 5]]

    def test_send_resources(self):
        client = with_horses(make_client(castles=[(1234, Kingdom.ICE)]))
        goods = {Resource.WOOD: 100, Resource.STONE: 50}
        assert client.castle.send_resources(1234, 10, 20, goods, horse_booster_id=COIN_HORSE) is True
        assert conn(client).request_payloads == [
            (
                "crm",
                {
                    "KID": 2,
                    "SID": 1234,
                    "TX": 10,
                    "TY": 20,
                    "HBW": 1001,
                    "PTT": 0,
                    "SD": 0,
                    "G": [["W", 100], ["S", 50]],
                },
            )
        ]

    @pytest.mark.parametrize("kwargs", [{"horse_booster_id": RUBY_HORSE}, {"slowdown": 30}])
    def test_a_horse_or_slowdown_that_costs_rubies_needs_spend_rubies(self, kwargs):
        # CastlePostSendGoodsDialog.getBoostCostC2, ACastlePostActionDialog.getTotalCostsC2
        client = with_horses(make_client(castles=[(1234, Kingdom.GREEN)]))
        with pytest.raises(ValueError, match="spend_rubies=True"):
            client.castle.send_resources(1234, 10, 20, {Resource.WOOD: 1}, **kwargs)
        assert conn(client).request_payloads == []
        assert client.castle.send_resources(1234, 10, 20, {Resource.WOOD: 1}, spend_rubies=True, **kwargs) is True

    def test_feathers_send_no_horse(self):
        client = make_client(castles=[(1234, Kingdom.GREEN)])
        client.castle.send_resources(1234, 10, 20, {Resource.WOOD: 1}, horse_booster_id=5, feathers=True)
        payload = conn(client).request_payloads[0][1]
        assert (payload["HBW"], payload["PTT"]) == (-1, 1)

    def test_the_resources_are_the_client_server_keys(self):
        # CollectableItem*VO.SERVER_KEY of the send dialog's three tabs
        assert {r.name: r.value for r in Resource} == {
            "WOOD": "W",
            "STONE": "S",
            "FOOD": "F",
            "COAL": "C",
            "OIL": "O",
            "GLASS": "G",
            "IRON": "I",
            "HONEY": "HONEY",
            "MEAD": "MEAD",
            "BEEF": "BEEF",
        }

    @pytest.mark.parametrize(
        ("goods", "sent"),
        [
            ({Resource.FOOD: 1, Resource.WOOD: 3}, [["F", 1], ["W", 3]]),
            ({Resource.IRON: 2, Resource.COAL: 1}, [["I", 2], ["C", 1]]),
            ({Resource.MEAD: 3, Resource.HONEY: 1}, [["MEAD", 3], ["HONEY", 1]]),
        ],
    )
    def test_a_legend_sends_one_tab_in_the_given_order(self, goods, sent):
        player = StubPlayer(level=70)
        player.legendary_level = 5
        client = make_client(state=StubState(local_player=player), castles=[(1234, Kingdom.FIRE)])
        client.castle.send_resources(1234, 10, 20, goods)
        assert conn(client).request_payloads[0][1]["G"] == sent

    @pytest.mark.parametrize(
        "goods",
        [
            {Resource.WOOD: 1, Resource.COAL: 1},
            {Resource.COAL: 1, Resource.HONEY: 1},
            {Resource.FOOD: 1, Resource.BEEF: 1},
        ],
    )
    def test_goods_from_two_tabs_raise_and_send_nothing(self, goods):
        # Live, the server refuses a crm mixing tabs with INVALID_PARAMETER_VALUE
        player = StubPlayer(level=70)
        player.legendary_level = 5
        client = make_client(state=StubState(local_player=player), castles=[(1234, Kingdom.FIRE)])
        with pytest.raises(UnsendableGoodsError, match="one tab"):
            client.castle.send_resources(1234, 10, 20, goods)
        assert conn(client).request_payloads == []

    def test_goods_are_not_checked_by_level_before_the_player_is_known(self):
        client = make_client(castles=[(1234, Kingdom.GREEN)])
        client.castle.send_resources(1234, 10, 20, {Resource.COAL: 1})
        assert conn(client).request_payloads[0][1]["G"] == [["C", 1]]

    @pytest.mark.parametrize(
        "goods",
        [
            {},
            {Resource.WOOD: 0},
            {Resource.WOOD: -5},
            {Resource.WOOD: 1.5},
            {Resource.WOOD: True},
            {"A": 10},
            {"X": 10},
        ],
    )
    def test_unsendable_goods_raise_and_send_nothing(self, goods):
        client = make_client(castles=[(1234, Kingdom.GREEN)])
        with pytest.raises(UnsendableGoodsError) as raised:
            client.castle.send_resources(1234, 10, 20, goods)
        assert raised.value.goods is goods
        assert conn(client).request_payloads == []

    @pytest.mark.parametrize("resource", [Resource.COAL, Resource.IRON, Resource.HONEY, Resource.BEEF])
    def test_below_legend_level_only_classic_goods_are_sent(self, resource):
        client = make_client(state=StubState(local_player=StubPlayer(level=69)), castles=[(1234, Kingdom.GREEN)])
        with pytest.raises(UnsendableGoodsError):
            client.castle.send_resources(1234, 10, 20, {resource: 1})
        assert conn(client).request_payloads == []

        client.castle.send_resources(1234, 10, 20, {Resource.WOOD: 1, Resource.STONE: 2, Resource.FOOD: 3})
        assert conn(client).request_payloads[0][1]["G"] == [["W", 1], ["S", 2], ["F", 3]]

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
        payload = KingdomUnitTransferRequest(
            source_castle_id=1234,
            source_kingdom_id=Kingdom.GREEN,
            target_kingdom_id=Kingdom.ICE,
            units=(WodAmount(1, 5),),
        ).to_payload()
        assert payload == {"SCID": 1234, "SKID": 0, "TKID": 2, "CID": -1, "A": [[1, 5]]}
        assert list(payload) == ["SCID", "SKID", "TKID", "CID", "A"]

    def test_transfer_units_to_kingdom(self):
        client = make_client(castles=[(1234, Kingdom.ICE)])
        assert client.castle.transfer_units_to_kingdom(1234, Kingdom.FIRE, {620: 10}) is True
        assert conn(client).request_payloads == [
            ("kut", {"SCID": 1234, "SKID": 2, "TKID": 3, "CID": -1, "A": [[620, 10]]})
        ]

    def test_the_reply(self):
        reply = parse_response("kut", {"gcu": {"C1": 1}, "gui": {}, "kpi": {}})
        assert isinstance(reply, KingdomUnitTransferResponse) and reply.currencies is not None


# =============================================================================
# kgt
# =============================================================================


class TestKingdomGoodsTransfer:
    def test_the_request_follows_the_client(self):
        # C2SKingdomGoodsTransferVO: SCID, SKID and TKID initialised, G set after them
        payload = KingdomGoodsTransferRequest(
            source_castle_id=1234,
            source_kingdom_id=Kingdom.GREEN,
            target_kingdom_id=Kingdom.ICE,
            goods={Resource.WOOD: 100, Resource.FOOD: 5},
        ).to_payload()
        assert payload == {"SCID": 1234, "SKID": 0, "TKID": 2, "G": [["W", 100], ["F", 5]]}
        assert list(payload) == ["SCID", "SKID", "TKID", "G"]

    def test_transfer_goods_to_kingdom_reads_the_source_kingdom(self):
        client = make_client(castles=[(1234, Kingdom.ICE), (99, Kingdom.FIRE)])
        assert client.castle.transfer_goods_to_kingdom(1234, Kingdom.FIRE, {Resource.STONE: 300}) is True
        assert conn(client).request_payloads == [("kgt", {"SCID": 1234, "SKID": 2, "TKID": 3, "G": [["S", 300]]})]

    @pytest.mark.parametrize(
        ("source", "target"),
        [
            # CastleTransferResToKingdomProperties.exceptingKingdomIDs: the target kingdom and Berimond
            (Kingdom.ICE, Kingdom.ICE),
            (Kingdom.BERIMOND, Kingdom.GREEN),
        ],
    )
    def test_a_source_the_client_leaves_out_raises(self, source, target):
        client = make_client(castles=[(1234, source), (99, Kingdom.GREEN), (98, Kingdom.ICE)])
        with pytest.raises(ValueError, match="from a castle in"):
            client.castle.transfer_goods_to_kingdom(1234, target, {Resource.WOOD: 1})
        assert conn(client).request_payloads == []

    def test_a_kingdom_without_your_castle_raises(self):
        # targetInitialized needs a castle of yours in the target kingdom
        client = make_client(castles=[(1234, Kingdom.GREEN)])
        with pytest.raises(ValueError, match="No castle of yours"):
            client.castle.transfer_goods_to_kingdom(1234, Kingdom.SANDS, {Resource.WOOD: 1})
        assert conn(client).request_payloads == []

    @pytest.mark.parametrize("goods", [{}, {Resource.WOOD: 0}, {Resource.WOOD: 1, Resource.COAL: 1}])
    def test_goods_are_checked_as_a_market_send(self, goods):
        player = StubPlayer(level=70)
        player.legendary_level = 5
        client = make_client(state=StubState(local_player=player), castles=[(1234, Kingdom.GREEN), (99, Kingdom.FIRE)])
        with pytest.raises(UnsendableGoodsError):
            client.castle.transfer_goods_to_kingdom(1234, Kingdom.FIRE, goods)
        assert conn(client).request_payloads == []

    def test_below_legend_level_only_classic_goods(self):
        client = make_client(
            state=StubState(local_player=StubPlayer(level=70)), castles=[(1234, Kingdom.GREEN), (99, Kingdom.FIRE)]
        )
        with pytest.raises(UnsendableGoodsError, match="below legend level"):
            client.castle.transfer_goods_to_kingdom(1234, Kingdom.FIRE, {Resource.COAL: 1})

    def test_the_reply(self):
        reply = parse_response("kgt", {"gcu": {"C1": 7}, "grc": {"AID": 1234, "W": 900}, "kpi": {"RT": []}})
        assert isinstance(reply, KingdomGoodsTransferResponse)
        assert reply.currencies is not None and reply.currencies.coins == 7
        assert reply.resources is not None and reply.resources.wood == 900


# =============================================================================
# msk
# =============================================================================


class TestKingdomTransferMinuteSkip:
    def test_the_request_follows_the_client(self):
        # C2SMinuteSkipKingdomTransferVO: MST, then KID and TT through toString()
        payload = MinuteSkipKingdomTransferRequest(
            minute_skip=Currency.SKIP_5_MINUTES, kingdom_id=Kingdom.FIRE, transfer_type=KingdomTransferType.GOODS
        ).to_payload()
        assert payload == {"MST": "MS2", "KID": "3", "TT": "2"}
        assert list(payload) == ["MST", "KID", "TT"]

    def test_skip_kingdom_transfer_time(self):
        client = make_client()
        assert client.castle.skip_kingdom_transfer_time(Kingdom.ICE, KingdomTransferType.UNITS, "MS1") is True
        assert conn(client).request_payloads == [("msk", {"MST": "MS1", "KID": "2", "TT": "1"})]

    @pytest.mark.parametrize("minute_skip", [Currency.CONSTRUCTION_TOKEN, "LT", "MSX", Currency.FAST_TRAVEL_FEATHERS])
    def test_a_currency_that_is_no_minute_skip_is_refused(self, minute_skip: Currency | str):
        # CurrencyData.getMinuteSkips: only the minute skip id range, 1000-1999
        client = make_client()
        with pytest.raises(ValueError, match="no minute skip"):
            client.castle.skip_kingdom_transfer_time(Kingdom.ICE, KingdomTransferType.GOODS, minute_skip)
        assert conn(client).request_payloads == []

    def test_a_minute_skip_you_hold_none_of_is_refused(self):
        # CastleMinuteSkipDialog.showLoaded lists only the skips with an amount above 0
        state = GameState()
        state.update_from_packet("gbd", {"gpi": {"PID": 1, "PN": "me"}})
        state.update_from_packet("sce", [["MS5", 0], ["MS99", 1]])  # type: ignore[arg-type]
        client = make_client(state=state)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="SKIP_1_HOUR"):
            client.castle.skip_kingdom_transfer_time(Kingdom.ICE, KingdomTransferType.GOODS, Currency.SKIP_1_HOUR)
        with pytest.raises(ValueError, match="SKIP_5_HOURS"):
            client.castle.skip_kingdom_transfer_time(Kingdom.ICE, KingdomTransferType.GOODS, Currency.SKIP_5_HOURS)
        assert conn(client).request_payloads == []
        assert client.castle.skip_kingdom_transfer_time(Kingdom.ICE, KingdomTransferType.GOODS, "MS99") is True

    def test_before_the_special_currencies_arrive_the_skip_goes_out(self):
        state = GameState()
        state.update_from_packet("gbd", {"gpi": {"PID": 1, "PN": "me"}})
        client = make_client(state=state)  # type: ignore[arg-type]
        assert client.castle.skip_kingdom_transfer_time(Kingdom.ICE, KingdomTransferType.GOODS, "MS5") is True

    def test_the_reply(self):
        assert isinstance(parse_response("msk", {"kpi": {"UT": []}}), MinuteSkipKingdomTransferResponse)


# =============================================================================
# cat
# =============================================================================


class TestSendTroops:
    def test_the_request_follows_the_client(self):
        # C2SCreateArmyTravelMovementVO: SX to SD initialised, A set after them
        payload = SendTroopsRequest(
            source_x=100,
            source_y=200,
            target_x=110,
            target_y=205,
            kingdom_id=Kingdom.GREEN,
            commander_id=5,
            units=(WodAmount(620, 10),),
        ).to_payload()
        assert list(payload) == ["SX", "SY", "TX", "TY", "KID", "LID", "WT", "HBW", "BPC", "PTT", "SD", "A"]
        assert payload == {
            "SX": 100,
            "SY": 200,
            "TX": 110,
            "TY": 205,
            "KID": 0,
            "LID": 5,
            "WT": 0,
            "HBW": -1,
            "BPC": 0,
            "PTT": 0,
            "SD": 0,
            "A": [[620, 10]],
        }

    def test_send_troops_pays_nothing_by_default(self):
        client = make_client()
        assert client.castle.send_troops(100, 200, 110, 205, {620: 10, 649: 2}, commander_id=5) is True
        assert conn(client).request_payloads == [
            (
                "cat",
                {
                    "SX": 100,
                    "SY": 200,
                    "TX": 110,
                    "TY": 205,
                    "KID": 0,
                    "LID": 5,
                    "WT": 0,
                    "HBW": -1,
                    "BPC": 0,
                    "PTT": 0,
                    "SD": 0,
                    "A": [[620, 10], [649, 2]],
                },
            )
        ]

    def test_feathers_send_no_horse(self):
        client = make_client()
        client.castle.send_troops(100, 200, 110, 205, {620: 1}, commander_id=5, horse_booster_id=3, feathers=True)
        payload = conn(client).request_payloads[0][1]
        assert (payload["HBW"], payload["PTT"]) == (-1, 1)

    def test_the_options(self):
        client = make_client()
        client.castle.send_troops(
            100,
            200,
            110,
            205,
            {620: 1},
            commander_id=-14,
            kingdom_id=Kingdom.ICE,
            use_premium_commander=True,
            spend_rubies=True,
            horse_booster_id=3,
            slowdown=60,
        )
        payload = conn(client).request_payloads[0][1]
        assert (payload["KID"], payload["LID"], payload["BPC"], payload["HBW"], payload["PTT"], payload["SD"]) == (
            2,
            -14,
            1,
            3,
            0,
            60,
        )

    def test_a_refusal_is_false(self):
        client = make_client({"cat": xt_packet("cat", error_code=92)})
        assert client.castle.send_troops(100, 200, 110, 205, {620: 1}, commander_id=5) is False

    def test_the_reply(self):
        # CATCommand reads O, A and gcu
        reply = parse_response("cat", {"O": [], "A": {"M": {"MID": 1}}, "gcu": {"C1": 900, "C2": 4}})
        assert isinstance(reply, SendTroopsResponse)
        assert reply.currencies is not None and (reply.currencies.coins, reply.currencies.rubies) == (900, 4)


# =============================================================================
# cmr / rcc
# =============================================================================


class TestCollect:
    def test_collect_mine(self):
        assert CollectMineResourcesRequest(object_id=42).to_payload() == {"OID": 42}
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
        assert CollectResourceCartRequest(cart_type=ResourceCartType.FOOD).to_payload() == {"RT": 2}
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


# =============================================================================
# sti
# =============================================================================

STI_REPLY: dict = {
    "SCID": 2003,
    "KID": 0,
    "gaa": {"AI": [2, 620, 231, -1, 0, -1, 0], "OI": {"OID": 1001, "N": "Me", "L": 70}},
    "gui": {"I": [[620, 10], [649, 2]], "SHI": [[10, 5]]},
    "AE": [[63, [10.0], "kingdom"]],
    "gli": {"C": [{"ID": 5, "WID": 2, "N": "", "EQ": []}], "B": []},
}


class TestTravelInfo:
    def test_the_request_follows_the_client(self):
        # C2STroopSupportInfoVO takes the target first but initialises SX, SY, TX, TY, KID
        payload = GetTravelInfoRequest(
            source_x=100, source_y=200, target_x=110, target_y=205, kingdom_id=Kingdom.ICE
        ).to_payload()
        assert payload == {"SX": 100, "SY": 200, "TX": 110, "TY": 205, "KID": 2}
        assert list(payload) == ["SX", "SY", "TX", "TY", "KID"]

    def test_get_travel_info(self):
        client = make_client({"sti": xt_packet("sti", STI_REPLY)})
        info = client.castle.get_travel_info(100, 200, 110, 205, kingdom_id=Kingdom.SANDS)

        assert conn(client).request_payloads == [("sti", {"SX": 100, "SY": 200, "TX": 110, "TY": 205, "KID": 1})]
        assert (info.source_castle_id, info.kingdom_id) == (2003, Kingdom.GREEN)
        assert info.units.units == {Tool.SHIELDS: 10, Tool.ELITELADDER: 2}
        assert info.units.stronghold == {Unit.ELITE_RANKREWARDRANGE: 5}
        assert info.target_area.area is not None
        assert info.target_area.owner is not None and info.target_area.owner.owner_id == 1001
        assert info.area_effects == [CommanderEffect(effect_id=63, values=[10.0], source="kingdom")]
        assert "AE" not in (info.model_extra or {})

    def test_the_owner_is_one_record(self):
        # CastleTroopSupportVO reads gaa.OI with parseOwnerInfo, which takes no record without an OID
        reply = parse_response("sti", {**STI_REPLY, "gaa": {"OI": {"N": "nobody"}}})
        assert isinstance(reply, GetTravelInfoResponse)
        assert reply.target_area.owner is None and reply.target_area.area is None
        listed = parse_response("sti", {**STI_REPLY, "gaa": {"OI": [{"OID": 1001}]}})
        assert isinstance(listed, GetTravelInfoResponse) and listed.target_area.owner is None

    def test_a_source_that_is_not_yours_raises(self):
        client = make_client({"sti": xt_packet("sti", {}, error_code=GGEError.NOT_IN_OWNED_CASTLE)})
        with pytest.raises(CommandError) as raised:
            client.castle.get_travel_info(100, 200, 110, 205)
        assert raised.value.error is GGEError.NOT_IN_OWNED_CASTLE
