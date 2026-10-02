"""Highscore list types and the hgh/llsp request shapes, checked against the client."""

import json
import logging

import pytest
from pydantic import ValidationError

from empire_core.alliance.models.search import SearchAllianceRequest
from empire_core.enums import RankingType
from empire_core.protocol.base import get_response_model
from empire_core.protocol.models import GetHighscoreRequest, GetRankingListRequest
from empire_core.ranking.models import (
    GetHighscoreResponse,
    GetRankingListResponse,
    GetRankingWindowRequest,
    GetRankingWindowResponse,
    RankingEntry,
    SearchRankingListRequest,
    SearchRankingListResponse,
)

# Every list id in HighscoreConst (dll line 19438); the page sizes, point
# values, sentinels and the PLAYER_BUILDINGS/ALLIANCE_BUILDINGS aliases are left out.
HIGHSCORE_CONST_LISTS = {
    "PLAYER_ACHIEVEMENT_POINTS": 1,
    "PLAYER_WEEKLY_LOOT": 2,
    "PLAYER_HONOR": 5,
    "PLAYER_MIGHT_POINTS": 6,
    "PLAYER_LEGEND": 7,
    "ALLIANCE_HONOR": 10,
    "ALLIANCE_MIGHT_POINTS": 11,
    "ALLIANCE_LANDMARKS": 12,
    "ALLIANCE_AQUA_POINTS": 13,
    "TOURNAMENT_FAME": 20,
    "ALLIANCE_TOURNAMENT_FAME": 21,
    "FACTION_TOURNAMENT": 30,
    "POINT_EVENT": 40,
    "BEGGING_KNIGHTS": 41,
    "ALIEN_INVASION": 42,
    "LUCKY_WHEEL": 43,
    "ALLIANCE_ALIEN_INVASION_PLAYER": 44,
    "ALLIANCE_ALIEN_INVASION_ALLIANCE": 45,
    "ALLIANCE_NOMADINVASION_PLAYER": 46,
    "ALLIANCE_NOMADINVASION_ALLIANCE": 47,
    "NOMADINVASION": 48,
    "ALLIANCE_SAMURAI_ALIEN_INVASION_PLAYER": 500,
    "ALLIANCE_SAMURAI_ALIEN_INVASION_ALLIANCE": 501,
    "COLOSSUS": 50,
    "SAMURAI_PLAYER": 51,
    "SAMURAI_ALLIANCE": 52,
    "LONG_TERM_POINT_EVENT": 53,
    "FACTION_INVASION_PLAYER_BLUE": 54,
    "FACTION_INVASION_PLAYER_RED": 55,
    "FACTION_INVASION_ALLIANCE": 56,
    "ALLIANCE_RED_ALIEN_INVASION_PLAYER": 58,
    "ALLIANCE_RED_ALIEN_INVASION_ALLIANCE": 59,
    "TEMP_SERVER_DAILY_MIGHT_POINTS_BUILDINGS": 61,
    "TEMP_SERVER_GLOBAL": 62,
    "KINGDOMS_LEAGUE_SEASON": 63,
    "KINGDOMS_LEAGUE_SEASON_EVENT": 64,
    "TEMP_SERVER_DAILY_COLLECTOR_POINTS": 65,
    "TEMP_SERVER_DAILY_RANK_SWAP": 66,
    "ALLIANCE_KINGDOMS_LEAGUE_SEASON": 67,
    "ALLIANCE_KINGDOMS_LEAGUE_SEASON_EVENT": 68,
    "ALLIANCE_DAIMYO": 69,
    "ALLIANCE_BATTLE_GROUND_ALLIANCE_COLLECTOR": 70,
    "ALLIANCE_BATTLE_GROUND_PLAYER_COLLECTOR": 71,
    "LUCKY_WHEEL_SALE_DAYS": 72,
    "ALLIANCE_BATTLE_GROUND_ALLIANCE_TOWER": 74,
    "ALLIANCE_BATTLE_GROUND_PLAYER_TOWER": 75,
    "TEMPSERVER_PREVIOUS_RUN_PLAYER": 76,
    "ALLIANCE_BATTLE_GROUND_PREVIOUS_RUN_ALLIANCE": 77,
    "ALLIANCE_BATTLE_GROUND_PREVIOUS_RUN_PLAYER": 78,
    "DONATION_EVENT": 79,
    "DECO_GACHA_EVENT": 80,
    "CHRISTMAS_GACHA_EVENT": 81,
    "EASTER_GACHA_EVENT": 82,
    "SUMMER_GACHA_EVENT": 83,
    "ALLIANCE_MOBILISATION_EVENT": 84,
    "ANNIVERSARY_GACHA_EVENT": 85,
    "HALLOWEEN_GACHA_EVENT": 86,
    "BLACK_FRIDAY_GACHA_EVENT": 87,
    "CARNIVAL_GACHA_EVENT": 88,
    "ALLIANCE_RAID_MOBILISATION_EVENT": 89,
}


class TestRankingType:
    def test_members_are_the_client_list_ids(self):
        assert {member.name: member.value for member in RankingType} == HIGHSCORE_CONST_LISTS

    def test_the_client_aliases_resolve_to_the_might_lists(self):
        # HighscoreConst.PLAYER_BUILDINGS=6 and ALLIANCE_BUILDINGS=11, as CastleHighscoreDialog sends them
        assert RankingType(6) is RankingType.PLAYER_MIGHT_POINTS
        assert RankingType(11) is RankingType.ALLIANCE_MIGHT_POINTS

    @pytest.mark.parametrize("value", [60, 113, 134])
    def test_values_the_client_has_no_list_for(self, value):
        with pytest.raises(ValueError):
            RankingType(value)


class TestHighscoreRequest:
    def test_payload_follows_the_client_key_order(self):
        request = GetHighscoreRequest(list_type=RankingType.SAMURAI_ALLIANCE, league_type_id=3, search_value="12")

        payload = request.to_payload()

        assert list(payload.items()) == [("LT", 52), ("LID", 3), ("SV", "12")]

    def test_league_defaults_to_minus_one_and_is_always_sent(self):
        # C2SGetHighscoreVO(t, i, n): void 0===n&&(n=-1)
        assert GetHighscoreRequest(list_type=RankingType.PLAYER_MIGHT_POINTS, search_value="-1").to_payload() == {
            "LT": 6,
            "LID": -1,
            "SV": "-1",
        }

    def test_search_value_is_encoded_as_the_client_encodes_text(self):
        request = GetHighscoreRequest(list_type=RankingType.PLAYER_MIGHT_POINTS, search_value="50% o'clock")

        assert json.loads(request.to_packet().split("%")[5])["SV"] == "50&percnt; o&145;clock"

    def test_alliance_search_is_the_same_vo(self):
        payload = SearchAllianceRequest.create("Knights' Hall").to_payload()

        assert list(payload.items()) == [("LT", 11), ("LID", 6), ("SV", "Knights&145; Hall")]


class TestRankingListRequest:
    def test_payload_follows_the_client_key_order(self):
        request = GetRankingListRequest(
            list_type=RankingType.LONG_TERM_POINT_EVENT, league_type_id=2, max_results=8, rank=41
        )

        assert list(request.to_payload().items()) == [("LT", 53), ("LID", 2), ("M", 8), ("R", 41)]

    def test_defaults_match_the_client(self):
        # C2SListLeaderboardScoresPageVO: R=1; M has no default
        assert GetRankingListRequest(
            list_type=RankingType.ALLIANCE_MOBILISATION_EVENT, league_type_id=4, max_results=10
        ).to_payload() == {
            "LT": 84,
            "LID": 4,
            "M": 10,
            "R": 1,
        }

    def test_the_league_is_required(self):
        # LeaderBoardDataProvider sends the league it was built with on every page
        with pytest.raises(ValidationError):
            GetRankingListRequest(list_type=RankingType.LONG_TERM_POINT_EVENT, max_results=10)  # type: ignore[call-arg]

    def test_alliance_event_keys_follow_the_vo_keys(self):
        # LeaderBoardDataProvider.sendCommand copies {SDI, EID} onto the VO after its constructor
        request = GetRankingListRequest(
            list_type=RankingType.ALLIANCE_MOBILISATION_EVENT,
            league_type_id=4,
            max_results=10,
            rank=11,
            sub_division_id=7,
            event_id=94,
        )

        assert list(request.to_payload().items()) == [
            ("LT", 84),
            ("LID", 4),
            ("M", 10),
            ("R", 11),
            ("SDI", 7),
            ("EID", 94),
        ]


class TestRankingWindowRequest:
    def test_payload_follows_the_client_key_order(self):
        # C2SListLeaderboardScoresWindowVO: LT, LID, M, SI
        request = GetRankingWindowRequest(
            list_type=RankingType.LONG_TERM_POINT_EVENT, league_type_id=3, max_results=8, score_id="1234"
        )

        assert list(request.to_payload().items()) == [("LT", 53), ("LID", 3), ("M", 8), ("SI", "1234")]

    def test_own_page_sends_an_empty_score_id_and_the_league(self):
        # getCurrentPlayerPage: new C2SListLeaderboardScoresWindowVO(LT, LID, M), SI defaults to ""
        assert GetRankingWindowRequest(
            list_type=RankingType.POINT_EVENT, league_type_id=2, max_results=8
        ).to_payload() == {
            "LT": 40,
            "LID": 2,
            "M": 8,
            "SI": "",
        }

    def test_the_league_is_required(self):
        with pytest.raises(ValidationError):
            GetRankingWindowRequest(list_type=RankingType.POINT_EVENT, max_results=8)  # type: ignore[call-arg]

    def test_score_id_is_encoded_as_the_client_encodes_text(self):
        request = GetRankingWindowRequest(
            list_type=RankingType.POINT_EVENT, league_type_id=1, max_results=8, score_id='a"b'
        )

        assert json.loads(request.to_packet().split("%", 5)[5][:-1])["SI"] == "a&quot;b"

    def test_a_result_without_a_league_sends_none(self):
        # getCurrentSearchPage passes the hit's LID as read; undefined is not serialised
        request = GetRankingWindowRequest(
            list_type=RankingType.POINT_EVENT, league_type_id=None, max_results=8, score_id="5"
        )

        assert request.to_payload() == {"LT": 40, "M": 8, "SI": "5"}

    def test_alliance_event_keys_follow_the_vo_keys(self):
        request = GetRankingWindowRequest(
            list_type=RankingType.ALLIANCE_RAID_MOBILISATION_EVENT, league_type_id=1, max_results=10, event_id=112
        )

        assert list(request.to_payload()) == ["LT", "LID", "M", "SI", "EID"]


class TestSearchRankingListRequest:
    def test_payload_follows_the_client_key_order(self):
        # C2SSearchLeaderboardScoresEventVO: LT, SV
        request = SearchRankingListRequest(list_type=RankingType.LONG_TERM_POINT_EVENT, search_value="Someone")

        assert list(request.to_payload().items()) == [("LT", 53), ("SV", "Someone")]

    def test_search_value_is_encoded_as_the_client_encodes_text(self):
        request = SearchRankingListRequest(list_type=RankingType.POINT_EVENT, search_value="50% o'clock")

        assert json.loads(request.to_packet().split("%", 5)[5][:-1])["SV"] == "50&percnt; o&145;clock"

    def test_alliance_event_keys_follow_the_vo_keys(self):
        request = SearchRankingListRequest(
            list_type=RankingType.ALLIANCE_MOBILISATION_EVENT, search_value="x", sub_division_id=2, event_id=94
        )

        assert list(request.to_payload()) == ["LT", "SV", "SDI", "EID"]


class TestRankingWindowResponse:
    def test_is_registered_for_llsw_and_reads_as_llsp(self):
        # LLSWCommand dispatches LEADERBOARD_SCORE_DATA, as LLSPCommand does
        assert get_response_model("llsw") is GetRankingWindowResponse
        assert get_response_model("llsp") is GetRankingListResponse

        response = GetRankingWindowResponse.model_validate(
            {"LT": 53, "LID": 2, "T": 40, "L": [{"R": 17, "S": 900, "P": "Player", "A": "", "I": 3, "SI": 4501}]}
        )

        assert (response.list_type, response.league_type_id, response.total) == (53, 2, 40)
        assert (response.scores[0].rank, response.scores[0].score_id) == (17, 4501)


class TestSearchRankingListResponse:
    def test_results_are_grouped_by_league(self):
        # onSearchDataReceived: e.params.L.forEach(e => e.L.forEach(i => push({leagueTypeId: e.LID, scoreId: i})))
        response = SearchRankingListResponse.model_validate(
            {"LT": 53, "LID": 2, "L": [{"LID": 2, "L": ["4501", "4502"]}, {"LID": 3, "L": ["977"]}]}
        )

        assert get_response_model("slse") is SearchRankingListResponse
        assert (response.list_type, response.league_type_id) == (53, 2)
        assert [(r.league_type_id, r.score_ids) for r in response.results] == [(2, ["4501", "4502"]), (3, ["977"])]

    @pytest.mark.parametrize(("lid", "expected"), [(4, 4), ("4", 4), (0, -1), (None, -1)])
    def test_a_falsy_league_reads_as_minus_one(self, lid, expected):
        # onSearchDataReceived compares against e.params.LID || -1
        assert SearchRankingListResponse.model_validate({"LT": 53, "LID": lid, "L": []}).league_type_id == expected

    def test_unreadable_results_cost_only_themselves(self):
        response = SearchRankingListResponse.model_validate(
            {"L": [None, "x", {"LID": 1, "L": [12, "13", None, {}]}, {"LID": 2, "L": "nope"}]}
        )

        assert [(r.league_type_id, r.score_ids) for r in response.results] == [(1, ["12", "13"]), (2, [])]

    def test_no_results(self):
        assert SearchRankingListResponse.model_validate({"LT": 53}).results == []


class TestResponseLeague:
    @pytest.mark.parametrize(("lid", "expected"), [(5, 5), ("5", 5), ("0", 0), (0, -1), (None, -1), ("", -1)])
    def test_hgh_reads_a_falsy_league_as_minus_one(self, lid, expected):
        # HGHCommand.executeCommand: n=-1; i.LID&&(n=int(i.LID))
        assert GetHighscoreResponse.model_validate({"LT": 6, "LID": lid, "L": []}).league_type_id == expected

    def test_hgh_without_a_league_reads_minus_one(self):
        assert GetHighscoreResponse.model_validate({"LT": 6, "L": []}).league_type_id == -1

    @pytest.mark.parametrize(("lid", "expected"), [(3, 3), ("3", 3), (0, None), (None, None)])
    def test_llsp_reads_a_falsy_league_as_none(self, lid, expected):
        # LeaderBoardDataProvider.onScoreDataReceived: e.params.LID || this._leagueTypeID
        assert GetRankingListResponse.model_validate({"LT": 53, "LID": lid, "L": []}).league_type_id == expected


class TestGoldenRankingPayloads:
    def test_dict_details_layout(self):
        payload = {"L": [[1, 999999, {"OID": 7001, "N": "LeaderGuy", "AID": 301, "AN": "PACT"}]]}
        entry = GetHighscoreResponse.model_validate(payload).entries[0]
        assert (entry.rank, entry.score, entry.entity_id, entry.name) == (1, 999999, 7001, "LeaderGuy")
        assert (entry.alliance_id, entry.alliance_name) == (301, "PACT")

    def test_list_details_layout(self):
        payload = {"L": [[2, 888888, [7002, "OfficerGal"]]]}
        entry = GetHighscoreResponse.model_validate(payload).entries[0]
        assert (entry.rank, entry.score, entry.entity_id, entry.name) == (2, 888888, 7002, "OfficerGal")

    def test_nested_name_field_is_flattened(self):
        payload = {"L": [[2, 888888, [7002, ["OfficerGal"]]]]}
        assert GetHighscoreResponse.model_validate(payload).entries[0].name == "OfficerGal"

    def test_cargo_layout_has_a_leading_extra_value(self):
        # LT=13 prepends the cargo value: [cargo, rank, score, {details}].
        payload = {"L": [[5000, 3, 777777, {"OID": 7003, "N": "AfkDude"}]]}
        entry = GetHighscoreResponse.model_validate(payload).entries[0]
        assert (entry.rank, entry.score, entry.entity_id, entry.name) == (3, 777777, 7003, "AfkDude")

    def test_flat_layout(self):
        payload = {"L": [[4, 666, 7004, "FlatGuy"]]}
        entry = GetHighscoreResponse.model_validate(payload).entries[0]
        assert (entry.rank, entry.score, entry.entity_id, entry.name) == (4, 666, 7004, "FlatGuy")

    def test_ranking_list_dict_layout(self):
        payload = {"L": [{"R": 3, "S": 500, "P": "SomePlayer", "A": "SomeAlliance"}], "T": 12345}
        response = GetRankingListResponse.model_validate(payload)
        assert response.total == 12345
        entry = response.entries[0]
        assert (entry.rank, entry.score, entry.name, entry.alliance_name) == (3, 500, "SomePlayer", "SomeAlliance")

    def test_unranked_synthetic_entry(self):
        entry = RankingEntry.unranked("Nobody")
        assert (entry.rank, entry.score, entry.name) == (-1, 0, "Nobody")


class TestRankingEntryDriftedLayouts:
    """RankingEntry parses four different shapes and must never raise."""

    @pytest.mark.parametrize(
        "raw",
        [
            {},
            [],
            [1],
            [1, 2],
            None,
            "abcd",
            [1, 2, None],
            [None, None, {}],
            [1, 2, {"unexpected": "keys"}],
            [[1, 2], [3, 4]],
        ],
    )
    def test_drifted_entries_never_raise(self, raw):
        entry = RankingEntry(raw)
        assert entry.raw is raw
        assert repr(entry)

    @pytest.mark.parametrize("raw", [[], [1, 2]])
    def test_unknown_layout_is_logged_and_left_unranked(self, raw, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.ranking.models"):
            entry = RankingEntry(raw)
        assert entry.rank == -1
        assert "Unknown RankingEntry format" in caplog.text

    def test_a_layout_that_raises_internally_is_logged_as_an_error(self, caplog):
        with caplog.at_level(logging.ERROR, logger="empire_core.ranking.models"):
            # Deliberately not a list/dict: the point of the test is that an
            # unparseable layout degrades to rank -1 rather than raising.
            entry = RankingEntry(None)  # type: ignore[arg-type]
        assert entry.rank == -1
        assert "Failed to parse RankingEntry" in caplog.text


class TestLeaderboardLeniency:
    def test_null_and_odd_values_read_as_the_getter_defaults(self):
        from empire_core.protocol.models import GetRankingListResponse

        response = GetRankingListResponse.model_validate(
            {"L": [{"R": 1, "S": 10, "P": "a", "A": None}, {"R": None, "S": None, "P": None, "I": "abc"}]}
        )
        first, second = response.scores
        assert (first.rank, first.alliance_name) == (1, "")
        assert (second.rank, second.score, second.player_name, second.instance_id) == (-1, -1, "", 0)
