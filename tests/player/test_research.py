"""Starting research and shortening it with a minute skip: res and msr."""

from __future__ import annotations

from empire_core.gamedata import Currency, Research
from empire_core.player import (
    SkipResearchRequest,
    SkipResearchResponse,
    StartResearchRequest,
    StartResearchResponse,
)
from empire_core.protocol.models import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet

REI = {"ARID": 172, "ARRT": 300, "BR": [1, 2, 171]}


class TestRequests:
    def test_res_sends_the_research_with_no_offer_and_no_rubies(self):
        # C2SResearchStartVO: RID, PO -1, PWR 0 as ResearchInfo.buyResearch sends it
        payload = StartResearchRequest(research_id=Research.MANEUVER_L1).to_payload()
        assert payload == {"RID": 1, "PO": -1, "PWR": 0}
        assert list(payload) == ["RID", "PO", "PWR"]

    def test_msr_sends_the_minute_skip_key(self):
        # CastleMinuteSkipDialog passes the currency's jsonKey
        assert SkipResearchRequest(minute_skip=Currency.SKIP_5_MINUTES).to_payload() == {"MST": "MS2"}


class TestReplies:
    def test_res(self):
        reply = parse_response("res", {"rei": REI, "gcu": {"C1": 10, "C2": 3}, "grc": {"AID": 5, "W": 7}})
        assert isinstance(reply, StartResearchResponse)
        assert reply.research is not None and reply.research.current_research_id == 172
        assert reply.currencies is not None and reply.resources is not None

    def test_msr(self):
        reply = parse_response("msr", {"rei": REI})
        assert isinstance(reply, SkipResearchResponse)
        assert reply.research is not None and reply.research.bought_research_ids[-1] == 171


class TestService:
    def test_start_research_sends_res_and_its_reply_reaches_the_state(self):
        client = make_client({"res": xt_packet("res", {"rei": REI, "gcu": {}})}, state=GameState())  # type: ignore[arg-type]
        conn(client).on_packet = client._on_packet

        assert client.player.start_research(Research.MANEUVER_L1) is True

        assert conn(client).request_payloads == [("res", {"RID": 1, "PO": -1, "PWR": 0})]
        research = client.state.get_research()
        assert research is not None and research.current_research_id == 172

    def test_skip_research_sends_msr_and_its_reply_reaches_the_state(self):
        client = make_client({"msr": xt_packet("msr", {"rei": REI})}, state=GameState())  # type: ignore[arg-type]
        conn(client).on_packet = client._on_packet

        assert client.player.skip_research(Currency.SKIP_10_MINUTES) is True

        assert conn(client).request_payloads == [("msr", {"MST": "MS3"})]
        research = client.state.get_research()
        assert research is not None and research.research_seconds == 300

    def test_a_skip_newer_than_the_enum_goes_out_by_its_key(self):
        client = make_client()
        assert client.player.skip_research("MS99") is True
        assert conn(client).request_payloads == [("msr", {"MST": "MS99"})]

    def test_a_refused_start_is_false_and_leaves_the_state(self):
        client = make_client({"res": xt_packet("res", error_code=21)}, state=GameState())  # type: ignore[arg-type]
        conn(client).on_packet = client._on_packet

        assert client.player.start_research(Research.MANEUVER_L1) is False
        assert client.state.get_research() is None
