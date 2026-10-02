"""Tests for the events service."""

from __future__ import annotations

from empire_core.events import service as events_module
from empire_core.events.models import PointEvent, SpecialEventInfoRequest
from empire_core.gamedata.ids.events import Event
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet


def _client(state: GameState | None = None):
    return make_client(state=state or GameState())  # ty: ignore[invalid-argument-type]


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

    def test_active_events_carry_their_titles(self, monkeypatch):
        monkeypatch.setattr(events_module, "get_event_titles", lambda lang="en", force_refresh=False: {72: lang})
        client = _client()
        client._on_packet(
            xt_packet("sei", {"E": [{"EID": 72, "RS": 60}, {"EID": 60, "RS": 60}, {"EID": 999, "RS": 60}]})
        )

        events = client.events.get_active_events(lang="de")

        assert [(e.event_id, e.event, e.display_name) for e in events] == [
            (72, Event.ALLIANCE_NOMAD_INVASION, "de"),
            (60, Event.POINT_EVENT, "POINT_EVENT"),
            (999, None, "999"),
        ]
        assert events[0].details is client.state.get_event(72)

    def test_a_dumped_event_keeps_its_own_fields(self, monkeypatch):
        monkeypatch.setattr(events_module, "get_event_titles", lambda lang="en", force_refresh=False: {})
        client = _client()
        client._on_packet(xt_packet("sei", {"E": [{"EID": 60, "RS": 60, "LID": 4, "PET": 15}]}))

        dumped = client.events.get_active_events()[0].model_dump()

        assert (dumped["details"]["league_id"], dumped["details"]["point_event_type"]) == (4, 15)

    def test_no_running_event_asks_for_no_titles(self, monkeypatch):
        def no_titles(lang="en", force_refresh=False):
            raise AssertionError("fetched titles")

        monkeypatch.setattr(events_module, "get_event_titles", no_titles)

        assert _client().events.get_active_events() == []


class TestRefresh:
    def test_the_request_has_no_fields(self):
        # C2SSpecialEventInfoVO has no fields
        assert SpecialEventInfoRequest().to_payload() == {}
        assert SpecialEventInfoRequest.get_response_command() == "sei"

    def test_refresh_sends_sei_and_returns_the_events_it_brings(self):
        reply = xt_packet("sei", {"E": [{"EID": 60, "RS": 60, "LID": 4}]})
        client = make_client({"sei": reply}, state=GameState())  # ty: ignore[invalid-argument-type]
        conn(client).on_packet = client._on_packet

        events = client.events.refresh()

        assert conn(client).request_payloads == [("sei", {})]
        point = events[60]
        assert isinstance(point, PointEvent) and point.league_id == 4


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
        assert client.state.get_event(60).own_points == 0


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
