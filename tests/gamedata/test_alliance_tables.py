"""The alliance and Beyond the Horizon tables, whole, from items v790.06, and their lookups against the client's own
code run in node (tests/data/alliance_tables_client.json)."""

import json
import logging
from pathlib import Path

import pytest

from empire_core.alliance.models.diplomacy import AllianceDonation
from empire_core.alliance.models.info import AllianceInfo
from empire_core.enums import AllianceRank, AllianceRight, CollectableKind, HelpType, HorizonPhaseTriggerType
from empire_core.events.status_models import GrandTournamentQuestSlot
from empire_core.gamedata import (
    AllianceTowerId,
    AllianceTreasuryDonatableId,
    GameData,
    GrandTournamentQuestId,
    HorizonDungeonId,
    HorizonPhaseTriggerId,
    HorizonRankRewardId,
    HorizonRewardSetId,
    HorizonScoringId,
    QuestId,
    RewardId,
)
from empire_core.gamedata.tables_alliance import AllianceGloryLevelDef, AllianceHelpRequestDef, AllianceTowerDef

DATA = Path(__file__).parents[1] / "data"
ITEMS = json.loads((DATA / "items_v790.06_alliance.json").read_text())
CLIENT = json.loads((DATA / "alliance_tables_client.json").read_text())

TABLES = {
    "alliance_ranks": "allianceranks",
    "alliance_rights": "alliancerankrights",
    "alliance_glory_levels": "alliancefameranks",
    "alliance_help_requests": "alliancehelprequests",
    "grand_tournament_quests": "allianceQuests",
    "alliance_forge_levels": "allianceForges",
    "alliance_treasury_donatables": "allianceFundsDonatables",
    "alliance_towers": "allianceTowers",
    "alliance_tower_effect_activations": "allianceTowerEffectsActivations",
    "horizon_dungeons": "allianceBattleGroundDungeons",
    "horizon_phase_triggers": "allianceBattleGroundPhaseTriggers",
    "horizon_rank_rewards": "allianceBattleGroundRankRewards",
}


@pytest.fixture(scope="module")
def data() -> GameData:
    return GameData.parse("790.06", ITEMS)


@pytest.mark.parametrize(("attribute", "items_table"), TABLES.items())
def test_every_row_is_read(data, caplog, attribute, items_table):
    with caplog.at_level(logging.WARNING):
        table = getattr(data, attribute)
        assert len(table) == len(ITEMS[items_table])
    assert caplog.records == []


def test_the_tables_survive_the_cache(data, tmp_path):
    data._write_cache(tmp_path / "cache.json")

    again = GameData._read_cache(tmp_path / "cache.json", "790.06")

    assert again is not None
    for attribute in TABLES:
        assert dict(getattr(again, attribute)) == dict(getattr(data, attribute))
    assert again.alliance_glory_levels[2].rewards == data.alliance_glory_levels[2].rewards


def test_ranks_and_rights(data):
    assert data.alliance_ranks[AllianceRank.LEADER].rerank_right is AllianceRight.NEW_LEADER
    assert data.alliance_rights[AllianceRight.KICK_MEMBER].needed_rank is AllianceRank.SERGEANT
    assert data.alliance_rights[17].needed_rank is AllianceRank.LEADER


def test_rights_and_reranks_match_the_client(data):
    rights = [[rank, right] for rank in range(10) for right in range(19) if data.alliance_rank_has_right(rank, right)]
    reranks = [
        [rank, target] for rank in range(10) for target in range(10) if data.alliance_rank_may_rerank(rank, target)
    ]

    assert rights == CLIENT["rights"]
    assert reranks == CLIENT["reranks"]


def test_unknown_rights_and_ranks_are_refused():
    data = GameData.parse("790.06", {"allianceranks": [{"rankID": "1", "rerankRight": "99"}]})

    assert not data.alliance_rank_has_right(AllianceRank.LEADER, AllianceRight.RENAME)
    assert not data.alliance_rank_may_rerank(AllianceRank.LEADER, AllianceRank.COLEADER)
    assert not data.alliance_rank_may_rerank(AllianceRank.LEADER, AllianceRank.MEMBER)


def test_glory_levels_match_the_client(data):
    assert [[points, data.alliance_glory_level(points)] for points, _ in CLIENT["glory"]] == CLIENT["glory"]
    assert [[level, data.alliance_glory_points_for_level(level)] for level, _ in CLIENT["gloryPoints"]] == CLIENT[
        "gloryPoints"
    ]


def test_glory_level_rewards_leave_out_nothing_and_unreadable_amounts():
    level_1 = AllianceGloryLevelDef.model_validate({"fameLevel": "1", "threshold": "0", "wood": "0", "stone": "0"})
    level_2 = AllianceGloryLevelDef.model_validate(
        {"fameLevel": "2", "threshold": "8000", "wood": "750", "currency1": "x", "currency2": "300"}
    )

    assert level_1.rewards == ()
    assert [(reward.kind, reward.key, reward.amount) for reward in level_2.rewards] == [
        (CollectableKind.WOOD, "W", 750),
        (CollectableKind.RUBIES, "C2", 300),
    ]


def test_a_glory_level_without_a_threshold_is_left_out(caplog):
    data = GameData.parse("790.06", {"alliancefameranks": [{"fameLevel": "1", "threshold": ""}]})

    with caplog.at_level(logging.WARNING):
        assert len(data.alliance_glory_levels) == 0
    assert "alliance_glory_levels row 1" in caplog.text


def test_help_requests_read_their_reductions_for_their_kind_only(data):
    assert data.alliance_help_requests[HelpType.LOOP_RECRUIT].max_helpers == 20
    heal = data.alliance_help_requests[HelpType.HEAL_UNIT]
    assert (heal.max_helpers, heal.heal_time_reduction, heal.build_time_reduction_seconds) == (5, 20, None)
    assert data.alliance_help_requests[HelpType.BUILD].build_time_reduction_seconds == 300

    recruit = AllianceHelpRequestDef.model_validate(
        {"allianceHelpRequestID": "1", "maxHelpersCount": "3", "unitHealTimeReduction": "20"}
    )
    assert recruit.heal_time_reduction is None


def test_grand_tournament_quests(data):
    quest = data.grand_tournament_quests[GrandTournamentQuestId(1)]

    assert (quest.quest, quest.quest_type, quest.duration_seconds) == (
        QuestId.SPEND_CURRENCY1,
        "SpendCurrenciesOrResources",
        3600,
    )
    assert (quest.reward_points, quest.cancel_cost_rubies, quest.event_id) == (50, 199, -1)


def test_grand_tournament_quest_defaults():
    quest = GameData.parse(
        "790.06", {"allianceQuests": [{"allianceQuestID": "7", "questType": "x"}]}
    ).grand_tournament_quests[GrandTournamentQuestId(7)]

    assert (quest.quest, quest.cancel_cost_rubies, quest.event_id, quest.quest_type) == (-1, 199, -1, "X")


def test_a_grand_tournament_quest_without_a_type_is_left_out(caplog):
    data = GameData.parse("790.06", {"allianceQuests": [{"allianceQuestID": "7", "questType": ""}]})

    with caplog.at_level(logging.WARNING):
        assert len(data.grand_tournament_quests) == 0
    assert "grand_tournament_quests row 7" in caplog.text


def test_forge_levels_and_treasury_donatables(data):
    assert data.alliance_forge_levels[1].forging_cost_coins == 23
    wood = data.alliance_treasury_donatables[AllianceTreasuryDonatableId(1)]
    assert (wood.resource_id, wood.currency_id, wood.directly_by_player) == (3, -1, True)
    doubloon = data.alliance_treasury_donatables[AllianceTreasuryDonatableId(9)]
    assert (doubloon.resource_id, doubloon.currency_id, doubloon.directly_by_player) == (-1, 33, False)


def test_alliance_donation_offers_the_donatables_members_may_give(data):
    by_player = [row for row in data.alliance_treasury_donatables.values() if row.directly_by_player]

    assert len(AllianceDonation.model_fields) == len(by_player)


def test_forge_levels_keep_the_last_row_of_a_level_as_the_client_does():
    data = GameData.parse(
        "790.06",
        {
            "allianceForges": [
                {"allianceForgeID": "1", "level": "1", "forgingCostC1": "23"},
                {"allianceForgeID": "2", "level": "1", "forgingCostC1": "65"},
            ]
        },
    )

    assert data.alliance_forge_levels[1].forging_cost_coins == 65


def test_tower_activation_costs_match_the_client(data):
    assert [
        [seconds, data.alliance_tower_effect_activation_cost(seconds)] for seconds, _ in CLIENT["activation"]
    ] == CLIENT["activation"]


def test_towers_match_the_client(data):
    def tower_id(victories: int) -> int | None:
        tower = data.alliance_tower_by_victories(victories)
        return tower.tower_id if tower is not None else None

    assert [[victories, tower_id(victories)] for victories, _ in CLIENT["towers"]] == CLIENT["towers"]
    assert data.alliance_tower_by_level(3) == data.alliance_towers[AllianceTowerId(3)]
    assert data.alliance_tower_by_level(6) is None


def test_no_tower_below_the_first_row_s_victories():
    data = GameData.parse("790.06", {"allianceTowers": [{"allianceTowerID": "1", "countVictory": "10"}]})

    assert data.alliance_tower_by_victories(9) is None
    assert data.alliance_tower_by_victories(10) == data.alliance_towers[AllianceTowerId(1)]


def test_tower_points_to_loot():
    tower = AllianceTowerDef.model_validate(
        {"allianceTowerID": "3", "addStatuette": "5", "defeatedPVPBasePoints": "5", "allianceTowerLevelMultiplier": "8"}
    )

    assert tower.points_to_loot(0) == 5
    assert tower.points_to_loot(2) == (5 + 5 * 4) * 8
    assert tower.points_to_loot(32) == 5 * 8
    assert tower.points_to_loot(-1) == 5 * 8
    assert tower.points_to_loot(31) == (5 + 5 * -(2**31)) * 8
    assert tower.points_to_loot(5000) == 5 * 8


def test_robber_barons_match_the_client(data):
    def dungeon_id(row) -> int | None:
        return row.dungeon_id if row is not None else None

    assert [
        [scoring, data.horizon_dungeon_max_level(HorizonScoringId(scoring))] for scoring, _ in CLIENT["maxLevels"]
    ] == (CLIENT["maxLevels"])
    assert [
        [scoring, victories, dungeon_id(data.horizon_dungeon_by_victories(HorizonScoringId(scoring), victories))]
        for scoring, victories, _ in CLIENT["byVictory"]
    ] == CLIENT["byVictory"]
    assert [
        [scoring, level, dungeon_id(data.horizon_dungeon_by_level(HorizonScoringId(scoring), level))]
        for scoring, level, _ in CLIENT["byLevel"]
    ] == CLIENT["byLevel"]
    assert [
        [scoring, victories, seconds, data.horizon_dungeon_skip_cost(HorizonScoringId(scoring), victories, seconds)]
        for scoring, victories, seconds, _ in CLIENT["skip"]
    ] == CLIENT["skip"]


def test_robber_barons_of_a_scoring_without_rows(data):
    assert data.horizon_dungeon_by_victories(HorizonScoringId(99), 0) is None
    assert data.horizon_dungeon_by_level(HorizonScoringId(99), 1) is None
    assert data.horizon_dungeon_skip_cost(HorizonScoringId(99), 0, 60) is None
    assert data.horizon_dungeons[HorizonDungeonId(1)].cooldown_seconds == 10800


def test_phase_triggers(data):
    timer = data.horizon_phase_triggers[HorizonPhaseTriggerId(1)]
    citadel = data.horizon_phase_triggers[HorizonPhaseTriggerId(2)]

    assert (timer.trigger_type, timer.timer_offset_seconds, timer.has_warning_lead_time) == (
        HorizonPhaseTriggerType.TIMER,
        172800,
        True,
    )
    assert (citadel.trigger_type, citadel.citadel_level, citadel.alliance_share, citadel.min_alliances) == (
        HorizonPhaseTriggerType.CITADEL_CONDITION,
        4,
        85,
        50,
    )
    bare = GameData.parse("790.06", {"allianceBattleGroundPhaseTriggers": [{"phaseTriggerID": "3"}]})
    assert not bare.horizon_phase_triggers[HorizonPhaseTriggerId(3)].has_warning_lead_time


def test_rank_rewards(data):
    reward = data.horizon_rank_rewards[HorizonRankRewardId(1)]
    rewards = data.horizon_rank_rewards_of_set(HorizonRewardSetId(1))

    assert (reward.reward_set_id, reward.reward_id, reward.rank, reward.participation_points) == (
        1,
        RewardId(5133),
        1000,
        0,
    )
    assert rewards[0] == reward
    assert {row.reward_set_id for row in rewards} == {1}
    assert sum(len(data.horizon_rank_rewards_of_set(HorizonRewardSetId(s))) for s in range(10)) == len(
        ITEMS["allianceBattleGroundRankRewards"]
    )


def test_columns_the_current_items_leave_empty():
    data = GameData.parse(
        "790.06",
        {
            "allianceBattleGroundRankRewards": [
                {
                    "allianceBattleGroundRankRewardID": "1",
                    "rewardSetID": "2",
                    "rewardID": "7",
                    "participationPoints": "500",
                }
            ],
            "allianceBattleGroundPhaseTriggers": [{"phaseTriggerID": "2", "type": "2", "warningShare": "70"}],
            "allianceFundsDonatables": [
                {"allianceFundsDonatableID": "1"},
                {"allianceFundsDonatableID": "2", "directlyByPlayer": "0"},
                {"allianceFundsDonatableID": "3", "directlyByPlayer": "1"},
            ],
        },
    )

    reward = data.horizon_rank_rewards[HorizonRankRewardId(1)]
    assert (reward.reward_set_id, reward.reward_id, reward.rank, reward.participation_points) == (2, 7, 0, 500)
    assert data.horizon_phase_triggers[HorizonPhaseTriggerId(2)].warning_share == 70
    assert [row.directly_by_player for row in data.alliance_treasury_donatables.values()] == [False, False, True]


def test_an_alliance_reads_its_glory_levels(data):
    alliance = AllianceInfo.model_validate({"AID": 1, "CF": "34000", "HF": 7999})

    assert alliance.glory_level(game_data=data) == 3
    assert alliance.highest_glory_level(game_data=data) == 1
    assert AllianceInfo.model_validate({"AID": 1, "CF": 10**19}).glory_level(game_data=data) == 50


def test_grand_tournament_quest_slots_name_their_quest():
    slot = GrandTournamentQuestSlot.model_validate({"slot_id": 0, "QID": "12", "PID": -1, "RS": 0})

    assert slot.alliance_quest_id == GrandTournamentQuestId(12)
