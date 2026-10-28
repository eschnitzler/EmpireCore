"""An event's reward sets resolve to the game-data rows that hold its rewards."""

from empire_core.enums import CollectableKind
from empire_core.events.models import BerimondEvent, ImperialPatronageEvent, MaraudersContestEvent, NobilityContestEvent
from empire_core.gamedata import (
    Event,
    GameData,
    LeaderboardRewardSetId,
    LeagueType,
    LeagueTypeEventDef,
    RewardId,
    RewardSetId,
    Unit,
)

MARAUDERS = int(Event.MARAUDERS_CONTEST)
DATA = GameData.parse(
    "test",
    {
        "rewards": [
            {"rewardID": "91", "units": "211+20"},
            {"rewardID": "92", "addC1": "500"},
            {"rewardID": "93", "units": "211+5"},
        ],
        # leaguetypeevents rows of items 788.03, cut down; 4 names a reward the items lack
        "leaguetypeevents": [
            {"leaguetypeEventsID": "1", "leaguetypeID": "1", "eventID": str(MARAUDERS), "rewardSetID": "1",
             "neededPointsForRewards": "75,300", "rewardIDs": "91,92#93,4", "topXValue": "20"},
            {"leaguetypeEventsID": "2", "leaguetypeID": "1", "eventID": str(MARAUDERS), "rewardSetID": "2",
             "neededPointsForRewards": "90", "rewardIDs": "93"},
            {"leaguetypeEventsID": "3", "leaguetypeID": "2", "eventID": "3", "subType": "1", "rewardSetID": "10",
             "rewardIDs": "92"},
            {"leaguetypeEventsID": "4", "leaguetypeID": "2", "eventID": "3", "subType": "0", "rewardSetID": "10",
             "rewardIDs": "93"},
        ],
        "leaderboardRewards": [
            {"leaderboardRewardID": "1", "eventTypeID": "123", "leaderboardRewardSetID": "1", "maxRank": "1",
             "rewardIDs": "91"},
            {"leaderboardRewardID": "2", "eventTypeID": "123", "leaderboardRewardSetID": "1", "maxRank": "3",
             "rewardIDs": "92", "leagueID": "2"},
            {"leaderboardRewardID": "3", "eventTypeID": "123", "leaderboardRewardSetID": "2", "maxRank": "1",
             "rewardIDs": "93"},
            {"leaderboardRewardID": "4", "eventTypeID": "60", "leaderboardRewardSetID": "1", "maxRank": "1",
             "rewardIDs": "93"},
        ],
    },
)  # fmt: skip


def _marauders(**entry: object) -> MaraudersContestEvent:
    event = MaraudersContestEvent.from_entry(MARAUDERS, {"RS": 600, **entry}, None, 0.0, {})
    assert isinstance(event, MaraudersContestEvent)
    return event


class TestLeagueRewards:
    def test_a_known_set_resolves_to_its_row_with_typed_rewards(self):
        event = _marauders(LID=1, RSID=1)

        row = event.league_rewards(game_data=DATA)

        assert row is not None and row.league_type_event_id == 1
        assert (row.event_id, row.league_type_id, row.reward_set_id) == (Event.MARAUDERS_CONTEST, LeagueType(1), 1)
        assert row.needed_points == (75, 300) and row.top_x == (20,)
        # createListsFromRewardIdsString: a list per "," part, a part's "#" pieces in one
        assert row.reward_ids == ((RewardId(91),), (RewardId(92), RewardId(93)), (RewardId(4),))
        first, second, missing = row.rewards(game_data=DATA)
        assert [(c.kind, c.item, c.amount) for c in first] == [(CollectableKind.UNITS, Unit.MEAD_RANGER_L6, 20)]
        assert type(first[0].item) is Unit
        assert [c.kind for c in second] == [CollectableKind.COINS, CollectableKind.UNITS]
        assert missing == ()

    def test_the_set_picks_among_the_leagues_rows(self):
        row = _marauders(LID=1, RSID=2).league_rewards(game_data=DATA)
        assert row is not None and row.league_type_event_id == 2

    def test_no_set_takes_the_first_row_of_the_league(self):
        # ALeagueTypeScoreEventVO: rewardSetId <= 0 matches any set
        row = _marauders(LID=1).league_rewards(game_data=DATA)
        assert row is not None and row.league_type_event_id == 1

    def test_an_unknown_set_or_league_resolves_to_none(self):
        assert _marauders(LID=1, RSID=99).league_rewards(game_data=DATA) is None
        assert _marauders(LID=7, RSID=1).league_rewards(game_data=DATA) is None
        assert _marauders(LID=1, RSID=1).league_rewards(game_data=GameData.parse("test", {})) is None

    def test_the_wire_field_keeps_the_set_id(self):
        event = _marauders(LID=1, RSID=2)
        assert event.reward_set_id == RewardSetId(2) and type(event.reward_set_id) is int

    def test_berimond_takes_the_last_row_of_its_league_and_set_of_any_sub_type(self):
        # FactionEventVO.parseData keys the leagues by league and set, a later row replacing an earlier one
        event = BerimondEvent.from_entry(3, {"LID": 2, "RSID": 10}, None, 0.0, {})
        assert isinstance(event, BerimondEvent)
        row = event.league_rewards(game_data=DATA)
        assert row is not None and row.league_type_event_id == 4

    def test_a_row_reads_from_the_lazy_table_by_its_id(self):
        assert isinstance(DATA.league_type_events[3], LeagueTypeEventDef)
        assert DATA.league_type_event(3, 2, sub_type=1, reward_set_id=10) is DATA.league_type_events[3]


class TestLeaderboardRewards:
    def test_an_events_set_gives_its_rank_bands(self):
        event = ImperialPatronageEvent.from_entry(123, {"LRSI": 1}, None, 0.0, {})
        assert isinstance(event, ImperialPatronageEvent)
        assert event.leaderboard_reward_set_id == LeaderboardRewardSetId(1)

        bands = event.leaderboard_rewards(game_data=DATA)

        assert [band.leaderboard_reward_id for band in bands] == [1, 2]
        assert [band.max_rank for band in bands] == [1, 3]
        assert bands[0].league_type_id == -1 and bands[1].league_type_id is LeagueType(2)
        assert [(c.item, c.amount) for c in bands[0].rewards(game_data=DATA)] == [(Unit.MEAD_RANGER_L6, 20)]

    def test_a_league_takes_only_its_own_bands(self):
        # getRewardListForDialogList: asked for a league, it skips every band of another, leagueID -1 too
        event = ImperialPatronageEvent.from_entry(123, {"LRSI": 1}, None, 0.0, {})
        assert isinstance(event, ImperialPatronageEvent)
        assert [band.leaderboard_reward_id for band in event.leaderboard_rewards(LeagueType(2), game_data=DATA)] == [2]

    def test_a_scored_event_reads_its_set_from_lrsi(self):
        event = NobilityContestEvent.from_entry(60, {"RS": 600, "LRSI": 1}, None, 0.0, {})
        assert isinstance(event, NobilityContestEvent)
        assert [band.leaderboard_reward_id for band in event.leaderboard_rewards(game_data=DATA)] == [4]

    def test_no_set_or_an_unknown_one_gives_no_bands(self):
        absent = ImperialPatronageEvent.from_entry(123, {}, None, 0.0, {})
        assert isinstance(absent, ImperialPatronageEvent)
        assert absent.leaderboard_reward_set_id is None
        assert absent.leaderboard_rewards(game_data=DATA) == ()
        unknown = ImperialPatronageEvent.from_entry(123, {"LRSI": 99}, None, 0.0, {})
        assert isinstance(unknown, ImperialPatronageEvent)
        assert unknown.leaderboard_rewards(game_data=DATA) == ()
