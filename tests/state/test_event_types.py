"""The event models added for the sei detail: each read as its client class reads its entry, and their pep and cqs."""

import threading
from typing import Any

import pytest

from empire_core.events import (
    EVENT_CLASSES,
    AllianceBonusEvent,
    AllianceMobilizationEvent,
    AllianceTournamentEvent,
    ArtifactEvent,
    CampaignEvent,
    CampaignQuestEvent,
    DiscountSaleEvent,
    EventPart,
    FameBoosterEvent,
    FortuneTellerEvent,
    GiftEvent,
    LuckyWheelEvent,
    PointEvent,
    SeasonEvent,
    SkipForFreeEvent,
    SpecialEvent,
    TournamentEvent,
)
from empire_core.gamedata import QuestId
from empire_core.gamedata.ids.events import Event
from empire_core.map import MapObject
from empire_core.quests import Quest
from empire_core.state import events as event_state


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(event_state, "_clock", lambda: now[0])
    return now


def sei(state, *entries: dict[str, Any]) -> None:
    state.update_from_packet("sei", {"E": list(entries)})


def settle(state) -> None:
    done = threading.Event()
    state._dispatch_callback(done.set)
    assert done.wait(5)


@pytest.mark.parametrize(
    ("event", "model"),
    [
        (Event.ALLI_TOURNAMENT, AllianceTournamentEvent),
        (Event.ALLIANCE_MOBILIZATION_EVENT, AllianceMobilizationEvent),
        (Event.LUCKY_WHEEL, LuckyWheelEvent),
        (Event.SALE_DAYS_LUCKY_WHEEL, LuckyWheelEvent),
        (Event.ARTIFACT_67, ArtifactEvent),
        (Event.THORNKING, SeasonEvent),
        (Event.SEAQUEEN, SeasonEvent),
        (Event.UNDERWORLD, SeasonEvent),
        (Event.FAMEBOOSTER, FameBoosterEvent),
        (Event.PRIME_ALLI_BONUS, AllianceBonusEvent),
        (Event.ALLI_PAYMENT_BONUS, AllianceBonusEvent),
        (Event.RELIC_ENCHANTER_PRIME_SALE, DiscountSaleEvent),
        (Event.SEASON_PASS_PRIME_SALE, DiscountSaleEvent),
        (Event.SKIP_FOR_FREE, SkipForFreeEvent),
        (Event.GGS_GIFT, GiftEvent),
        (Event.FORTUNE_TELLER, FortuneTellerEvent),
        (Event.TOURNAMENT, TournamentEvent),
        (Event.TIME_LIMITED_CAMPAIGN_EVENT, CampaignEvent),
        (Event.TIME_LIMITED_CAMPAIGN_QUEST_EVENT, CampaignQuestEvent),
    ],
)
def test_each_event_has_its_model(event, model):
    assert EVENT_CLASSES[event] is model


class TestScoreEvents:
    def test_alliance_tournament_reads_its_alliance_score_and_peps_into_it(self, state, clock):
        sei(state, {"EID": 36, "RS": 60, "OP": 5, "LID": 2, "A": {"OP": 40, "LID": 3, "RSID": 7}, "KL": 1})
        sei(state, {"EID": 36, "A": {"OR": 4}})

        event = state.get_event(36)
        assert (event.own_points, event.league_id, event.kingdoms_league_mode) == (5, 2, False)
        assert event.parts["A"] == EventPart(own_points=40, league_id=3, own_rank=4, reward_set_id=0)

        state.update_from_packet("pep", {"EID": 36, "OR": [2], "OP": [55], "PT": [100]})

        event = state.get_event(36)
        assert (event.parts["A"].own_rank, event.parts["A"].own_points, event.parts["A"].max_points) == (2, 55, 0)
        assert event.own_points == 5

    @pytest.mark.parametrize(
        "entry",
        [
            {"EID": 36, "RS": 60},
            {"EID": 129, "RS": 60, "SP": {}},
            {"EID": 129, "RS": 60, "A": {}},
            {"EID": 96, "RS": 60},
        ],
    )
    def test_an_entry_its_client_class_fails_to_read_is_skipped(self, state, clock, entry):
        added: list[SpecialEvent] = []
        state.on_event_added(added.append)

        sei(state, entry)
        settle(state)

        assert state.get_event(entry["EID"]) is None and added == []

    def test_alliance_mobilisation_rebuilds_both_scores_in_the_alliance_league(self, state, clock):
        entry = {
            "EID": 129,
            "RS": 60,
            "RSID": 4,
            "DRI": 9,
            "SP": {"OP": 12, "OR": 3, "LID": 1},
            "A": {"OP": 300, "LID": 2, "SDI": 6},
        }
        sei(state, entry)

        event = state.get_event(129)
        assert isinstance(event, AllianceMobilizationEvent)
        assert (event.league_id, event.subdivision_id, event.division_round_id) == (2, 6, 9)
        assert event.parts["SP"] == EventPart(own_points=12, own_rank=3, league_id=2, reward_set_id=4)
        assert event.parts["A"] == EventPart(own_points=300, league_id=2, reward_set_id=4, sub_type=1)

        state.update_from_packet("pep", {"EID": 129, "OR": [1, 8], "OP": [20, 310]})

        event = state.get_event(129)
        assert (event.parts["SP"].own_rank, event.parts["SP"].own_points) == (1, 20)
        assert (event.parts["A"].own_rank, event.parts["A"].own_points) == (8, 310)

    def test_alliance_mobilisation_without_a_league_has_no_alliance_score(self, state, clock):
        sei(state, {"EID": 129, "RS": 60, "SP": {}, "A": {"LID": 0}})

        assert "A" not in state.get_event(129).parts

    def test_lucky_wheel_reads_its_score_and_wheel(self, state, clock):
        entry = {"EID": 15, "RS": 60, "OP": 9, "PET": 3, "HFS": 1, "PMA": 0, "CWC": 2, "WCP": 0.5, "JSID": 4, "KL": 1}
        sei(state, entry)

        event = state.get_event(15)
        assert isinstance(event, LuckyWheelEvent) and isinstance(event, PointEvent)
        assert (event.own_points, event.point_event_type, event.kingdoms_league_mode) == (9, 3, False)
        assert (event.has_free_spin, event.pro_mode, event.win_class, event.win_class_progress) == (True, False, 2, 0.5)
        assert (event.jackpot_set_id, event.jackpot_spin_set_id) == (4, 0)

        state.update_from_packet("pep", {"EID": 15, "OR": [7, 1], "OP": [11, 2], "PT": [99]})

        event = state.get_event(15)
        assert (event.own_rank, event.own_points, event.max_points) == (7, 11, 0)


class TestPlainEvents:
    def test_artifact(self, state, clock):
        sei(state, {"EID": 23, "RS": 60, "ALID": 2, "PF": 3, "SID": 1})

        event = state.get_event(23)
        assert (event.artifact_league_id, event.parts_found, event.skin_id) == (2, 3, 1)

    def test_season_event_keeps_unlock_and_reward_until_sent_again(self, state, clock):
        sei(state, {"EID": 2, "RS": 60, "UL": {"UL": 1, "MID": "11"}, "RID": 5, "F": 0})
        sei(state, {"EID": 2, "F": 1})

        event = state.get_event(2)
        assert (event.unlocked, event.map_id, event.reward_id, event.finished) == (True, 11, 5, True)

        sei(state, {"EID": 2, "UL": {"UL": 0}, "F": 1})

        assert state.get_event(2).unlocked is False and state.get_event(2).map_id == 11

    @pytest.mark.parametrize(
        ("entry", "field", "value"),
        [
            ({"EID": 16, "GBP": 25}, "bonus_percent", 25),
            ({"EID": 45, "APP": 10}, "bonus_percent", 10),
            ({"EID": 55, "APP": 15}, "bonus_percent", 15),
            ({"EID": 88, "DIS": 30}, "discount", 30),
            ({"EID": 599, "DIS": 50}, "discount", 50),
            ({"EID": 8, "SEC": 300}, "free_skip_seconds", 300),
            ({"EID": 13, "AC": 1, "SID": "4"}, "collected", True),
            ({"EID": 13, "AC": 0}, "collected", False),
            ({"EID": 13, "SID": "4x"}, "skin_id", 4),
            ({"EID": 24, "OR": 3, "OEP": 900, "MFB": 50, "R": [[1, 1000, {}]]}, "own_fame_points", 900),
        ],
    )
    def test_one_field_events(self, state, clock, entry, field, value):
        sei(state, {"RS": 60, **entry})

        assert getattr(state.get_event(entry["EID"]), field) == value

    def test_fortune_teller_reads_kl_and_its_reset(self, state, clock):
        sei(state, {"EID": 117, "RS": 60, "FTDC": 2, "STR": 30, "KL": 1})

        event = state.get_event(117)
        assert (event.tries, event.daily_reset_time, event.kingdoms_league_mode) == (2, 1030.0, True)

    def test_the_tournament_ranking_keeps_the_places_an_entry_leaves_out(self, state, clock):
        owner = {"OID": 77, "N": "Ana", "L": 40}
        sei(state, {"EID": 24, "RS": 60, "R": [[2, 800, owner], [1, "1000", {}]]})
        sei(state, {"EID": 24, "RS": 60, "R": [[2, 850, owner], [3, 10]]})

        ranking = state.get_event(24).ranking
        assert [(place.rank, place.fame_points) for place in ranking] == [(1, 1000), (2, 850), (3, 10)]
        assert ranking[0].owner is None and ranking[2].owner is None
        assert ranking[1].owner == MapObject.model_validate(owner)

    def test_the_campaign_quest_ids_are_quest_ids(self, state, clock):
        sei(state, {"EID": 96, "RS": 60, "CQS": [{"QID": 3047}, {"QID": 99999999}]})

        assert state.get_event(96).quest_ids == (QuestId.BUY_RUBIES, 99999999)
        assert state.get_event(96).quest_ids[0] is QuestId.BUY_RUBIES

    @pytest.mark.parametrize("eid", [16, 45, 88, 8, 13, 24, 23, 2])
    def test_events_whose_class_skips_the_season_league_ignore_kl(self, state, clock, eid):
        sei(state, {"EID": eid, "RS": 60, "KL": 1})

        assert state.get_event(eid).kingdoms_league_mode is False


class TestCampaign:
    ENTRY: dict[str, Any] = {
        "EID": 95,
        "RS": 600,
        "RIDS": [3, 4],
        "COL": 0,
        "ERV": 12,
        "CQS": [
            {"QID": 50, "CQID": 2, "QCS": "N"},
            {"QID": 51, "CQID": 3, "ST": 10, "QCS": "C"},
            {"QID": 52, "CQID": 1, "ST": 10, "P": [4]},
        ],
    }

    def test_quests_in_campaign_order(self, state, clock):
        sei(state, self.ENTRY)

        event = state.get_event(95)
        assert [quest.quest_id for quest in event.quests] == [52, 51, 50]
        assert event.quests[0] == Quest(quest_id=52, progress=(4,), campaign_quest_id=1, campaign_timestamp=10)
        assert (event.reward_ids, event.reward_collected, event.end_reward_value) == ((3, 4), False, 12)

    def test_a_cqs_reads_the_campaign_again(self, state, clock):
        sei(state, self.ENTRY)
        seen: list[Any] = []
        state.on_events_updated(seen.append)

        state.update_from_packet("cqs", {"COL": 1, "ERV": 20, "CQS": [{"QID": 50, "CQID": 2, "QCS": "C"}], "RS": 5})
        settle(state)

        event = state.get_event(95)
        assert (event.reward_collected, event.end_reward_value, event.reward_ids) == (True, 20, ())
        assert event.quests == (Quest(quest_id=50, campaign_quest_id=2, completed=True),)
        assert event.end_time == 1600.0
        assert len(seen) == 1 and state.get_last_packet_time("cqs") is not None

    def test_a_cqs_without_the_campaign_or_on_error_does_nothing(self, state, clock):
        seen: list[Any] = []
        state.on_events_updated(seen.append)
        state.update_from_packet("cqs", {"COL": 1})
        sei(state, self.ENTRY)
        state.update_from_packet("cqs", {"COL": 1}, error_code=1)
        settle(state)

        assert state.get_event(95).reward_collected is False and len(seen) == 1

    def test_the_campaign_quest_event_names_its_quests(self, state, clock):
        sei(state, {"EID": 96, "RS": 60, "CQS": [{"QID": 50}, {"QID": "51"}]}, {"EID": 96, "RS": 60})

        event = state.get_event(96)
        assert isinstance(event, CampaignQuestEvent) and event.quest_ids == (50, 51)


def test_an_event_without_a_model_stays_plain(state, clock):
    sei(state, {"EID": 46, "RS": 60})

    assert type(state.get_event(46)) is SpecialEvent
