"""Tests for the events service."""

from __future__ import annotations

from empire_core.events import service as events_module
from empire_core.state.manager import GameState
from tests.service_helpers import make_client, xt_packet


def _client(state: GameState | None = None):
    return make_client(state=state or GameState())  # type: ignore[arg-type]


class TestEventLeagues:
    def test_the_league_comes_from_the_sei_entries(self):
        client = _client()

        client._on_packet(xt_packet("sei", {"E": [{"EID": 83, "RS": 60, "LID": 3, "OP": [0]}, {"EID": 7, "RS": 60}]}))

        # A running event without a league is in league 1, the client's default; one not running has none
        leagues = [client.events.get_league_id(event) for event in (83, 7, 60)]
        assert leagues == [3, 1, None]

    def test_a_later_entry_without_a_league_keeps_it(self):
        # AScoreEventVO: t.LID&&(this._leagueID=int(t.LID))
        client = _client()
        client._on_packet(xt_packet("sei", {"E": [{"EID": 83, "RS": 60, "LID": 3}]}))

        client._on_packet(xt_packet("sei", {"E": [{"EID": 83, "RS": 60, "LID": 0}, {"EID": 60, "RS": 60, "LID": "7"}]}))

        assert (client.events.get_league_id(83), client.events.get_league_id(60)) == (3, 7)

    def test_the_login_data_carries_them_too(self):
        client = _client()

        client._on_packet(xt_packet("gbd", {"sei": {"E": [{"EID": 83, "RS": 60, "LID": 2}]}}))

        assert client.events.get_league_id(83) == 2

    def test_a_reset_forgets_them(self):
        state = GameState()
        client = _client(state)
        client._on_packet(xt_packet("sei", {"E": [{"EID": 83, "RS": 60, "LID": 3}]}))

        state.reset()

        assert client.events.get_league_id(83) is None


class TestActiveEvents:
    def test_ids_are_the_running_events_in_order_and_a_copy(self):
        client = _client()
        client._on_packet(xt_packet("sei", {"E": [{"EID": 11, "RS": 60}, {"EID": 10, "RS": 60}]}))

        ids = client.events.get_active_event_ids()
        ids.append(99)

        assert client.events.get_active_event_ids() == [11, 10]

    def test_events_resolve_the_state_ids(self, monkeypatch):
        calls = []

        def fake_get_active_events(event_ids, lang="en", force_refresh=False):
            calls.append((event_ids, lang, force_refresh))
            return []

        monkeypatch.setattr(events_module, "_get_active_events", fake_get_active_events)
        client = _client()
        client._on_packet(xt_packet("sei", {"E": [{"EID": 10, "RS": 60}]}))

        assert client.events.get_active_events(lang="de", force_refresh=True) == []
        assert calls == [([10], "de", True)]


class TestRefusedReplies:
    def test_a_refused_event_reply_is_not_applied(self):
        # SEICommand, PEPCommand, FJFCommand, ... parse only on ALL_OK
        client = _client()
        client._on_packet(xt_packet("sei", {"E": [{"EID": 60, "RS": 60}]}))

        client._on_packet(xt_packet("sei", {"E": [{"EID": 83, "RS": 60}]}, error_code=1))
        client._on_packet(xt_packet("pep", {"EID": 60, "OR": [1], "OP": [5]}, error_code=1))
        client._on_packet(xt_packet("see", {"EID": 60}, error_code=1))
        client._on_packet(xt_packet("fjf", {"sei": {"E": [{"EID": 3, "RS": 60}]}}, error_code=1))

        assert client.events.get_active_event_ids() == [60]
        assert client.state.get_event(60).own_points == 0  # type: ignore[union-attr]


class TestEventUpdates:
    def test_a_later_sei_updates_and_adds_but_ends_nothing(self):
        # CastleSpecialEventData.parseServerEventData: an entry updates its event or adds it
        client = _client()
        client._on_packet(xt_packet("sei", {"E": [{"EID": 3, "RS": 60}, {"EID": 83, "RS": 60}]}))

        client._on_packet(xt_packet("sei", {"E": [{"EID": 83, "RS": 60}, {"EID": 60, "RS": 60}]}))

        assert client.events.get_active_event_ids() == [3, 83, 60]

    def test_a_see_ends_its_event(self):
        client = _client()
        client._on_packet(xt_packet("sei", {"E": [{"EID": 3, "RS": 60}, {"EID": 83, "RS": 60}]}))

        client._on_packet(xt_packet("see", {"EID": 3}))
        client._on_packet(xt_packet("see", {"EID": 999}))

        assert client.events.get_active_event_ids() == [83]

    def test_berimond_invasion_rebuilds_every_part_at_league_one(self):
        # FactionInvasionEventVO.parseData builds FB, FR and A anew from every entry
        client = _client()
        first = {"EID": 85, "RS": 60, "FB": {"LID": 2}, "FR": {"LID": "3"}, "A": {}}
        client._on_packet(xt_packet("sei", {"E": [first]}))
        parts = (None, "FB", "FR", "A", "SP")
        before = [client.events.get_league_id(85, part) for part in parts]

        client._on_packet(xt_packet("sei", {"E": [{"EID": 85, "RS": 60, "FB": {"LID": 0}, "SP": "x"}]}))

        # SP is not one of its parts, so it reads as the default league
        assert before == [1, 2, 3, 1, 1]
        assert [client.events.get_league_id(85, part) for part in parts] == [1, 1, 1, 1, 1]
