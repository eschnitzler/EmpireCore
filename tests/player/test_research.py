"""Starting research and shortening it with a minute skip: res and msr."""

from __future__ import annotations

import pytest

from empire_core.enums import CollectableKind
from empire_core.exceptions import GameDataNotLoadedError
from empire_core.gamedata import Currency, GameData, Research
from empire_core.gamedata import data as data_module
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

# rows as items 786.03 has them: MANEUVER_L1 costs coins and resources, MARCHING_FORMATION_L4 rubies,
# and 799 legendary tokens
ITEMS = {
    "currencies": [{"currencyID": "28", "Name": "LegendaryToken", "JSONKey": "LT"}],
    "researches": [
        {"researchID": "1", "groupID": "1", "level": "1", "costC1": "120", "costWood": "50", "costStone": "50"},
        {
            "researchID": "184",
            "groupID": "22",
            "level": "4",
            "costC2": "3500",
            "globalServerCostWood": "7627",
            "globalServerCostStone": "7627",
        },
        {"researchID": "799", "groupID": "199", "level": "1", "costLegendaryToken": "15", "costC1": "1000"},
    ],
}


def game_data() -> GameData:
    return GameData.parse("test", ITEMS)


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


class TestCosts:
    def test_every_cost_column_is_read(self):
        # AResearchVO.fillFromParamXML: x2cList over the cost and globalServerCost columns
        researches = game_data().researches
        maneuver = researches[Research.MANEUVER_L1]
        assert [(cost.kind, cost.amount) for cost in maneuver.costs] == [
            (CollectableKind.COINS, 120),
            (CollectableKind.WOOD, 50),
            (CollectableKind.STONE, 50),
        ]
        assert maneuver.cost_rubies == 0
        marching = researches[Research.MARCHING_FORMATION_L4]
        assert marching.cost_rubies == 3500
        assert [(cost.kind, cost.amount) for cost in marching.costs] == [(CollectableKind.RUBIES, 3500)]
        assert [cost.kind for cost in marching.temp_server_costs] == [CollectableKind.WOOD, CollectableKind.STONE]

    def test_a_currency_cost_is_read_by_its_name(self):
        (token, _) = game_data().researches[799].costs
        assert token.item is Currency.CONSTRUCTION_TOKEN and token.amount == 15


class TestService:
    def test_start_research_sends_res_and_its_reply_reaches_the_state(self):
        client = make_client({"res": xt_packet("res", {"rei": REI, "gcu": {}})}, state=GameState())  # type: ignore[arg-type]
        conn(client).on_packet = client._on_packet
        client.game_data = game_data()

        assert client.player.start_research(Research.MANEUVER_L1) is True

        assert conn(client).request_payloads == [("res", {"RID": 1, "PO": -1, "PWR": 0})]
        research = client.state.get_research()
        assert research is not None and research.current_research_id == 172

    def test_start_research_reads_game_data_the_process_loaded(self, monkeypatch: pytest.MonkeyPatch):
        """A GameData.load() made without the client reaches its services too."""
        client = make_client({"res": xt_packet("res", {"rei": REI, "gcu": {}})}, state=GameState())  # type: ignore[arg-type]
        conn(client).on_packet = client._on_packet
        monkeypatch.setattr(data_module, "_loaded", game_data())

        assert client.player.start_research(Research.MANEUVER_L1) is True
        assert conn(client).request_payloads == [("res", {"RID": 1, "PO": -1, "PWR": 0})]

    def test_start_research_needs_the_game_data(self):
        client = make_client()
        with pytest.raises(GameDataNotLoadedError):
            client.player.start_research(Research.MANEUVER_L1)
        assert conn(client).request_payloads == []

    def test_a_research_the_game_data_lacks_is_refused(self):
        client = make_client()
        client.game_data = game_data()
        with pytest.raises(ValueError, match="no research"):
            client.player.start_research(Research.MANEUVER_L2)
        assert conn(client).request_payloads == []

    def test_a_research_that_costs_rubies_is_refused(self):
        # ResearchInfo.buyResearch sends the same res for it, and the server takes the rubies
        client = make_client()
        client.game_data = game_data()
        with pytest.raises(ValueError, match="3500 rubies"):
            client.player.start_research(Research.MARCHING_FORMATION_L4)
        assert conn(client).request_payloads == []

    def test_a_research_that_costs_rubies_starts_when_asked_to_spend_them(self):
        client = make_client()
        client.game_data = game_data()
        assert client.player.start_research(Research.MARCHING_FORMATION_L4, spend_rubies=True) is True
        assert conn(client).request_payloads == [("res", {"RID": 184, "PO": -1, "PWR": 0})]

    def test_a_research_that_costs_legendary_tokens_starts(self):
        client = make_client()
        client.game_data = game_data()
        assert client.player.start_research(799) is True
        assert conn(client).request_payloads == [("res", {"RID": 799, "PO": -1, "PWR": 0})]

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

    def test_a_currency_that_is_no_minute_skip_is_refused(self):
        client = make_client()
        with pytest.raises(ValueError, match="no minute skip"):
            client.player.skip_research(Currency.CONSTRUCTION_TOKEN)
        with pytest.raises(ValueError, match="no minute skip"):
            client.player.skip_research("LT")
        assert conn(client).request_payloads == []

    def test_a_minute_skip_you_hold_none_of_is_refused(self):
        # CastleMinuteSkipDialog.showLoaded lists only the skips with an amount above 0
        state = GameState()
        state.update_from_packet("gbd", {"gpi": {"PID": 1, "PN": "me"}})
        state.update_from_packet("sce", [["MS1", 0], ["MS3", 2]])  # type: ignore[arg-type]
        client = make_client({"msr": xt_packet("msr", {"rei": REI})}, state=state)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="SKIP_1_MINUTE"):
            client.player.skip_research(Currency.SKIP_1_MINUTE)
        assert conn(client).request_payloads == []
        assert client.player.skip_research(Currency.SKIP_10_MINUTES) is True

    def test_a_refused_start_is_false_and_leaves_the_state(self):
        client = make_client({"res": xt_packet("res", error_code=21)}, state=GameState())  # type: ignore[arg-type]
        conn(client).on_packet = client._on_packet
        client.game_data = game_data()

        assert client.player.start_research(Research.MANEUVER_L1) is False
        assert client.state.get_research() is None
