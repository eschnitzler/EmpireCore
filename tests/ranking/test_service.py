"""Tests for the ranking service."""

from __future__ import annotations

import pytest

from empire_core.enums import RankingType
from empire_core.exceptions import CommandError
from empire_core.ranking import HighscorePlayerRow
from tests.service_helpers import conn, make_client, xt_packet

# =============================================================================
# RankingService
# =============================================================================


class TestRankingService:
    def test_highscore_dict_details_layout(self):
        payload = {"L": [[1, 999999, {"OID": 7001, "N": "LeaderGuy", "AID": 301, "AN": "PACT"}]]}
        client = make_client({"hgh": xt_packet("hgh", payload)})

        entries = client.ranking.get_highscore(list_type=RankingType.PLAYER_MIGHT_POINTS, search_value="LeaderGuy")

        (row,) = entries
        assert isinstance(row, HighscorePlayerRow) and row.owner is not None
        assert (row.rank, row.score, row.owner.owner_id) == (1, 999999, 7001)
        assert (row.owner.owner_name, row.owner.alliance_id, row.owner.alliance_name) == ("LeaderGuy", 301, "PACT")

    def test_highscore_sends_list_type_league_and_search_value(self):
        client = make_client({"hgh": xt_packet("hgh", {"L": []})})

        client.ranking.get_highscore(
            list_type=RankingType.PLAYER_MIGHT_POINTS, search_value="LeaderGuy", league_type_id=6
        )

        assert conn(client).request_payloads == [("hgh", {"LT": 6, "LID": 6, "SV": "LeaderGuy"})]

    def test_highscore_sends_minus_one_for_an_unset_league(self):
        # C2SGetHighscoreVO defaults LID to -1 and always sends it
        client = make_client({"hgh": xt_packet("hgh", {"L": []})})
        client.ranking.get_highscore(list_type=RankingType.PLAYER_MIGHT_POINTS, search_value="x")
        assert conn(client).request_payloads == [("hgh", {"LT": 6, "LID": -1, "SV": "x"})]

    def test_ranking_list_by_position(self):
        payload = {"L": [{"R": 3, "S": 500, "P": "SomePlayer", "A": "SomeAlliance"}], "T": 1000}
        client = make_client({"llsp": xt_packet("llsp", payload)})

        entries = client.ranking.get_ranking_list(
            list_type=RankingType.LONG_TERM_POINT_EVENT, rank=3, max_results=8, league_type_id=3
        )

        assert (entries[0].rank, entries[0].score) == (3, 500)
        assert (entries[0].player_name, entries[0].alliance_name) == ("SomePlayer", "SomeAlliance")
        assert conn(client).request_payloads == [("llsp", {"LT": 53, "LID": 3, "M": 8, "R": 3})]

    def test_the_donation_ranking_sends_no_league(self):
        # DonationEventDialogRanking: GlobalLeaderBoardComponent.init(highscoreID), so LID -1
        client = make_client({"llsp": xt_packet("llsp", {"L": [], "T": 0})})

        client.ranking.get_ranking_list(RankingType.LONG_TERM_POINT_EVENT, 1, 10, -1)

        assert conn(client).request_payloads == [("llsp", {"LT": 53, "LID": -1, "M": 10, "R": 1})]

    def test_ranking_list_sends_the_alliance_event_keys(self):
        client = make_client({"llsp": xt_packet("llsp", {"L": [], "T": 0})})

        client.ranking.get_ranking_list(
            list_type=RankingType.ALLIANCE_MOBILISATION_EVENT, rank=1, max_results=10, league_type_id=4, event_id=94
        )

        assert conn(client).request_payloads == [("llsp", {"LT": 84, "LID": 4, "M": 10, "R": 1, "EID": 94})]

    def test_own_ranking_page(self):
        payload = {"LT": 53, "LID": 2, "T": 40, "L": [{"R": 17, "S": 900, "P": "Player", "A": "Alliance"}]}
        client = make_client({"llsw": xt_packet("llsw", payload)})

        entries = client.ranking.get_own_ranking_page(
            list_type=RankingType.LONG_TERM_POINT_EVENT, max_results=8, league_type_id=2
        )

        assert (entries[0].rank, entries[0].player_name) == (17, "Player")
        assert conn(client).request_payloads == [("llsw", {"LT": 53, "LID": 2, "M": 8, "SI": ""})]

    def test_search_then_page_to_a_hit(self):
        client = make_client(
            {
                "slse": xt_packet("slse", {"LT": 53, "LID": 2, "L": [{"LID": 3, "L": ["977"]}]}),
                "llsw": xt_packet("llsw", {"LT": 53, "LID": 3, "T": 40, "L": [{"R": 5, "S": 10, "P": "Someone"}]}),
            }
        )

        results = client.ranking.search_leaderboard(list_type=RankingType.LONG_TERM_POINT_EVENT, search_value="Some")
        hit = results[0]
        entries = client.ranking.get_ranking_window(
            list_type=RankingType.LONG_TERM_POINT_EVENT,
            score_id=hit.score_ids[0],
            max_results=8,
            league_type_id=hit.league_type_id,
        )

        assert entries[0].player_name == "Someone"
        assert conn(client).request_payloads == [
            ("slse", {"LT": 53, "SV": "Some"}),
            ("llsw", {"LT": 53, "LID": 3, "M": 8, "SI": "977"}),
        ]

    def test_an_empty_search_is_not_sent(self):
        # searchLeaderBoard: ""!=e&&null!=e&&this.sendCommand(...)
        client = make_client({})

        with pytest.raises(ValueError):
            client.ranking.search_leaderboard(list_type=RankingType.LONG_TERM_POINT_EVENT, search_value="")

        assert conn(client).request_payloads == []

    def test_error_raises(self):
        client = make_client({"hgh": xt_packet("hgh", error_code=21)})
        with pytest.raises(CommandError):
            client.ranking.get_highscore(list_type=RankingType.PLAYER_MIGHT_POINTS, search_value="x")
