"""The events' lookups into the special server and season tables, done as the client does them."""

import pytest

from empire_core.enums import CollectableKind
from empire_core.events.board_models import GetOuterRealmsRanksResponse
from empire_core.events.models import GrandTournamentEvent, KingdomsLeagueEvent, OuterRealmsEvent, RiftRaidEvent
from empire_core.events.status_models import RiftRaidStatus
from empire_core.gamedata import (
    DivisionRoundId,
    GameData,
    KingdomsLeagueRankId,
    KingdomsLeagueRewardSetId,
    OuterRealmsRewardSetId,
    OuterRealmsSettingId,
    RaidBossLevelId,
    RaidBossStageId,
    ids,
)
from tests.gamedata.test_tables_seasons import ITEMS


@pytest.fixture
def data() -> GameData:
    return GameData.parse("790.06", ITEMS)


class TestOuterRealmsEvent:
    def test_daily_rank_points_come_from_the_first_band_holding_the_rank(self, data):
        def points(rank: object) -> int:
            ranks = GetOuterRealmsRanksResponse.model_validate({"DHS": 0, "DR": rank, "HS": 0, "R": 0})
            return ranks.daily_rank_points(game_data=data)

        assert (points(45000), points(1), points(50001)) == (10000, 110000, 0)
        # an unranked -1 reads as 0, which no band holds
        assert points(-1) == 0

    def test_the_runs_rank_rewards_come_from_its_settings_reward_set(self):
        rows = [
            {"tempServerRankRewardID": "1", "rank": "1", "rewardSetID": "14"},
            {"tempServerRankRewardID": "2", "participationPoints": "100", "rewardSetID": "14"},
            {"tempServerRankRewardID": "3", "rank": "5", "rewardSetID": "14"},
            {"tempServerRankRewardID": "4", "participationPoints": "900", "rewardSetID": "14"},
            {"tempServerRankRewardID": "5", "rank": "2", "rewardSetID": "4"},
            {"tempServerRankRewardID": "6", "rewardSetID": "14"},
        ]
        data = GameData.parse("790.06", {**ITEMS, "tempServerRankRewards": rows})
        assert data.outer_realms_settings[OuterRealmsSettingId(24)].reward_set_id == OuterRealmsRewardSetId(14)

        event = OuterRealmsEvent(event_id=106, setting_id=OuterRealmsSettingId(24))

        # TempServerEventVO.sortRewards: the points rewards first, then from the highest value down
        assert [row.rank_reward_id for row in event.rank_rewards(game_data=data)] == [4, 2, 3, 1]
        assert OuterRealmsEvent(event_id=106).rank_rewards(game_data=data) == ()
        assert OuterRealmsEvent(event_id=106, setting_id=OuterRealmsSettingId(99)).rank_rewards(game_data=data) == ()

    def test_daily_task_rewards_add_up_every_step_reached(self, data):
        assert OuterRealmsEvent.daily_task_rewards(4, game_data=data) == ()
        coins = OuterRealmsEvent.daily_task_rewards(40, game_data=data)
        assert [(c.kind, c.amount) for c in coins] == [(CollectableKind.COINS, 300), (CollectableKind.RUBIES, 5)]


class TestKingdomsLeagueEvent:
    def test_end_reward_bands_follow_the_reward_set_and_league_type(self, data):
        league = KingdomsLeagueEvent(
            event_id=601, reward_set_id=KingdomsLeagueRewardSetId(7), league_type_id=ids.LeagueType(1)
        )
        other = KingdomsLeagueEvent(event_id=601, reward_set_id=KingdomsLeagueRewardSetId(1), league_type_id=2)

        assert [row.end_reward_id for row in league.end_reward_bands(game_data=data)] == [192]
        # a row with no leaguetypeID (0) is for every league
        assert [row.end_reward_id for row in other.end_reward_bands(game_data=data)] == [1]

    def test_promotion_and_event_rewards_pick_their_rows(self):
        rewards = [
            {"rewardID": "1", "currency1": "1"},
            {"rewardID": "2", "currency1": "2"},
            {"rewardID": "3", "currency1": "3"},
            {"rewardID": "4", "currency1": "4"},
        ]
        items = {
            "rewards": rewards,
            "seasonPromotionRewards": [
                {"id": "1", "leaguetypeID": "2", "rewardSetID": "7", "rankID": "21", "rewardIDs": "1"},
                {"id": "2", "rewardSetID": "7", "rankID": "21", "rewardIDs": "2"},
                {"id": "3", "rewardSetID": "7", "rankID": "21", "rewardIDs": "3"},
                {"id": "4", "rewardSetID": "7", "rankID": "21", "needsSeasonPass": "1", "rewardIDs": "4"},
            ],
            "seasonEventRewards": [
                {"id": "1", "rewardSetID": "7", "eventIDs": "3,71", "rankID": "21", "rewardIDs": "1,2"},
                {"id": "2", "rewardSetID": "7", "eventIDs": "71", "rankID": "21", "rewardIDs": "3"},
                {
                    "id": "3",
                    "rewardSetID": "7",
                    "eventIDs": "71",
                    "rankID": "21",
                    "needsSeasonPass": "1",
                    "rewardIDs": "4",
                },
            ],
        }
        data = GameData.parse("790.06", items)
        league = KingdomsLeagueEvent(event_id=601, reward_set_id=KingdomsLeagueRewardSetId(7), league_type_id=1)
        rank = KingdomsLeagueRankId(21)

        # getPromotionRewards returns the first row that matches
        assert [c.amount for c in league.promotion_rewards(rank, game_data=data)] == [2]
        assert [c.amount for c in league.promotion_rewards(rank, season_pass=True, game_data=data)] == [4]
        assert league.promotion_rewards(KingdomsLeagueRankId(1), game_data=data) == ()
        # getSeasonEventRewards adds up every row that matches
        assert [c.amount for c in league.event_rewards(ids.Event.WAR_OF_THE_REALMS, rank, game_data=data)] == [
            1,
            2,
            3,
        ]
        assert [
            c.amount
            for c in league.event_rewards(ids.Event.BATTLE_FOR_BERIMOND, rank, season_pass=True, game_data=data)
        ] == []


class TestDivisionRounds:
    def test_events_find_their_division_round(self, data):
        raid = RiftRaidEvent(event_id=133, division_round_id=DivisionRoundId(-11))
        tournament = GrandTournamentEvent(event_id=129, division_round_id=DivisionRoundId(1))
        assert raid.division_round(game_data=data) is data.division_rounds[DivisionRoundId(-11)]
        assert tournament.division_round(game_data=data) is data.division_rounds[DivisionRoundId(1)]
        assert RiftRaidEvent(event_id=133).division_round(game_data=data) is None


class TestRiftRaidStatus:
    def test_the_raid_status_names_its_level_and_stage(self, data):
        status = RiftRaidStatus.model_validate({"BID": 3, "BLID": "60", "HP": 25, "RUP": 0, "BS": 396})
        assert status.level(game_data=data) is data.raid_boss_levels[RaidBossLevelId(60)]
        assert status.stage(game_data=data) is data.raid_boss_stages[RaidBossStageId(396)]
        assert RiftRaidStatus.model_validate({}).level(game_data=data) is None
