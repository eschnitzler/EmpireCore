"""The officers' school's training programs (gtp, atp, ptp, rtp) and the hero pick (hdc)."""

from __future__ import annotations

import pytest

from empire_core.enums import Hero
from empire_core.exceptions import CommandError
from empire_core.gamedata import CurrencyId
from empire_core.player import (
    HeroDecisionResponse,
    OfficerBonus,
    RerollTrainingProgramsRequest,
    TrainingProgramsResponse,
)
from empire_core.protocol.base import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet

# Shaped as OfficersSchoolData.parse_GTP reads a gtp
GTP = {
    "AT": {"TE": 12, "S": 3, "D": 86400, "E": [811, [7]]},
    "TP": [
        {"TE": 4, "S": 1, "D": 43200, "E": [810, [5]]},
        {"TE": 9, "S": 2, "D": 43200, "E": [812, [3, 1]]},
        {"TE": 12, "S": 3, "D": 86400, "E": [811, [7]]},
    ],
    "PC": 1,
    "RCSC": 2,
    "RCHC": 0,
    "CT": 7,
}


class TestTrainingPrograms:
    def test_the_programs_are_read(self):
        programs = parse_response("gtp", GTP)

        assert isinstance(programs, TrainingProgramsResponse)
        assert programs.running is not None
        assert (programs.running.program_id, programs.running.slot_id, programs.running.duration_seconds) == (
            12,
            3,
            86400,
        )
        assert [program.slot_id for program in programs.offered] == [1, 2, 3]
        assert programs.offered[1].bonus == OfficerBonus(effect=812, values=(3, 1))
        assert (programs.prolong_count, programs.event_currency_rerolls, programs.ruby_rerolls) == (1, 2, 0)
        assert programs.event_currency is CurrencyId.SAMURAI_TOKENS

    def test_no_running_program_is_none(self):
        programs = parse_response("gtp", {"AT": None, "TP": []})
        assert isinstance(programs, TrainingProgramsResponse)
        assert programs.running is None and programs.offered == ()

    def test_get_sends_an_empty_gtp(self):
        client = make_client({"gtp": xt_packet("gtp", GTP)})

        programs = client.player.get_training_programs()

        assert conn(client).request_payloads == [("gtp", {})]
        assert programs.ruby_rerolls == 0

    def test_the_state_keeps_the_last_gtp(self):
        state = GameState()
        state.update_from_packet("gtp", GTP)
        programs = state.get_training_programs()
        assert programs is not None and len(programs.offered) == 3

    def test_an_error_gtp_is_not_kept(self):
        state = GameState()
        state.update_from_packet("gtp", GTP, error_code=1)
        assert state.get_training_programs() is None


class TestActivate:
    @pytest.mark.parametrize("slot_id", [1, 2])
    def test_coin_and_event_currency_slots_need_no_consent(self, slot_id):
        client = make_client()
        client.player.activate_training_program(slot_id)
        assert conn(client).request_payloads == [("atp", {"S": slot_id})]

    def test_the_ruby_slot_needs_consent(self):
        client = make_client()
        with pytest.raises(ValueError, match="spend_rubies"):
            client.player.activate_training_program(3)
        assert conn(client).request_payloads == []

        client.player.activate_training_program(3, spend_rubies=True)
        assert conn(client).request_payloads == [("atp", {"S": 3})]

    def test_a_refusal_raises(self):
        client = make_client({"atp": xt_packet("atp", None, error_code=1)})
        with pytest.raises(CommandError):
            client.player.activate_training_program(1)


class TestProlong:
    def test_needs_consent(self):
        client = make_client()
        with pytest.raises(ValueError, match="spend_rubies"):
            client.player.prolong_training_program()
        assert conn(client).request_payloads == []

    def test_sends_an_empty_ptp(self):
        client = make_client()
        client.player.prolong_training_program(spend_rubies=True)
        assert conn(client).request_payloads == [("ptp", {})]


class TestReroll:
    def test_keys(self):
        request = RerollTrainingProgramsRequest(premium=True, kept_slot_ids=[2])
        assert request.to_payload() == {"P": 1, "LS": [2]}

    def test_the_event_currency_reroll_needs_no_consent(self):
        client = make_client()
        client.player.reroll_training_programs([1, 3])
        assert conn(client).request_payloads == [("rtp", {"P": 0, "LS": [1, 3]})]

    def test_the_premium_reroll_needs_consent(self):
        client = make_client()
        with pytest.raises(ValueError, match="spend_rubies"):
            client.player.reroll_training_programs(premium=True)
        assert conn(client).request_payloads == []

    def test_consent_alone_sends_no_premium_reroll(self):
        client = make_client()
        client.player.reroll_training_programs(spend_rubies=True)
        assert conn(client).request_payloads == [("rtp", {"P": 0, "LS": []})]

    def test_the_premium_reroll_with_consent(self):
        client = make_client()
        client.player.reroll_training_programs(premium=True, spend_rubies=True)
        assert conn(client).request_payloads == [("rtp", {"P": 1, "LS": []})]


class TestHero:
    def test_choose_sends_the_hero_id(self):
        client = make_client({"hdc": xt_packet("hdc", {"HID": 803})})

        reply = client.player.choose_hero(Hero.FEMALE_WARRIOR)

        assert conn(client).request_payloads == [("hdc", {"HID": 803})]
        assert reply.hero is Hero.FEMALE_WARRIOR

    def test_minus_one_means_none_is_picked(self):
        reply = parse_response("hdc", {"HID": -1})
        assert isinstance(reply, HeroDecisionResponse)
        assert reply.hero is None

    def test_the_state_keeps_the_hero(self):
        state = GameState()
        state.update_from_packet("hdc", {"HID": 802})
        assert state.get_hero() is Hero.OLD_KNIGHT

    def test_a_refusal_raises(self):
        client = make_client({"hdc": xt_packet("hdc", None, error_code=1)})
        with pytest.raises(CommandError):
            client.player.choose_hero(Hero.YOUNG_KNIGHT)


def test_the_player_service_reads_the_hero():
    state = GameState()
    client = make_client(state=state)  # type: ignore[arg-type]
    assert client.player.hero is None
    state.update_from_packet("hdc", {"HID": -1})
    assert client.player.hero is None
    state.update_from_packet("hdc", {"HID": 801})
    assert client.player.hero is Hero.YOUNG_KNIGHT
