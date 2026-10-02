"""Tests for client.events.get_scores and the scoreboard lookup."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.enums import RankingType
from empire_core.events import EVENT_SCOREBOARDS, EventScore, EventScores
from empire_core.exceptions import CommandError, EventNotRunningError, ReplyMismatchError
from empire_core.gamedata.ids import Event
from empire_core.state import events as event_state
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet


def _running(script: dict[str, Any] | None = None, *entries: dict[str, Any]):
    # Every entry runs for an hour, and Berimond is unlocked, unless the test says otherwise
    client = make_client(script, state=GameState())  # ty: ignore[invalid-argument-type]
    client._on_packet(xt_packet("sei", {"E": [{"RS": 3600, "UL": 1, **entry} for entry in entries]}))
    return client


def _owner(oid: int, name: str, aid: int = 0, alliance: str = "") -> dict[str, Any]:
    return {"OID": oid, "N": name, "L": 70, "AID": aid, "AN": alliance}


class TestScoreboards:
    def test_the_boards_are_the_dialogs_lists(self):
        assert EVENT_SCOREBOARDS[Event.FACTION].player_lists == (RankingType.FACTION_TOURNAMENT,)
        alien = EVENT_SCOREBOARDS[Event.ALLIANCE_ALIEN_INVASION]
        assert alien.alliance_list is RankingType.ALLIANCE_ALIEN_INVASION_ALLIANCE
        assert EVENT_SCOREBOARDS[Event.ALLIANCE_NOMAD_INVASION].player_lists == ()
        assert EVENT_SCOREBOARDS[Event.FACTION_INVASION].lists == (
            RankingType.FACTION_INVASION_PLAYER_BLUE,
            RankingType.FACTION_INVASION_PLAYER_RED,
            RankingType.FACTION_INVASION_ALLIANCE,
        )

    def test_only_the_long_term_point_and_donation_events_are_leaderboards(self):
        leaderboards = {e for e, board in EVENT_SCOREBOARDS.items() if board.is_leaderboard}
        assert leaderboards == {Event.LONG_TERM_POINT_EVENT, Event.DONATION_EVENT}

    def test_every_event_has_a_board_and_a_source(self):
        assert all(board.lists and board.source for board in EVENT_SCOREBOARDS.values())

    def test_the_keys_are_the_client_event_ids(self):
        ids = {int(e) for e in EVENT_SCOREBOARDS}
        assert ids == {3, 60, 62, 71, 72, 80, 83, 85, 103, 123}

    def test_the_accessor(self):
        client = make_client()

        assert client.events.scoreboard(Event.SAMURAI_INVASION).alliance_list is RankingType.SAMURAI_ALLIANCE
        with pytest.raises(ValueError, match="no scoreboard; these do: Event.FACTION, "):
            client.events.scoreboard(Event.LUCKY_WHEEL)

    def test_the_lookup_loads_only_the_event_ids(self):
        import subprocess
        import sys

        code = (
            "import sys, empire_core.events as e\n"
            "assert e.EVENT_SCOREBOARDS\n"
            "assert 'empire_core.gamedata.ids.events' in sys.modules\n"
            "assert 'empire_core.gamedata.ids.units' not in sys.modules\n"
        )
        subprocess.run([sys.executable, "-c", code], check=True)


class TestHighscoreBoards:
    def test_your_own_page_in_your_league_by_default(self):
        reply = {"LT": 30, "LID": 2, "LR": 640, "L": [[11, 900, _owner(5, "Someone", 3, "Allies")]]}
        client = _running({"hgh": xt_packet("hgh", reply)}, {"EID": 3, "LID": 2})

        scores = client.events.get_scores(Event.FACTION)

        assert conn(client).request_payloads == [("hgh", {"LT": 30, "LID": 2, "SV": "-1"})]
        assert (scores.event, scores.list_type, scores.league_id, scores.total) == (
            Event.FACTION,
            RankingType.FACTION_TOURNAMENT,
            2,
            640,
        )
        assert scores.scores == [
            EventScore(
                rank=11, points=900, name="Someone", player_id=5, alliance_id=3, alliance_name="Allies", level=70
            )
        ]

    def test_the_top_and_a_name(self):
        client = _running({"hgh": [xt_packet("hgh", {"L": []}), xt_packet("hgh", {"L": []})]}, {"EID": 60, "LID": 4})

        client.events.get_scores(Event.POINT_EVENT, rank=1)
        client.events.get_scores(Event.POINT_EVENT, name="Someone")

        assert conn(client).request_payloads == [
            ("hgh", {"LT": 40, "LID": 4, "SV": "1"}),
            ("hgh", {"LT": 40, "LID": 4, "SV": "Someone"}),
        ]

    def test_league_one_when_the_sei_gave_none(self):
        # AScoreEventVO starts at _leagueID=1
        client = _running({"hgh": xt_packet("hgh", {"L": []})}, {"EID": 62})

        client.events.get_scores(Event.BEGGING_KNIGHTS)

        assert conn(client).request_payloads == [("hgh", {"LT": 41, "LID": 1, "SV": "-1"})]

    def test_another_league(self):
        client = _running({"hgh": xt_packet("hgh", {"L": []})}, {"EID": 3, "LID": 2})

        client.events.get_scores(Event.FACTION, league_id=4, rank=1)

        assert conn(client).request_payloads == [("hgh", {"LT": 30, "LID": 4, "SV": "1"})]

    def test_an_invasion_board_takes_its_league_from_its_part(self):
        # AAlienInvasionEventVO.parseData: the player board from SP, the alliance board from A
        entry = {"EID": 71, "LID": 9, "SP": {"LID": 3}, "A": {"LID": 5}}
        client = _running({"hgh": [xt_packet("hgh", {"L": []}), xt_packet("hgh", {"L": []})]}, entry)

        client.events.get_scores(Event.ALLIANCE_ALIEN_INVASION)
        client.events.get_scores(Event.ALLIANCE_ALIEN_INVASION, alliance=True)

        assert conn(client).request_payloads == [
            ("hgh", {"LT": 44, "LID": 3, "SV": "-1"}),
            ("hgh", {"LT": 45, "LID": 5, "SV": "-1"}),
        ]

    def test_alliance_rows(self):
        reply = {"LT": 47, "LID": 1, "LR": 12, "L": [[1, 5000, [77, "Allies", 40, 123]], [2, 10, [78, 12345, 3, 0]]]}
        client = _running({"hgh": xt_packet("hgh", reply)}, {"EID": 72, "A": {"LID": 1}})

        scores = client.events.get_scores(Event.ALLIANCE_NOMAD_INVASION, alliance=True)

        assert scores.scores == [
            EventScore(rank=1, points=5000, name="Allies", alliance_id=77, alliance_name="Allies", member_count=40),
            EventScore(rank=2, points=10, name="12345", alliance_id=78, alliance_name="12345", member_count=3),
        ]

    def test_berimond_invasion_needs_a_faction(self):
        client = _running({"hgh": xt_packet("hgh", {"L": []})}, {"EID": 85, "FB": {"LID": 2}, "FR": {"LID": 3}})

        with pytest.raises(ValueError, match="FACTION_INVASION_PLAYER_BLUE or RankingType.FACTION_INVASION_PLAYER_RED"):
            client.events.get_scores(Event.FACTION_INVASION)
        client.events.get_scores(Event.FACTION_INVASION, list_type=RankingType.FACTION_INVASION_PLAYER_RED)

        assert conn(client).request_payloads == [("hgh", {"LT": 55, "LID": 3, "SV": "-1"})]

    def test_rows_that_cannot_be_read_are_skipped(self):
        reply = {"L": [None, [3, 20, None], [4]], "LID": 0}
        client = _running({"hgh": xt_packet("hgh", reply)}, {"EID": 60})

        scores = client.events.get_scores(Event.POINT_EVENT)

        assert scores.league_id is None
        assert [(s.rank, s.points, s.name, s.player_id) for s in scores.scores] == [(3, 20, "", 0), (4, 0, "", 0)]


class TestLeaderboards:
    def test_your_own_page(self):
        reply = {"LT": 53, "LID": 3, "T": 900, "L": [{"R": 41, "S": 1200, "P": "Someone", "A": "Allies", "I": 7}]}
        client = _running({"llsw": xt_packet("llsw", reply)}, {"EID": 83, "LID": 3})

        scores = client.events.get_scores(Event.LONG_TERM_POINT_EVENT, page_size=8)

        assert conn(client).request_payloads == [("llsw", {"LT": 53, "LID": 3, "M": 8, "SI": ""})]
        assert (scores.league_id, scores.total) == (3, 900)
        expected = EventScore(rank=41, points=1200, name="Someone", alliance_name="Allies", instance_id=7)
        assert scores.scores == [expected]

    def test_a_page_from_a_rank(self):
        client = _running({"llsp": xt_packet("llsp", {"LT": 53, "L": [], "T": 0})}, {"EID": 83, "LID": 2})

        client.events.get_scores(Event.LONG_TERM_POINT_EVENT, rank=1)

        assert conn(client).request_payloads == [("llsp", {"LT": 53, "LID": 2, "M": 10, "R": 1})]

    def test_the_donation_board_has_no_league(self):
        client = _running({"llsw": xt_packet("llsw", {"LT": 79, "L": [], "T": 0})}, {"EID": 123, "LID": 5})

        client.events.get_scores(Event.DONATION_EVENT)

        assert conn(client).request_payloads == [("llsw", {"LT": 79, "LID": -1, "M": 10, "SI": ""})]

    def test_a_name_pages_to_its_first_hit(self):
        script = {
            "slse": xt_packet("slse", {"LT": 53, "L": [{"LID": 2, "L": []}, {"LID": 4, "L": ["977", "978"]}]}),
            "llsw": xt_packet("llsw", {"LT": 53, "LID": 4, "L": [], "T": 50}),
        }
        client = _running(script, {"EID": 83, "LID": 3})

        scores = client.events.get_scores(Event.LONG_TERM_POINT_EVENT, name="Someone")

        assert conn(client).request_payloads == [
            ("slse", {"LT": 53, "SV": "Someone"}),
            ("llsw", {"LT": 53, "LID": 4, "M": 10, "SI": "977"}),
        ]
        assert scores.league_id == 4

    def test_a_name_with_no_hit_is_an_empty_page(self):
        client = _running({"slse": xt_packet("slse", {"LT": 53, "L": []})}, {"EID": 83})

        scores = client.events.get_scores(Event.LONG_TERM_POINT_EVENT, name="Nobody")

        assert scores == EventScores(
            event=Event.LONG_TERM_POINT_EVENT, list_type=RankingType.LONG_TERM_POINT_EVENT, league_id=None
        )
        assert [c for c, _ in conn(client).request_payloads] == ["slse"]


class TestRefusals:
    def test_an_event_that_is_not_running(self):
        client = _running(None, {"EID": 60})

        with pytest.raises(EventNotRunningError) as caught:
            client.events.get_scores(Event.FACTION)

        assert caught.value.event_id == 3
        assert conn(client).request_payloads == []

    def test_an_event_a_see_ended(self):
        client = _running(None, {"EID": 3, "LID": 1})
        client._on_packet(xt_packet("see", {"EID": 3}))

        with pytest.raises(EventNotRunningError):
            client.events.get_scores(Event.FACTION)

    def test_a_board_the_event_does_not_have(self):
        client = _running(None, {"EID": 72}, {"EID": 3})

        with pytest.raises(ValueError, match="no player board"):
            client.events.get_scores(Event.ALLIANCE_NOMAD_INVASION)
        with pytest.raises(ValueError, match="no alliance board"):
            client.events.get_scores(Event.FACTION, alliance=True)
        with pytest.raises(ValueError, match="no board"):
            client.events.get_scores(Event.FACTION, list_type=RankingType.POINT_EVENT)

    def test_rank_and_name_together(self):
        client = _running(None, {"EID": 3})

        with pytest.raises(ValueError, match="not both"):
            client.events.get_scores(Event.FACTION, rank=1, name="x")
        with pytest.raises(ValueError, match="empty"):
            client.events.get_scores(Event.FACTION, name="")

    def test_a_server_refusal_raises(self):
        client = _running({"llsw": xt_packet("llsw", {}, error_code=145)}, {"EID": 83})

        with pytest.raises(CommandError):
            client.events.get_scores(Event.LONG_TERM_POINT_EVENT)


class TestRunningScoreEvents:
    def test_only_events_with_a_board_in_sei_order(self):
        client = _running(None, {"EID": 85}, {"EID": 7}, {"EID": 3})

        assert client.events.get_running_score_events() == [Event.FACTION_INVASION, Event.FACTION]


class TestClientDivergencesFixed:
    def test_another_league_opens_on_its_top(self):
        # CastleGenericHighscoreDialog.scrollLeagueUp: "-1" only in your own league
        hgh = [xt_packet("hgh", {"L": []}), xt_packet("hgh", {"L": []})]
        client = _running({"hgh": hgh}, {"EID": 60, "LID": 2})

        client.events.get_scores(Event.POINT_EVENT, league_id=3)
        client.events.get_scores(Event.POINT_EVENT, league_id=2)

        assert conn(client).request_payloads == [
            ("hgh", {"LT": 40, "LID": 3, "SV": "1"}),
            ("hgh", {"LT": 40, "LID": 2, "SV": "-1"}),
        ]

    def test_a_locked_berimond_opens_on_the_top_of_league_one(self):
        # FactionRankingComponent.generateProperties: isLocked?1:ownLeagueID, isLocked?1:-1
        client = _running({"hgh": xt_packet("hgh", {"L": []})}, {"EID": 3, "LID": 3, "UL": 0})

        client.events.get_scores(Event.FACTION)

        assert conn(client).request_payloads == [("hgh", {"LT": 30, "LID": 1, "SV": "1"})]

    def test_a_reply_for_another_board_of_the_event_is_read_as_that_board(self):
        reply = {"LT": 45, "LID": 1, "L": [[1, 50, [77, "Allies", 9, 0]]]}
        client = _running({"hgh": xt_packet("hgh", reply)}, {"EID": 71})

        scores = client.events.get_scores(Event.ALLIANCE_ALIEN_INVASION)

        assert scores.list_type is RankingType.ALLIANCE_ALIEN_INVASION_ALLIANCE
        assert (scores.scores[0].alliance_id, scores.scores[0].member_count) == (77, 9)

    def test_a_reply_for_another_list_is_refused(self):
        # An alliance search's reply (LT 11) taken by an event request
        reply = {"LT": 11, "LID": 6, "SV": "x", "L": [[1, 900, [77, "Allies", 40, 0]]]}
        client = _running({"hgh": xt_packet("hgh", reply)}, {"EID": 60})

        with pytest.raises(ReplyMismatchError) as caught:
            client.events.get_scores(Event.POINT_EVENT)

        assert (caught.value.expected, caught.value.received) == (40, 11)

    def test_an_event_whose_time_ran_out_is_not_running(self, monkeypatch):
        # CastleSpecialEventData.executeUpdateForEvents removes it at remainingEventTimeInSeconds<=0
        now = [1000.0]
        monkeypatch.setattr(event_state, "_clock", lambda: now[0])
        client = _running(None, {"EID": 3, "RS": 60, "LID": 2}, {"EID": 60, "RS": 600})

        now[0] += 61

        assert client.events.get_active_event_ids() == [60]
        assert client.events.get_running_score_events() == [Event.POINT_EVENT]
        assert client.events.get_league_id(3) is None
        with pytest.raises(EventNotRunningError):
            client.events.get_scores(Event.FACTION)

    def test_an_event_never_given_an_end_has_ended(self):
        # ASpecialEventVO starts at _endTimestamp=0
        client = make_client(state=GameState())  # ty: ignore[invalid-argument-type]
        client._on_packet(xt_packet("sei", {"E": [{"EID": 3}]}))

        assert client.events.get_active_event_ids() == []

    def test_the_parts_are_rebuilt_at_league_one(self):
        client = _running(None, {"EID": 80, "SP": {"LID": 4}, "A": {"LID": 2}}, {"EID": 71, "SP": {"LID": 4}})
        client._on_packet(xt_packet("sei", {"E": [{"EID": 80, "RS": 60, "SP": {}}, {"EID": 71, "RS": 60, "A": {}}]}))

        parts = ((80, "SP"), (80, "A"), (71, "SP"), (71, "A"))
        leagues = [client.events.get_league_id(e, part) for e, part in parts]

        # SamuraiInvasionEventVO rebuilds every part; AAlienInvasionEventVO only the parts sent
        assert leagues == [1, 1, 4, 1]

    def test_a_see_forgets_the_leagues_and_a_re_added_event_starts_over(self):
        client = _running(None, {"EID": 71, "LID": 3, "SP": {"LID": 4}})
        client._on_packet(xt_packet("see", {"EID": 71}))
        client._on_packet(xt_packet("sei", {"E": [{"EID": 71, "RS": 60}]}))

        assert (client.events.get_league_id(71), client.events.get_league_id(71, "SP")) == (1, 1)
        assert client.state.get_event(71).parts == {}

    def test_rank_starts_at_one(self):
        client = _running(None, {"EID": 3})

        with pytest.raises(ValueError, match="rank starts at 1"):
            client.events.get_scores(Event.FACTION, rank=0)

    def test_alliance_with_a_player_board_is_refused(self):
        client = _running(None, {"EID": 85})

        with pytest.raises(ValueError, match="not FACTION_INVASION's alliance board"):
            client.events.get_scores(
                Event.FACTION_INVASION, alliance=True, list_type=RankingType.FACTION_INVASION_PLAYER_BLUE
            )

    def test_an_event_without_a_board(self):
        client = _running(None, {"EID": 15})

        with pytest.raises(ValueError, match="no scoreboard"):
            client.events.get_scores(Event.LUCKY_WHEEL)
