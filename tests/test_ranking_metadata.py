"""Golden ranking payload shapes from issue #138; no game connection required."""

import pytest

from empire_core.protocol.models.ranking import GetHighscoreResponse, GetRankingListResponse, RankingEntry


def test_player_highscore_metadata():
    response = GetHighscoreResponse.model_validate(
        {
            "LT": 6,
            "LID": 5,
            "LR": 120,
            "SV": "Player",
            "L": [
                [
                    2,
                    900,
                    {
                        "OID": 42,
                        "N": "Player",
                        "L": 70,
                        "LL": 800,
                        "H": 2300,
                        "MP": 900,
                        "AID": 8,
                        "AN": "Alliance",
                    },
                ]
            ],
        }
    )
    assert (response.list_type, response.list_id, response.last_rank, response.search_value) == (6, 5, 120, "Player")
    entry = response.entries[0]
    assert (entry.entity_id, entry.name, entry.alliance_id, entry.alliance_name) == (42, "Player", 8, "Alliance")
    assert (entry.level, entry.legend_level, entry.honor, entry.might) == (70, 800, 2300, 900)


@pytest.mark.parametrize("list_type", [10, 11, 12])
def test_alliance_highscore_details(list_type):
    response = GetHighscoreResponse.model_validate(
        {"LT": list_type, "LID": 1, "LR": 40, "SV": "Alliance", "L": [[1, 8000, [8, "Alliance", 65, 1234]]]}
    )
    entry = response.entries[0]
    assert (entry.entity_id, entry.name, entry.member_count, entry.fame) == (8, "Alliance", 65, 1234)


def test_global_list_paging_and_server_metadata():
    response = GetRankingListResponse.model_validate(
        {
            "LT": 71,
            "LID": 6,
            "T": 1200,
            "L": [
                {"R": 3, "S": 900, "P": "Player", "A": "Alliance", "I": 12, "SI": 456},
                {"R": 4, "S": 800, "P": "Solo", "I": 13, "SI": 457},
            ],
        }
    )
    assert (response.list_type, response.list_id, response.total) == (71, 6, 1200)
    first, second = response.entries
    assert (first.instance_id, first.score_id, first.alliance_name) == (12, 456, "Alliance")
    assert (second.instance_id, second.score_id, second.alliance_name) == (13, 457, "")
    assert first.entity_id == 0  # A score ID is not evidence of an owner ID.
    top = response.scores[0]
    assert (top.rank, top.score, top.player_name, top.alliance_name) == (3, 900, "Player", "Alliance")
    assert (top.instance_id, top.score_id) == (12, 456)
    assert response.scores[1].alliance_name == ""


def test_llsp_rows_the_client_would_not_break_on():
    response = GetRankingListResponse.model_validate({"L": [{"R": 1, "S": 12.5, "P": "p"}, None]})
    assert [(s.rank, s.score) for s in response.scores] == [(1, 12.5), (-1, -1)]


def test_empty_highscore_retains_zero_last_rank_and_search():
    response = GetHighscoreResponse.model_validate({"LT": 5, "LID": 6, "LR": 0, "SV": "Nobody", "L": []})
    assert response.last_rank == 0
    assert response.search_value == "Nobody"
    assert response.entries == []


def test_missing_metadata_and_unranked_have_safe_defaults():
    assert GetHighscoreResponse.model_validate({}).last_rank is None
    assert GetRankingListResponse.model_validate({}).list_id is None
    for entry in [RankingEntry({}), RankingEntry([1, 2, [3, "Name"]]), RankingEntry.unranked("Nobody")]:
        assert (entry.instance_id, entry.score_id) == (None, None)
        assert (entry.level, entry.legend_level, entry.honor, entry.might) == (0, 0, 0, 0)
        assert (entry.member_count, entry.fame) == (0, 0)
