"""Tests for the ranking service."""

from __future__ import annotations

import pytest

from empire_core.enums import RankingType
from empire_core.exceptions import CommandError
from tests.service_helpers import conn, make_client, xt_packet

# =============================================================================
# RankingService
# =============================================================================


class TestRankingService:
    def test_highscore_dict_details_layout(self):
        payload = {"L": [[1, 999999, {"OID": 7001, "N": "LeaderGuy", "AID": 190426, "AN": "HOPE"}]]}
        client = make_client({"hgh": xt_packet("hgh", payload)})

        entries = client.ranking.get_highscore(list_type=RankingType.PLAYER_MIGHT_POINTS, search_value="LeaderGuy")

        assert len(entries) == 1
        entry = entries[0]
        assert (entry.rank, entry.score, entry.entity_id) == (1, 999999, 7001)
        assert (entry.name, entry.alliance_id, entry.alliance_name) == ("LeaderGuy", 190426, "HOPE")

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

        entries = client.ranking.get_ranking_list(list_type=RankingType.LONG_TERM_POINT_EVENT, rank=3, max_results=8)

        assert (entries[0].rank, entries[0].score) == (3, 500)
        assert (entries[0].name, entries[0].alliance_name) == ("SomePlayer", "SomeAlliance")
        assert conn(client).request_payloads == [("llsp", {"LT": 53, "LID": -1, "M": 8, "R": 3})]

    def test_error_raises(self):
        client = make_client({"hgh": xt_packet("hgh", error_code=21)})
        with pytest.raises(CommandError):
            client.ranking.get_highscore(list_type=RankingType.PLAYER_MIGHT_POINTS, search_value="x")
