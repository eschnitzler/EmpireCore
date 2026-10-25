"""Taunts: lta, lwta and the rpr rage push."""

from __future__ import annotations

import pytest

from empire_core.attack import RagePointsResponse
from empire_core.events.models import NomadInvasionEvent
from empire_core.exceptions import CommandError
from empire_core.gamedata.ids.events import Event
from empire_core.protocol.base import parse_response
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

NOMAD_ENTRY = {"EID": 72, "RS": 600, "ACE": 1, "AC": {"AR": 5, "PCRP": 1, "PTRP": 2, "ACID": 9}}


class TestKhanTaunt:
    @pytest.mark.parametrize(("share", "flag"), [(False, 0), (True, 1)])
    def test_sends_the_alliance_flag_and_the_event(self, share, flag):
        client = make_client()

        client.attack.taunt_nomad_khan(share_with_alliance=share)

        assert conn(client).request_payloads == [("lta", {"AV": flag, "EID": 72})]

    def test_a_refusal_raises(self):
        client = make_client({"lta": xt_packet("lta", error_code=1)})
        with pytest.raises(CommandError):
            client.attack.taunt_nomad_khan()


class TestWolfKingTaunt:
    def test_sends_nothing_else(self):
        client = make_client()
        client.attack.taunt_wolf_king()
        assert conn(client).request_payloads == [("lwta", {})]

    def test_a_refusal_raises(self):
        client = make_client({"lwta": xt_packet("lwta", error_code=1)})
        with pytest.raises(CommandError):
            client.attack.taunt_wolf_king()


class TestRagePoints:
    def test_the_push(self):
        push = parse_response("rpr", {"EID": 72, "PCRP": 40, "PTRP": "90"})
        assert isinstance(push, RagePointsResponse)
        assert (push.event_id, push.player_rage, push.player_total_rage) == (72, 40, 90)

    def test_updates_the_nomad_invasion(self):
        state = logged_in_state()
        state.update_from_packet("sei", {"E": [NOMAD_ENTRY]})

        state.update_from_packet("rpr", {"EID": 72, "PCRP": 40, "PTRP": 90})

        event = state.get_event(Event.ALLIANCE_NOMAD_INVASION)
        assert isinstance(event, NomadInvasionEvent)
        assert (event.player_rage, event.player_total_rage, event.alliance_rage) == (40, 90, 5)
        state.shutdown()

    def test_another_event_is_left_alone(self):
        state = logged_in_state()
        state.update_from_packet("sei", {"E": [NOMAD_ENTRY]})

        state.update_from_packet("rpr", {"EID": 71, "PCRP": 40, "PTRP": 90})
        state.update_from_packet("rpr", {"EID": 72, "PCRP": 40, "PTRP": 90}, error_code=1)

        event = state.get_event(Event.ALLIANCE_NOMAD_INVASION)
        assert isinstance(event, NomadInvasionEvent) and event.player_rage == 1
        state.shutdown()
