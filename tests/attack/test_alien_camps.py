"""Alien camps: rae, hac and rce."""

from __future__ import annotations

import pytest

from empire_core.attack import AlienRerollCountsResponse, HiddenAlienCampsResponse
from empire_core.enums import CollectableKind
from empire_core.exceptions import CommandError
from empire_core.gamedata import Currency
from empire_core.protocol.base import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

ALIEN_ENTRY = {"EID": 71, "RS": 600, "CRE": 1, "RCKS": ["C1", "DC2"], "RCSC": 2, "RCHC": 1}


def alien_state() -> GameState:
    state = logged_in_state()
    state.update_from_packet("sei", {"E": [ALIEN_ENTRY]})
    return state


class TestReroll:
    def test_rubies_need_consent(self):
        client = make_client()
        with pytest.raises(ValueError, match="rubies"):
            client.attack.reroll_alien_camp(10, 20)
        client.attack.reroll_alien_camp(10, 20, spend_rubies=True)
        assert conn(client).request_payloads == [("rae", {"XPOS": 10, "YPOS": 20, "RCK": "C2"})]
        assert list(conn(client).request_payloads[0][1]) == ["XPOS", "YPOS", "RCK"]

    def test_an_event_currency(self):
        state = alien_state()
        client = make_client(state=state)

        client.attack.reroll_alien_camp(10, 20, currency=CollectableKind.COINS)
        client.attack.reroll_alien_camp(10, 20, currency=Currency.DC2)

        assert conn(client).request_payloads == [
            ("rae", {"XPOS": 10, "YPOS": 20, "RCK": "C1"}),
            ("rae", {"XPOS": 10, "YPOS": 20, "RCK": "DC2"}),
        ]
        state.shutdown()

    def test_a_currency_no_invasion_takes(self):
        state = alien_state()
        client = make_client(state=state)
        with pytest.raises(ValueError, match="C1"):
            make_client(state=logged_in_state()).attack.reroll_alien_camp(1, 2, currency=CollectableKind.COINS)
        with pytest.raises(ValueError, match="W"):
            client.attack.reroll_alien_camp(1, 2, currency=CollectableKind.WOOD)
        state.shutdown()

    def test_a_refusal_raises(self):
        client = make_client({"rae": xt_packet("rae", error_code=1)})
        with pytest.raises(CommandError):
            client.attack.reroll_alien_camp(1, 2, spend_rubies=True)


class TestHiddenCamps:
    def test_the_push_reaches_the_callbacks(self):
        client = make_client()
        seen: list[HiddenAlienCampsResponse] = []
        client.attack.on_alien_camps_hidden(seen.append)

        client._on_packet(xt_packet("hac", {"CP": [[10, 20], [30, 40]]}))

        assert [push.positions for push in seen] == [((10, 20), (30, 40))]


class TestRerollCounts:
    def test_the_push(self):
        push = parse_response("rce", {"RCSC": 3, "RCHC": "4"})
        assert isinstance(push, AlienRerollCountsResponse)
        assert (push.soft_rerolls, push.ruby_rerolls) == (3, 4)

    def test_an_alien_invasion_entry_brings_them(self):
        state = alien_state()
        client = make_client(state=state)

        counts = client.attack.alien_reroll_counts

        assert counts is not None and (counts.soft_rerolls, counts.ruby_rerolls) == (2, 1)
        state.shutdown()

    def test_a_push_keeps_a_count_it_leaves_out(self):
        state = alien_state()

        state.update_from_packet("rce", {"RCHC": 5})

        counts = state.get_alien_reroll_counts()
        assert counts is not None and (counts.soft_rerolls, counts.ruby_rerolls) == (2, 5)
        state.shutdown()

    def test_none_before_the_server_sent_them(self):
        state = logged_in_state()
        assert make_client(state=state).attack.alien_reroll_counts is None
        state.shutdown()

    def test_an_entry_without_counts_brings_none(self):
        state = logged_in_state()
        state.update_from_packet("sei", {"E": [{"EID": 71, "RS": 600}]})
        assert state.get_alien_reroll_counts() is None
        state.shutdown()
