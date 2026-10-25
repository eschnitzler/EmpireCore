"""The hunter (hin) and the citizen judgements (sjc, jjc)."""

from __future__ import annotations

import pytest

from empire_core.castle import HunterInfo, JudgementStarted
from empire_core.enums import JudgementOption
from empire_core.exceptions import CommandError
from empire_core.protocol.base import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet


class TestHunter:
    def test_set_sends_the_boost_and_returns_the_values(self):
        client = make_client({"hin": xt_packet("hin", {"FB": 20, "WSR": 40})})

        hunter = client.castle.set_hunter(20)

        assert conn(client).request_payloads == [("hin", {"FB": 20})]
        assert (hunter.food_boost, hunter.wood_stone_reduction, hunter.is_boosted) == (20, 40, True)

    def test_no_boost(self):
        hunter = parse_response("hin", {"FB": 0, "WSR": 0})
        assert isinstance(hunter, HunterInfo) and not hunter.is_boosted

    def test_a_refusal_raises(self):
        client = make_client({"hin": xt_packet("hin", None, error_code=1)})
        with pytest.raises(CommandError):
            client.castle.set_hunter(500)

    def test_the_state_keeps_a_hin(self):
        state = GameState()
        state.update_from_packet("hin", {"FB": 10, "WSR": 20})
        hunter = state.get_hunter()
        assert hunter is not None and hunter.food_boost == 10

    def test_an_error_hin_is_not_kept(self):
        state = GameState()
        state.update_from_packet("hin", {"FB": 10, "WSR": 20}, error_code=1)
        assert state.get_hunter() is None

    def test_a_join_carries_the_hunter(self):
        # JAACommand.executeCommand: i.hin&&hunterData.parse_HIN(i.hin)
        state = GameState()
        state.update_from_packet("jaa", {"KID": 0, "hin": {"FB": 5, "WSR": 10}})
        hunter = state.get_hunter()
        assert hunter is not None and hunter.wood_stone_reduction == 10


class TestJudgement:
    def test_a_started_judgement_is_kept(self):
        state = GameState()
        state.update_from_packet("sjc", {"JID": 14})
        assert state.get_judgement_id() == 14
        assert isinstance(parse_response("sjc", {"JID": 14}), JudgementStarted)

    def test_the_verdict_ends_it(self):
        state = GameState()
        state.update_from_packet("sjc", {"JID": 14})
        state.update_from_packet("jjc", {"CO": 1})
        assert state.get_judgement_id() is None

    def test_a_refused_verdict_keeps_it(self):
        state = GameState()
        state.update_from_packet("sjc", {"JID": 14})
        state.update_from_packet("jjc", {}, error_code=1)
        assert state.get_judgement_id() == 14

    @pytest.mark.parametrize("option", list(JudgementOption))
    def test_judge_sends_the_option(self, option):
        client = make_client({"jjc": xt_packet("jjc", {"CO": int(option)})})
        client.castle.judge_citizen(option)
        assert conn(client).request_payloads == [("jjc", {"CO": int(option)})]

    def test_a_refusal_raises(self):
        client = make_client({"jjc": xt_packet("jjc", None, error_code=1)})
        with pytest.raises(CommandError):
            client.castle.judge_citizen(JudgementOption.A)
