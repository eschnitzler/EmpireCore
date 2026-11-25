"""The special server and season tables, read as the client reads them."""

import json
import logging
import os
from pathlib import Path

import pytest

from empire_core.enums import CollectableKind, DivisionRoundType
from empire_core.gamedata import (
    DaimyoEndRewardId,
    DivisionRoundDef,
    DivisionRoundId,
    GameData,
    IsleId,
    KingdomsLeagueEndRewardDef,
    KingdomsLeagueEventRewardDef,
    KingdomsLeagueMedalId,
    KingdomsLeagueRankId,
    KingdomsLeagueSettingDef,
    KingdomsLeagueSettingId,
    OuterRealmsRankId,
    OuterRealmsRankRewardDef,
    OuterRealmsRankRewardId,
    RaidBossLevelDef,
    RaidBossLevelId,
    RaidBossStageId,
    StormIslandsAllianceRewardId,
    StormIslandsPlayerRewardId,
    StormIslandsRewardSetId,
    StormIsleDef,
    ids,
)

# Rows of items v790.06, each table's first and last rows and the rows the tests look up
ITEMS = {
    "tempServerSettings": [{"settingID": "24", "rewardSetID": "14"}],
    "tempServerRankPoints": [
        {"tempServerRankID": "1", "eventID": "106", "minRank": "50000", "maxRank": "45001", "rankPoints": "9000"},
        {"tempServerRankID": "2", "eventID": "106", "minRank": "45000", "maxRank": "40001", "rankPoints": "10000"},
        {"tempServerRankID": "47", "eventID": "106", "minRank": "1", "maxRank": "1", "rankPoints": "110000"},
    ],
    "tempServerRankRewards": [
        {
            "tempServerRankRewardID": "73",
            "tempServerRankID": "1",
            "eventID": "106",
            "rank": "50000",
            "rewardID": "661",
            "rewardSetID": "4",
        },
        {
            "tempServerRankRewardID": "516",
            "tempServerRankID": "47",
            "eventID": "106",
            "rank": "1",
            "rewardID": "10927",
            "rewardSetID": "14",
        },
    ],
    "tempServerDailyTaskRewards": [
        {"tempServerDailyTaskRewardID": "1", "minDailyTaskPointsPerDay": "5", "rewardID": "10928"},
        {"tempServerDailyTaskRewardID": "5", "minDailyTaskPointsPerDay": "40", "rewardID": "10932"},
    ],
    "isles": [
        {
            "IsleID": "1",
            "type": "VILLAGEWOOD",
            "maxCountVictories": "10",
            "countVictories": "90#91#92#93#94#95#96#97#98#99",
            "dungeonlevel": "70",
            "guards": "15",
            "wallBonus": "100",
            "gateBonus": "100",
            "moatBonus": "20",
            "wallLevel": "5",
            "gateLevel": "5",
            "moatLevel": "1",
            "towerLevel": "5",
            "fixedLootWood": "40000",
            "globalCooldown": "259200",
            "occupationTime": "28800",
        },
        {
            "IsleID": "14",
            "type": "DUNGEON",
            "maxCountVictories": "10",
            "dungeonlevel": "80",
            "wallBonus": "100",
            "gateBonus": "100",
            "moatBonus": "30",
            "lootWood": "442",
            "lootStone": "442",
            "lootFood": "767",
            "lootAquamarine": "6192",
            "lootCargoPoints": "180",
        },
    ],
    "islandrewardranks": [
        {"islandRewardRankID": "0", "cargoPointRequirement": "5000", "rewardIDs": "126", "islandRewardSetID": "0"},
        {"islandRewardRankID": "13", "topXValue": "5", "rewardIDs": "6793,6794", "islandRewardSetID": "2"},
    ],
    "islandPlayerRewards": [
        {"islandPlayerRewardID": "0", "cargoPointRequirement": "90000", "rewardIDs": "5965", "islandRewardSetID": "0"},
        {"islandPlayerRewardID": "7", "cargoPointRequirement": "100000", "rewardIDs": "6807", "islandRewardSetID": "2"},
    ],
    "seasonSettings": [
        {
            "settingID": "1",
            "seasonPassPromotionPrice": "809",
            "seasonPassEventEndPrice": "1620",
            "seasonPassFullDiscount": "25",
            "seasonPassSingleDiscount": "10",
        }
    ],
    "seasonRanks": [
        {"rankID": "1", "minMedalPointsForUnlock": "0", "majorRank": "1", "minorRank": "0"},
        {"rankID": "21", "minMedalPointsForUnlock": "2000", "majorRank": "6", "minorRank": "0"},
    ],
    "seasonMedals": [
        {"medalID": "1", "type": "goldMedal", "minHighscoreRank": "1", "medalPoints": "1000"},
        {"medalID": "7", "type": "woodMedal", "minHighscoreRank": "7", "medalPoints": "100"},
    ],
    "seasonEndRewards": [
        {"id": "1", "rewardSetID": "1", "minHighscoreRank": "1", "rewardIDs": "30374,30375,30376,30377"},
        {"id": "161", "leaguetypeID": "2", "rewardSetID": "7", "minHighscoreRank": "1", "rewardIDs": "32371"},
        {"id": "192", "leaguetypeID": "1", "rewardSetID": "7", "minHighscoreRank": "10001", "rewardIDs": "32402"},
    ],
    "seasonEventRewards": [
        {"id": "1", "rewardSetID": "1", "eventIDs": "72", "rankID": "1", "rewardIDs": "30080,30081"},
        {"id": "797", "rewardSetID": "7", "eventIDs": "3,71,72,80,85,103", "rankID": "21", "rewardIDs": "32643,32644"},
        {
            "id": "798",
            "rewardSetID": "7",
            "eventIDs": "3,71,72,80,85,103",
            "rankID": "21",
            "needsSeasonPass": "1",
            "rewardIDs": "32645,32646",
        },
    ],
    "seasonPromotionRewards": [
        {"id": "1", "rewardSetID": "1", "rankID": "2", "rewardIDs": "30000,30001"},
        {"id": "439", "leaguetypeID": "2", "rewardSetID": "7", "rankID": "21", "rewardIDs": "32479,32480"},
        {"id": "479", "leaguetypeID": "1", "rewardSetID": "7", "rankID": "21", "rewardIDs": "32559,32560"},
        {
            "id": "480",
            "leaguetypeID": "1",
            "rewardSetID": "7",
            "rankID": "21",
            "needsSeasonPass": "1",
            "rewardIDs": "32561,32562",
        },
    ],
    "daimyoEndRewards": [
        {"id": "1", "rewardSetID": "1", "minHighscoreRank": "1", "rewardIDs": "29900,29901"},
        {"id": "168", "rewardSetID": "12", "minHighscoreRank": "2501", "rewardIDs": "29926,29927"},
    ],
    "divisionRounds": [
        {
            "divisionRoundID": "1",
            "comment1": "Initial event run setup",
            "eventID": "129",
            "type": "qualification",
            "divisions": "1",
            "subdivisions": "48",
            "promotes": "0,1200,480,80,48",
            "targetDivisionRoundID": "2",
        },
        {
            "divisionRoundID": "-11",
            "comment1": "QA Testing Values",
            "eventID": "133",
            "type": "normal",
            "divisions": "6",
            "subdivisions": "4,4,4,2,2,1",
            "subdivisionSizes": "0,50,30,16,8,5",
            "promotes": "8,4,2,2,1,0",
            "demotes": "0,8,4,4,2,2",
            "testonly": "1",
        },
    ],
    "raidBossLevels": [
        {
            "raidBossLevelID": "60",
            "raidBossID": "3",
            "level": "20",
            "wallRegenerationTime": "600",
            "courtyardReserveUnits": "785+2000000#786+1500000#787+6500000#788+2000000#783+3300000#784+6000000",
            "courtyardMeleePercent": "30",
            "courtyardSize": "75000",
            "rewardIDs": "9936",
            "minPointsForBossRewards": "8130",
            "lootBoxTombolaID": "109",
        }
    ],
    "raidBossStages": [
        {
            "raidBossStageID": "396",
            "raidBossLevelID": "60",
            "health": "25",
            "defenderStageEffects": "444&1",
            "defenderBattleEffects": "445&20000,446&25000,509&25000,510&30000,501&3500",
            "defenderPostBattleEffects": "488&785+20,488&786+10,488&787+5",
            "defenderWallRegenerationEffects": "487&785+8000000",
            "leftWallUnits": "783+20000#784+20000#787+10000",
            "courtyardPointFactor": "9035",
            "wallPointFactor": "4518",
            "generalID": "136",
            "HighlightEffectIcon": "444,487,488",
        },
        {
            "raidBossStageID": "390",
            "raidBossLevelID": "60",
            "health": "100",
            "attackerBattleEffects": "432&-30",
            "attackerPostBattleEffects": "434&5,436&2.5",
            "generalID": "134",
            "HighlightEffectIcon": "487,488",
        },
    ],
    "rewards": [
        {"rewardID": "126", "grantType": "1", "currency1": "250000", "currency2": "25000"},
        {"rewardID": "661", "units": "9+500#10+500"},
        {"rewardID": "9936", "lootBox": "46+1", "grantType": "2"},
        {"rewardID": "10928", "currency1": "100"},
        {"rewardID": "10932", "currency1": "200", "currency2": "5"},
    ],
}


@pytest.fixture
def data() -> GameData:
    return GameData.parse("790.06", ITEMS)


class TestOuterRealms:
    def test_rank_points_bands(self, data):
        band = data.outer_realms_rank_points[OuterRealmsRankId(1)]
        assert (band.min_rank, band.max_rank, band.rank_points) == (50000, 45001, 9000)
        assert band.covers(45001) and band.covers(50000) and not band.covers(45000)

    def test_rank_rewards_are_keyed_by_their_own_id(self, data):
        # the client keys nothing: tempServerRankID repeats once per reward set, so it cannot key the rows
        reward = data.outer_realms_rank_rewards[OuterRealmsRankRewardId(516)]
        assert (reward.rank_id, reward.rank, reward.reward_id, reward.reward_set_id) == (47, 1, 10927, 14)
        assert not reward.uses_points and reward.gives_reward

    def test_a_points_reward_and_a_rank_overriding_points(self):
        # CastleTempServerRewardVO.parseXML: participationPoints above 0 makes a points reward, a rank above 0 wins
        points = OuterRealmsRankRewardDef.model_validate({"tempServerRankRewardID": "1", "participationPoints": "500"})
        both = OuterRealmsRankRewardDef.model_validate(
            {"tempServerRankRewardID": "2", "participationPoints": "500", "rank": "3"}
        )
        neither = OuterRealmsRankRewardDef.model_validate({"tempServerRankRewardID": "3"})
        assert points.uses_points and not both.uses_points
        assert not neither.gives_reward and (neither.rank_id, neither.reward_set_id) == (0, 0)

    def test_rank_reward_rewards(self, data):
        units = data.outer_realms_rank_rewards[OuterRealmsRankRewardId(73)].rewards(game_data=data)
        assert [(c.item, c.amount) for c in units] == [
            (ids.Unit.ELITE_RANKREWARDMELEE, 500),
            (ids.Unit.ELITE_RANKREWARDRANGE, 500),
        ]


class TestStormIslands:
    def test_isles(self, data):
        village = data.storm_isles[IsleId(1)]
        assert village.is_village and village.isle_type == "VILLAGEWOOD"
        assert (village.dungeon_level, village.occupation_seconds, village.fixed_loot_wood, village.loot_wood) == (
            70,
            28800,
            40000,
            -1,
        )
        assert (village.wall_level, village.gate_level, village.moat_level, village.tower_level) == (5, 5, 1, 5)
        dungeon = data.storm_isles[IsleId(14)]
        assert not dungeon.is_village
        assert (dungeon.loot_aquamarine, dungeon.occupation_seconds, dungeon.wall_level) == (6192, 0, 0)

    def test_a_bare_isle_takes_the_client_defaults(self):
        isle = StormIsleDef.model_validate({"IsleID": "3"})
        assert (isle.isle_type, isle.max_victories, isle.fixed_loot_aquamarine, isle.wall_bonus) == (
            "UNKNOWN",
            -1,
            -1,
            0,
        )

    def test_rewards_keep_row_zero_and_filter_reward_ids(self, data):
        first = data.storm_islands_alliance_rewards[StormIslandsAllianceRewardId(0)]
        assert (first.cargo_points_needed, first.top_x, first.reward_set_id) == (5000, -1, StormIslandsRewardSetId(0))
        assert not first.is_top_x_reward
        coins = first.rewards(game_data=data)
        assert [(c.kind, c.amount) for c in coins] == [(CollectableKind.COINS, 250000), (CollectableKind.RUBIES, 25000)]
        top = data.storm_islands_alliance_rewards[StormIslandsAllianceRewardId(13)]
        assert top.is_top_x_reward and top.reward_ids == (6793, 6794)
        player = data.storm_islands_player_rewards[StormIslandsPlayerRewardId(7)]
        assert (player.cargo_points_needed, player.reward_ids, player.reward_set_id) == (100000, (6807,), 2)

        # createListFromRewardIdsString keeps only the parts whose parseInt is above 0
        row = {"islandPlayerRewardID": "1", "rewardIDs": "0,-3,x,12"}
        data = GameData.parse("790.06", {"islandPlayerRewards": [row]})
        assert data.storm_islands_player_rewards[StormIslandsPlayerRewardId(1)].reward_ids == (12,)
        assert data.storm_islands_player_rewards[StormIslandsPlayerRewardId(1)].reward_set_id == -1


class TestKingdomsLeague:
    def test_settings_ranks_and_medals(self, data):
        setting = data.kingdoms_league_settings[KingdomsLeagueSettingId(1)]
        assert (setting.promotion_pass_price, setting.event_end_pass_price) == (809, 1620)
        assert (setting.event_pass_sale_price, setting.promotion_pass_sale_price) == (1458, 729)
        rank = data.kingdoms_league_ranks[KingdomsLeagueRankId(21)]
        assert (rank.min_medal_points, rank.major_rank, rank.minor_rank, rank.text_id) == (
            2000,
            6,
            0,
            "seasonLeague_rank_21",
        )
        gold = data.kingdoms_league_medals[KingdomsLeagueMedalId(1)]
        assert (gold.medal_type, gold.min_highscore_rank, gold.medal_points) == ("goldMedal", 1, 1000)

    def test_int_attributes_default_and_read_nan_as_zero(self):
        # int(getIntAttribute(key, row, -1)): missing is the default, no number is int(NaN), 0
        bare = KingdomsLeagueEventRewardDef.model_validate({"id": "1"})
        assert (bare.reward_set_id, bare.rank_id, bare.needs_season_pass, bare.event_ids) == (-1, -1, False, ())
        odd = KingdomsLeagueEventRewardDef.model_validate({"id": "1", "rankID": "x", "needsSeasonPass": "0"})
        assert (odd.rank_id, odd.needs_season_pass) == (0, False)
        setting = KingdomsLeagueSettingDef.model_validate({"settingID": "1"})
        assert (setting.promotion_pass_price, setting.event_pass_sale_price) == (0, 0)
        assert KingdomsLeagueEndRewardDef.model_validate({"id": "1"}).league_type_id == 0


class TestDaimyoAndDivisions:
    def test_daimyo_end_rewards(self, data):
        band = data.daimyo_end_rewards[DaimyoEndRewardId(168)]
        assert (band.reward_set_id, band.min_highscore_rank, band.reward_ids) == (12, 2501, (29926, 29927))

    def test_division_rounds_keep_the_negative_test_round(self, data):
        qualification = data.division_rounds[DivisionRoundId(1)]
        assert qualification.round_type is DivisionRoundType.QUALIFICATION
        assert (qualification.divisions, qualification.subdivisions, qualification.demotes) == (1, (48,), ())
        test_round = data.division_rounds[DivisionRoundId(-11)]
        assert test_round.round_type is DivisionRoundType.NORMAL
        assert test_round.subdivision_sizes == (0, 50, 30, 16, 8, 5)
        assert (test_round.promotes_for_division(1), test_round.promotes_for_division(7)) == (8, 0)
        assert (test_round.demotes_for_division(2), test_round.demotes_for_division(7)) == (8, 0)
        assert test_round.total_promotes == 17
        with pytest.raises(ValueError, match="below 1"):
            test_round.demotes_for_division(0)

    def test_qualification_division_matches_the_client(self, data):
        # expectations from getQualificationNewDivison run in node on the same promotes
        qualification = data.division_rounds[DivisionRoundId(1)]
        ranks = [-5, 0, 1, 47, 48, 49, 128, 129, 608, 609, 1808, 1809, 5000]
        assert [qualification.qualification_division(r) for r in ranks] == [1, 1, 5, 5, 5, 4, 4, 3, 3, 2, 2, 1, 1]
        test_round = data.division_rounds[DivisionRoundId(-11)]
        ranks = [0, 1, 2, 3, 5, 6, 9, 10, 17, 18]
        assert [test_round.qualification_division(r) for r in ranks] == [1, 5, 4, 4, 3, 2, 2, 1, 1, 1]

    def test_an_unknown_round_type_is_kept_as_text(self):
        assert DivisionRoundDef.model_validate({"divisionRoundID": "3", "type": "playoff"}).round_type == "playoff"
        assert DivisionRoundDef.model_validate({"divisionRoundID": "3"}).divisions == -1


class TestRaidBoss:
    def test_levels_read_their_courtyard_and_rewards(self, data):
        level = data.raid_boss_levels[RaidBossLevelId(60)]
        assert (level.raid_boss_id, level.level, level.wall_regeneration_seconds) == (
            ids.RaidBoss.LEGENDARY_DRAGON,
            20,
            600,
        )
        # the client reads courtyardMeleeRatio, which the items name courtyardMeleePercent
        assert (level.courtyard_melee_ratio, level.courtyard_size, level.min_points_for_boss_rewards) == (
            0,
            75000,
            8130,
        )
        assert level.courtyard_reserve_units[0] == (ids.Unit.ARE_LEGENDARY_DRAGON_EGG_L0, 2000000)
        assert len(level.courtyard_reserve_units) == 6
        assert [c.kind for c in level.rewards(game_data=data)] == [CollectableKind.LOOT_BOX]

    def test_a_ratio_is_read_with_parse_float(self):
        level = RaidBossLevelDef.model_validate({"raidBossLevelID": "1", "courtyardMeleeRatio": "0.7x"})
        assert level.courtyard_melee_ratio == 0.7
        assert (
            RaidBossLevelDef.model_validate({"raidBossLevelID": "1", "courtyardMeleeRatio": "x"}).courtyard_melee_ratio
            == 0
        )

    def test_stages_read_their_effects(self, data):
        stage = data.raid_boss_stages[RaidBossStageId(396)]
        assert (stage.raid_boss_level_id, stage.health, stage.general_id) == (60, 25, ids.General.RAID_BOSS3_LOW)
        assert [(e.effect_id, e.values) for e in stage.defender_post_battle_effects] == [
            (ids.Effect.MUTATE_RESERVE_UNIT_LEGENDARY_DRAGON, ((785, 20),)),
            (ids.Effect.MUTATE_RESERVE_UNIT_LEGENDARY_DRAGON, ((786, 10),)),
            (ids.Effect.MUTATE_RESERVE_UNIT_LEGENDARY_DRAGON, ((787, 5),)),
        ]
        assert stage.defender_wall_regeneration_effects[0].values == ((785, 8000000),)
        assert stage.highlighted_effects == (
            ids.Effect.RAID_BOSS_WALL_REGENERATION,
            ids.Effect.SPAWN_RESERVE_UNIT_LEGENDARY_DRAGON,
            ids.Effect.MUTATE_RESERVE_UNIT_LEGENDARY_DRAGON,
        )
        assert (stage.courtyard_point_factor, stage.wall_point_factor) == (9035, 4518)
        first = data.raid_boss_stages[RaidBossStageId(390)]
        assert [(e.effect_id, e.value) for e in first.attacker_post_battle_effects] == [
            (ids.Effect.INFECTION_RATE_BASE_BONUS, 5),
            (ids.Effect.INFECTION_RATE_RANGE_BONUS, 2.5),
        ]

    def test_a_level_lists_its_stages_healthiest_first(self, data):
        level = data.raid_boss_levels[RaidBossLevelId(60)]
        assert [stage.raid_boss_stage_id for stage in level.stages(game_data=data)] == [390, 396]


def test_every_table_survives_the_cache(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        data = GameData.parse("790.06", ITEMS)
        data._write_cache(tmp_path / "cache.json")
        again = GameData._read_cache(tmp_path / "cache.json", "790.06")

    assert again is not None
    assert (
        again.outer_realms_rank_rewards[OuterRealmsRankRewardId(516)]
        == data.outer_realms_rank_rewards[OuterRealmsRankRewardId(516)]
    )
    assert again.raid_boss_stages[RaidBossStageId(396)] == data.raid_boss_stages[RaidBossStageId(396)]
    assert again.kingdoms_league_promotion_rewards.keys() == data.kingdoms_league_promotion_rewards.keys()
    assert again.storm_isles[IsleId(1)] == data.storm_isles[IsleId(1)]
    assert again.division_rounds[DivisionRoundId(-11)] == data.division_rounds[DivisionRoundId(-11)]
    assert (len(again.outer_realms_rank_points), len(again.daimyo_end_rewards)) == (3, 2)
    assert not caplog.records


TABLES = {
    "outer_realms_rank_points": "tempServerRankPoints",
    "outer_realms_rank_rewards": "tempServerRankRewards",
    "outer_realms_daily_task_rewards": "tempServerDailyTaskRewards",
    "storm_isles": "isles",
    "storm_islands_alliance_rewards": "islandrewardranks",
    "storm_islands_player_rewards": "islandPlayerRewards",
    "kingdoms_league_settings": "seasonSettings",
    "kingdoms_league_ranks": "seasonRanks",
    "kingdoms_league_medals": "seasonMedals",
    "kingdoms_league_end_rewards": "seasonEndRewards",
    "kingdoms_league_event_rewards": "seasonEventRewards",
    "kingdoms_league_promotion_rewards": "seasonPromotionRewards",
    "daimyo_end_rewards": "daimyoEndRewards",
    "division_rounds": "divisionRounds",
    "raid_boss_levels": "raidBossLevels",
    "raid_boss_stages": "raidBossStages",
}


def test_every_row_of_the_full_items_file_loads(caplog):
    # The full items file is ~20 MB and not in the repo; point EMPIRE_CORE_ITEMS_JSON at it.
    path = os.environ.get("EMPIRE_CORE_ITEMS_JSON")
    if not path:
        pytest.skip("EMPIRE_CORE_ITEMS_JSON is not set")
        return
    payload = json.loads(Path(path).read_text())
    with caplog.at_level(logging.WARNING):
        data = GameData.parse("full", payload)
        counts = {name: len(getattr(data, name)) for name in TABLES}

    assert counts == {name: len(payload.get(key, [])) for name, key in TABLES.items()}
    assert not caplog.records
