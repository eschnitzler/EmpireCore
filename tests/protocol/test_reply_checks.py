"""Requests whose reply names what was asked for take only the reply that does (``accepts_reply``)."""

import pytest

from empire_core.alliance.models.info import GetAllianceInfoRequest
from empire_core.attack.models.send import CreateAttackRequest
from empire_core.castle.models.actions import JoinAreaRequest, SelectCastleRequest
from empire_core.castle.models.resources import GetResourcesRequest
from empire_core.castle.models.support import SendSupportRequest, SendTroopsRequest
from empire_core.defense.models import GetDefenseRequest
from empire_core.enums import Kingdom
from empire_core.exceptions import EmpireTimeoutError
from empire_core.map.models.areas import GetMapAreaRequest
from empire_core.movements.models import CancelMovementRequest
from empire_core.spy.models import SendSpyRequest, SpyScreenInfoRequest
from tests.service_helpers import conn, make_client, xt_packet


def movement(target: list, source: list, direction: int = 0) -> dict:
    return {"M": {"MID": 1, "T": 0, "TA": target, "SA": source, "D": direction}}


OWN = [1, 632, 243, 2001, 7]
TARGET = [2, 633, 244, 3001, -1]


class TestMapArea:
    request = GetMapAreaRequest(KID=Kingdom.GREEN, AX1=620, AY1=231, AX2=644, AY2=255)

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

    def test_corners_given_the_other_way_round(self):
        request = GetMapAreaRequest(KID=Kingdom.ICE, AX1=99, AY1=99, AX2=0, AY2=0)
        assert request.accepts_reply({"KID": 2, "AI": [[1, 50, 50]]})


class TestSpyScreen:
    request = SpyScreenInfoRequest(TX=633, TY=240, KID=Kingdom.GREEN)

    def test_the_target_s_reply(self):
        assert self.request.accepts_reply({"TX": 633.0, "TY": 240.0, "gaa": {"KID": 0, "AI": [[2, 633, 240]]}})

    def test_another_target_is_not_taken(self):
        assert not self.request.accepts_reply({"TX": 633.0, "TY": 244.0})

    def test_a_reply_without_a_position_is_taken_as_the_client_takes_it(self):
        assert self.request.accepts_reply({"GC": 3})
        assert self.request.accepts_reply({"TX": 0, "TY": 244})


class TestMovementSends:
    def test_spies_heading_out_and_their_way_home(self):
        request = SendSpyRequest(SID=2001, TX=633, TY=244)
        assert request.accepts_reply({"A": movement(TARGET, OWN)})
        # The server pushes the return as another csm: from the target back to your castle
        assert not request.accepts_reply({"A": movement(OWN, TARGET, direction=1)})

    def test_an_attack_support_and_troop_transfer(self):
        attack = CreateAttackRequest(SX=632, SY=243, TX=633, TY=244, LID=0)
        assert attack.accepts_reply({"AAM": movement(TARGET, OWN)})
        assert not attack.accepts_reply({"AAM": movement([2, 1, 1], OWN)})
        support = SendSupportRequest(SID=2001, TX=633, TY=244, LID=0, A=[])
        assert support.accepts_reply({"A": movement(TARGET, OWN)})
        troops = SendTroopsRequest(SX=632, SY=243, TX=633, TY=244, LID=0, A=[])
        assert not troops.accepts_reply({"A": movement(OWN, TARGET)})

    def test_a_reply_without_a_movement_is_taken(self):
        assert SendSpyRequest(SID=2001, TX=633, TY=244).accepts_reply({"O": []})


class TestIdEchoes:
    def test_alliance_info(self):
        request = GetAllianceInfoRequest(AID=190426)
        assert request.accepts_reply({"A": {"AID": 190426, "N": "Clan"}})
        assert not request.accepts_reply({"A": {"AID": 190427}})
        assert request.accepts_reply({"A": {"N": "no id"}})

    def test_castle_resources(self):
        request = GetResourcesRequest(AID=16654596, KID=Kingdom.GREEN)
        assert request.accepts_reply({"AID": 16654596, "KID": 0, "W": 1.0})
        assert not request.accepts_reply({"AID": 14733404, "KID": 0})

    def test_recall(self):
        request = CancelMovementRequest(MID=99090783)
        assert request.accepts_reply({"A": {"M": {"MID": 99090783}}})
        assert not request.accepts_reply({"A": {"M": {"MID": 99302849}}})

    def test_defense(self):
        request = GetDefenseRequest(CX=632, CY=243, AID=16654596)
        assert request.accepts_reply({"A": [1, 632, 243, 16654596]})
        assert not request.accepts_reply({"A": [1, 629, 235, 14733404]})

    def test_joining_a_castle_or_an_area(self):
        # JAACommand adopts the reply's kingdom, so a castle join checks nothing
        assert not hasattr(SelectCastleRequest(CID=16654596, KID=Kingdom.GREEN), "accepts_reply")
        area = JoinAreaRequest(PX=424, PY=894, KID=Kingdom.SANDS)
        assert area.accepts_reply({"KID": 1, "gca": {"A": [12, 424, 894]}})
        assert not area.accepts_reply({"KID": 1, "gca": {"A": [4, 626, 238]}})
        assert not area.accepts_reply({"KID": 0, "gca": {"A": [12, 424, 894]}})
        # A treasure camp's area is not read from gca.A
        assert area.accepts_reply({"KID": 1, "T": 8, "gca": {"A": [8, 22]}})


def test_request_packet_passes_the_request_s_check_on():
    client = make_client({"gaa": xt_packet("gaa", {"KID": 0, "AI": [[1, 5, 5]]})})
    request = GetMapAreaRequest(KID=Kingdom.GREEN, AX1=0, AY1=0, AX2=9, AY2=9)
    assert client.request_packet(request, "gaa").payload == {"KID": 0, "AI": [[1, 5, 5]]}
    conn(client).script["gaa"] = xt_packet("gaa", {"AI": [[2, 633, 244]]})
    with pytest.raises(EmpireTimeoutError):
        client.request_packet(request, "gaa")


def test_the_pushed_gaa_does_not_take_a_waiting_chunk_s_reply():
    from empire_core.network.connection import Connection
    from empire_core.protocol.packet import Packet

    conn = Connection("wss://example.invalid/")
    request = GetMapAreaRequest(KID=Kingdom.GREEN, AX1=630, AY1=180, AX2=719, AY2=269)
    waiter = conn.create_waiter("gaa", lambda reply: request.accepts_reply(reply.payload))
    conn._route_packet(Packet.from_bytes(b'%xt%gaa%1%0%{"AI":[[2,633,244,0,1,-3044784,0]]}%'))
    assert waiter.result is None
    conn._route_packet(Packet.from_bytes(b'%xt%gaa%1%0%{"KID":0,"AI":[[1,633,244,5,6]],"OI":[]}%'))
    assert waiter.result is not None and waiter.result.payload["KID"] == 0
