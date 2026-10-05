"""Requests whose reply names what was asked for take only the reply that does (``accepts_reply``)."""

import pytest

from empire_core.alliance.models.info import GetAllianceInfoRequest
from empire_core.army.models.production import GetProductionListRequest
from empire_core.attack.models.send import CreateAttackRequest
from empire_core.castle.models.actions import JoinAreaRequest, RenameCastleRequest, SelectCastleRequest
from empire_core.castle.models.resources import GetResourcesRequest
from empire_core.castle.models.support import SendSupportRequest, SendTroopsRequest
from empire_core.defense.models import GetDefenseRequest
from empire_core.enums import Kingdom, MapItemType, ProductionListId, RankingType
from empire_core.exceptions import EmpireTimeoutError
from empire_core.map.models.areas import GetMapAreaRequest
from empire_core.movements.models import CancelMovementRequest
from empire_core.ranking.models import (
    GetHighscoreRequest,
    GetRankingListRequest,
    GetRankingWindowRequest,
    SearchRankingListRequest,
)
from empire_core.spy.models import SendSpyRequest, SpyScreenInfoRequest
from tests.service_helpers import conn, make_client, xt_packet


def movement(target: list, source: list, direction: int = 0) -> dict:
    return {"M": {"MID": 1, "T": 0, "TA": target, "SA": source, "D": direction}}


OWN = [1, 632, 243, 2001, 7]
TARGET = [2, 633, 244, 3001, -1]


class TestMapArea:
    request = GetMapAreaRequest(kingdom=Kingdom.GREEN, x1=620, y1=231, x2=644, y2=255)

    def test_a_reply_for_this_rectangle(self):
        assert self.request.accepts_reply({"KID": 0, "AI": [[1, 620, 231], [2, 644, 255], [31, 0]], "OI": []})

    def test_a_row_outside_the_rectangle_is_another_request_s(self):
        assert not self.request.accepts_reply({"KID": 0, "AI": [[1, 620, 231], [2, 645, 240]]})

    def test_another_kingdom_is_not_taken(self):
        assert not self.request.accepts_reply({"KID": 2, "AI": [[1, 620, 231]]})

    def test_the_pushed_single_row_is_not_taken_even_inside_the_rectangle(self):
        assert not self.request.accepts_reply({"AI": [[2, 633, 244, 0, 1, -3044784, 0]]})
        assert not self.request.accepts_reply({"AI": [[2, 663, 244, 0, 1, -3044784, 0]]})

    def test_a_reply_without_a_kingdom_or_rows_is_taken(self):
        assert self.request.accepts_reply({"AI": [], "OI": []})
        assert self.request.accepts_reply({})

    def test_an_empty_reply_of_the_kingdom_matches(self):
        assert self.request.accepts_reply({"KID": 0, "AI": [], "OI": []})

    @pytest.mark.parametrize(
        ("x", "accepted"),
        [(630, True), ("630", True), (630.0, True), (True, False), (None, False), ("x", False), (2**1100, False)],
    )
    def test_a_position_is_read_as_a_number(self, x, accepted):
        assert self.request.accepts_reply({"KID": 0, "AI": [[1, 620, 231], [1, x, 240]]}) is accepted

    def test_corners_given_the_other_way_round(self):
        request = GetMapAreaRequest(kingdom=Kingdom.ICE, x1=99, y1=99, x2=0, y2=0)
        assert request.accepts_reply({"KID": 2, "AI": [[1, 50, 50]]})


class TestSpyScreen:
    request = SpyScreenInfoRequest(target_x=633, target_y=240, target_kingdom=Kingdom.GREEN)

    def test_the_target_s_reply(self):
        assert self.request.accepts_reply({"TX": 633.0, "TY": 240.0, "gaa": {"KID": 0, "AI": [[2, 633, 240]]}})

    def test_another_target_is_not_taken(self):
        assert not self.request.accepts_reply({"TX": 633.0, "TY": 244.0})

    def test_a_reply_without_a_position_is_taken_as_the_client_takes_it(self):
        assert self.request.accepts_reply({"GC": 3})
        assert self.request.accepts_reply({"TX": 0, "TY": 244})


class TestMovementSends:
    def test_spies_heading_out_and_their_way_home(self):
        request = SendSpyRequest(castle_id=2001, target_x=633, target_y=244)
        assert request.accepts_reply({"A": movement(TARGET, OWN)})
        # The server pushes the return as another csm: from the target back to your castle
        assert not request.accepts_reply({"A": movement(OWN, TARGET, direction=1)})

    def test_an_attack_support_and_troop_transfer(self):
        attack = CreateAttackRequest(source_x=632, source_y=243, target_x=633, target_y=244, commander_id=0)
        assert attack.accepts_reply({"AAM": movement(TARGET, OWN)})
        assert not attack.accepts_reply({"AAM": movement([2, 1, 1], OWN)})
        support = SendSupportRequest(source_castle_id=2001, target_x=633, target_y=244, commander_id=0, units=[])
        assert support.accepts_reply({"A": movement(TARGET, OWN)})
        troops = SendTroopsRequest(source_x=632, source_y=243, target_x=633, target_y=244, commander_id=0, units=[])
        assert not troops.accepts_reply({"A": movement(OWN, TARGET)})

    def test_a_reply_without_a_movement_is_taken(self):
        assert SendSpyRequest(castle_id=2001, target_x=633, target_y=244).accepts_reply({"O": []})


class TestIdEchoes:
    def test_alliance_info(self):
        request = GetAllianceInfoRequest(alliance_id=190426)
        assert request.accepts_reply({"A": {"AID": 190426, "N": "Clan"}})
        assert not request.accepts_reply({"A": {"AID": 190427}})
        assert request.accepts_reply({"A": {"N": "no id"}})

    def test_castle_resources(self):
        request = GetResourcesRequest(castle_id=16654596, kingdom_id=Kingdom.GREEN)
        assert request.accepts_reply({"AID": 16654596, "KID": 0, "W": 1.0})
        assert not request.accepts_reply({"AID": 14733404, "KID": 0})

    def test_recall(self):
        request = CancelMovementRequest(movement_id=99090783)
        assert request.accepts_reply({"A": {"M": {"MID": 99090783}}})
        assert not request.accepts_reply({"A": {"M": {"MID": 99302849}}})

    def test_defense(self):
        request = GetDefenseRequest(castle_x=632, castle_y=243, area_id=16654596)
        assert request.accepts_reply({"A": [1, 632, 243, 16654596]})
        assert not request.accepts_reply({"A": [1, 629, 235, 14733404]})

    def test_production_list(self):
        request = GetProductionListRequest(list_id=ProductionListId.SOLDIERS)
        assert request.accepts_reply({"LID": 0, "QS": []})
        assert request.accepts_reply({"LID": "0"})
        assert not request.accepts_reply({"LID": 1, "QS": []})
        # parse_SPL ignores a reply without LID
        assert not request.accepts_reply({"QS": []})
        # the server's answer for a list the castle cannot produce
        assert request.accepts_reply({})

    def test_castle_rename(self):
        request = RenameCastleRequest(
            castle_id=16654596, castle_name="Keep", castle_type=MapItemType.CASTLE, kingdom_id=Kingdom.ICE
        )
        assert request.accepts_reply({"CID": 16654596, "KID": 2, "P": 1})
        assert request.accepts_reply({"CID": 16654596})
        assert not request.accepts_reply({"CID": 14733404, "KID": 2})
        assert not request.accepts_reply({"CID": 16654596, "KID": 0})

    def test_joining_a_castle_or_an_area(self):
        # JAACommand adopts the reply's kingdom, so a castle join checks nothing
        assert not hasattr(SelectCastleRequest(castle_id=16654596, kingdom_id=Kingdom.GREEN), "accepts_reply")
        area = JoinAreaRequest(x=424, y=894, kingdom_id=Kingdom.SANDS)
        assert area.accepts_reply({"KID": 1, "gca": {"A": [12, 424, 894]}})
        assert not area.accepts_reply({"KID": 1, "gca": {"A": [4, 626, 238]}})
        assert not area.accepts_reply({"KID": 0, "gca": {"A": [12, 424, 894]}})
        # A treasure camp's area is not read from gca.A
        assert area.accepts_reply({"KID": 1, "T": 8, "gca": {"A": [8, 22]}})


class TestLeaderboards:
    page = GetRankingListRequest(list_type=RankingType.LONG_TERM_POINT_EVENT, league_type_id=3, max_results=8, rank=1)
    window = GetRankingWindowRequest(list_type=RankingType.LONG_TERM_POINT_EVENT, league_type_id=3, max_results=8)
    search = SearchRankingListRequest(list_type=RankingType.LONG_TERM_POINT_EVENT, search_value="name")

    def test_a_reply_for_the_list_asked_for(self):
        for request in (self.page, self.window, self.search):
            assert request.accepts_reply({"LT": 53, "LID": 3, "L": [], "T": 0})
            assert request.accepts_reply({"LT": "53", "L": []})

    def test_a_reply_for_another_list_is_not_taken(self):
        for request in (self.page, self.window, self.search):
            assert not request.accepts_reply({"LT": 40, "LID": 3, "L": []})

    def test_another_league_is_taken_as_the_client_adopts_it(self):
        for request in (self.page, self.window, self.search):
            assert request.accepts_reply({"LT": 53, "LID": 5, "L": []})

    def test_another_list_in_another_league_is_taken_for_pages(self):
        # onScoreDataReceived skips only when LT differs and the league, LID or -1, matches
        for request in (self.page, self.window):
            assert request.accepts_reply({"LT": 40, "LID": 5, "L": []})
        own_league = GetRankingListRequest(
            list_type=RankingType.PLAYER_LEGEND, league_type_id=-1, max_results=8, rank=1
        )
        assert not own_league.accepts_reply({"LT": 5, "L": []})
        assert own_league.accepts_reply({"LT": 5, "LID": 1, "L": []})
        assert not self.page.accepts_reply({"LT": None, "LID": 3, "L": []})

    def test_a_search_refuses_any_other_list(self):
        # The search sends no league, so the dialog's is unknown
        assert not self.search.accepts_reply({"LT": 40, "LID": 5, "L": []})

    def test_a_reply_without_a_list_is_taken(self):
        for request in (self.page, self.window, self.search):
            assert request.accepts_reply({"L": [], "T": 0})
            assert request.accepts_reply({})

    def test_highscores_check_nothing(self):
        # The highscore dialog switches to the list and league a reply names
        assert not hasattr(GetHighscoreRequest(list_type=RankingType.PLAYER_LEGEND, search_value="-1"), "accepts_reply")


def test_a_leaderboard_page_for_another_list_does_not_take_the_waiter():
    from empire_core.network.connection import Connection
    from empire_core.protocol.packet import Packet

    conn = Connection("wss://example.invalid/")
    request = GetRankingListRequest(
        list_type=RankingType.LONG_TERM_POINT_EVENT, league_type_id=3, max_results=8, rank=1
    )
    waiter = conn.create_waiter("llsp", lambda reply: request.accepts_reply(reply.payload))
    conn._route_packet(Packet.from_bytes(b'%xt%llsp%1%0%{"LT":40,"LID":3,"L":[],"T":0}%'))
    assert waiter.result is None
    conn._route_packet(Packet.from_bytes(b'%xt%llsp%1%0%{"LT":53,"LID":3,"L":[{"R":1,"S":9}],"T":1}%'))
    assert waiter.result is not None and waiter.result.payload["LT"] == 53


def test_a_leaderboard_error_goes_to_the_waiter():
    from empire_core.network.connection import Connection
    from empire_core.protocol.packet import Packet

    conn = Connection("wss://example.invalid/")
    request = GetRankingListRequest(
        list_type=RankingType.LONG_TERM_POINT_EVENT, league_type_id=3, max_results=8, rank=1
    )
    waiter = conn.create_waiter("llsp", lambda reply: request.accepts_reply(reply.payload))
    conn._route_packet(Packet.from_bytes(b"%xt%llsp%1%145%%"))
    assert waiter.result is not None and waiter.result.error_code == 145


def test_request_packet_passes_the_request_s_check_on():
    client = make_client({"gaa": xt_packet("gaa", {"KID": 0, "AI": [[1, 5, 5]]})})
    request = GetMapAreaRequest(kingdom=Kingdom.GREEN, x1=0, y1=0, x2=9, y2=9)
    assert client.request_packet(request, "gaa").payload == {"KID": 0, "AI": [[1, 5, 5]]}
    conn(client).script["gaa"] = xt_packet("gaa", {"AI": [[2, 633, 244]]})
    with pytest.raises(EmpireTimeoutError):
        client.request_packet(request, "gaa")


def test_the_pushed_gaa_does_not_take_a_waiting_chunk_s_reply():
    from empire_core.network.connection import Connection
    from empire_core.protocol.packet import Packet

    conn = Connection("wss://example.invalid/")
    request = GetMapAreaRequest(kingdom=Kingdom.GREEN, x1=630, y1=180, x2=719, y2=269)
    waiter = conn.create_waiter("gaa", lambda reply: request.accepts_reply(reply.payload))
    conn._route_packet(Packet.from_bytes(b'%xt%gaa%1%0%{"AI":[[2,633,244,0,1,-3044784,0]]}%'))
    assert waiter.result is None
    conn._route_packet(Packet.from_bytes(b'%xt%gaa%1%0%{"KID":0,"AI":[[1,633,244,5,6]],"OI":[]}%'))
    assert waiter.result is not None and waiter.result.payload["KID"] == 0
