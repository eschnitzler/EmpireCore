"""Highscore list types and the hgh/llsp request shapes, checked against the client."""

import json

import pytest

from empire_core.alliance.models.info import SearchAllianceRequest
from empire_core.enums import RankingType
from empire_core.protocol.models import GetHighscoreRequest, GetRankingListRequest
from empire_core.ranking.models import GetHighscoreResponse, GetRankingListResponse

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
        request = GetHighscoreRequest(LT=RankingType.SAMURAI_ALLIANCE, LID=3, SV="12")

        payload = request.to_payload()

        assert list(payload.items()) == [("LT", 52), ("LID", 3), ("SV", "12")]

    def test_league_defaults_to_minus_one_and_is_always_sent(self):
        # C2SGetHighscoreVO(t, i, n): void 0===n&&(n=-1)
        assert GetHighscoreRequest(LT=RankingType.PLAYER_MIGHT_POINTS, SV="-1").to_payload() == {
            "LT": 6,
            "LID": -1,
            "SV": "-1",
        }

    def test_search_value_is_encoded_as_the_client_encodes_text(self):
        request = GetHighscoreRequest(LT=RankingType.PLAYER_MIGHT_POINTS, SV="50% o'clock")

        assert json.loads(request.to_packet().split("%")[5])["SV"] == "50&percnt; o&145;clock"

    def test_alliance_search_is_the_same_vo(self):
        payload = SearchAllianceRequest.create("Knights' Hall").to_payload()

        assert list(payload.items()) == [("LT", 11), ("LID", 6), ("SV", "Knights&145; Hall")]


class TestRankingListRequest:
    def test_payload_follows_the_client_key_order(self):
        request = GetRankingListRequest(LT=RankingType.LONG_TERM_POINT_EVENT, LID=2, M=8, R=41)

        assert list(request.to_payload().items()) == [("LT", 53), ("LID", 2), ("M", 8), ("R", 41)]

    def test_defaults_match_the_client(self):
        # C2SListLeaderboardScoresPageVO: LID=-1, R=1; M has no default
        assert GetRankingListRequest(LT=RankingType.ALLIANCE_MOBILISATION_EVENT, M=10).to_payload() == {
            "LT": 84,
            "LID": -1,
            "M": 10,
            "R": 1,
        }


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
