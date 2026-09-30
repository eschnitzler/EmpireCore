"""Tests for the events service."""

from __future__ import annotations

from empire_core.events import service as events_module
from empire_core.state.manager import GameState
from tests.service_helpers import StubState, make_client, xt_packet


def _client(state: GameState | None = None):
    return make_client(state=state or GameState())  # type: ignore[arg-type]


class TestEventLeagues:
    def test_the_league_comes_from_the_sei_entries(self):
        client = _client()

        client._on_packet(xt_packet("sei", {"E": [{"EID": 83, "LID": 3, "OP": [0]}, {"EID": 7}]}))

        assert (client.events.get_league_id(83), client.events.get_league_id(7)) == (3, None)

    def test_a_later_entry_without_a_league_keeps_it(self):
        # AScoreEventVO: t.LID&&(this._leagueID=int(t.LID))
        client = _client()
        client._on_packet(xt_packet("sei", {"E": [{"EID": 83, "LID": 3}]}))

        client._on_packet(xt_packet("sei", {"E": [{"EID": 83, "LID": 0}, {"EID": 60, "LID": "7"}]}))

        assert (client.events.get_league_id(83), client.events.get_league_id(60)) == (3, 7)

    def test_the_login_data_carries_them_too(self):
        client = _client()

        client._on_packet(xt_packet("gbd", {"sei": {"E": [{"EID": 83, "LID": 2}]}}))

        assert client.events.get_league_id(83) == 2

    def test_a_reset_forgets_them(self):
        state = GameState()
        client = _client(state)
        client._on_packet(xt_packet("sei", {"E": [{"EID": 83, "LID": 3}]}))

        state.reset()

        assert client.events.get_league_id(83) is None


class TestActiveEvents:
    def test_ids_are_a_copy_of_the_state_list(self):
        state = StubState()
        state.active_event_ids = [10, 11]  # type: ignore[attr-defined]
        client = make_client(state=state)

        ids = client.events.get_active_event_ids()
        ids.append(99)

        assert client.events.get_active_event_ids() == [10, 11]

    def test_events_resolve_the_state_ids(self, monkeypatch):
        calls = []

        def fake_get_active_events(event_ids, lang="en", force_refresh=False):
            calls.append((event_ids, lang, force_refresh))
            return []

        monkeypatch.setattr(events_module, "_get_active_events", fake_get_active_events)
        state = StubState()
        state.active_event_ids = [10]  # type: ignore[attr-defined]
        client = make_client(state=state)

        assert client.events.get_active_events(lang="de", force_refresh=True) == []
        assert calls == [([10], "de", True)]
