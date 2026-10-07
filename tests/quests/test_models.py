"""The quest models read from their entries as the client's quest classes read them."""

import pytest

from empire_core.enums import CollectableKind
from empire_core.gamedata import DailyQuestId, MainQuest
from empire_core.quests import DailyQuest, DailyQuests, Quest, QuestBook


class TestQuest:
    def test_an_entry_with_progress_and_time(self):
        quest = Quest.from_entry({"QID": 1201, "P": [3, "2"], "RS": 600}, now=100.0)

        assert quest == Quest(quest_id=1201, progress=(3, 2), end_time=700.0)
        assert quest.remaining_seconds(now=400.0) == 300.0
        assert quest.remaining_seconds(now=900.0) == 0.0

    @pytest.mark.parametrize("entry", [{"QID": 1}, {"QID": 1, "RS": -1}])
    def test_no_rs_or_a_negative_one_has_no_time_limit(self, entry):
        quest = Quest.from_entry(entry, now=100.0)

        assert quest.end_time is None and quest.remaining_seconds() is None

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ({"S": 1}, (True, False, False)),
            ({"S": 0}, (False, True, False)),
            ({"S": "1"}, (True, False, False)),
            ({"S": 1, "QCS": "N"}, (True, False, False)),
            ({"S": None}, (False, False, False)),
            ({"S": ""}, (False, True, False)),
            ({"QCS": "C"}, (True, False, False)),
            ({"QCS": "F"}, (False, True, False)),
            ({"QCS": "N"}, (False, False, True)),
            ({}, (False, False, False)),
        ],
    )
    def test_s_wins_over_qcs(self, status, expected):
        quest = Quest.from_entry({"QID": 1, **status})

        assert (quest.completed, quest.failed, quest.locked) == expected

    def test_campaign_fields(self):
        quest = Quest.from_entry({"QID": 5, "CQID": 2, "ST": 30})

        assert (quest.campaign_quest_id, quest.campaign_timestamp) == (2, 30)

    def test_frozen(self):
        quest = Quest(quest_id=1)
        with pytest.raises(ValueError):
            quest.quest_id = 2  # type: ignore[misc]


class TestQuestBook:
    def test_all_three_lists_make_a_book(self):
        book = QuestBook.from_section({"ANN": [9], "R": [5, 6], "D": [1]})

        assert book == QuestBook(announced_quest_ids=(9,), running_quest_ids=(5, 6), finished_quest_ids=(1,))
        # Ids the main quests know are their members; one newer than the enum stays an int
        assert book.running_quest_ids == (MainQuest.TRUE_HAPPINESS, MainQuest.THE_EVERWINTER_GLACIER)
        assert type(book.announced_quest_ids[0]) is int

    @pytest.mark.parametrize("section", [{"R": [5], "D": [1]}, {"ANN": None, "R": [5], "D": [1]}, {}])
    def test_a_missing_list_makes_none(self, section):
        assert QuestBook.from_section(section) is None

    def test_empty_lists_are_truthy(self):
        assert QuestBook.from_section({"ANN": [], "R": [], "D": []}) == QuestBook()


class TestDailyQuests:
    def test_finished_and_running_sorted_by_id(self):
        daily = DailyQuests.from_section(
            {"PQL": 4, "FDQ": [30, "10"], "RDQ": [{"QID": 20, "P": [1, 0]}], "RS": [[["C1", 500]], [["C2", 5]]]}
        )

        assert daily.level == 4
        assert daily.quests == (
            DailyQuest(quest_id=10, finished=True),
            DailyQuest(quest_id=20, progress=(1, 0)),
            DailyQuest(quest_id=30, finished=True),
        )
        assert daily.quests[0].quest_id is DailyQuestId.COUNT_DUNGEONS_10
        rewards = [[(reward.kind, reward.amount) for reward in rows] for rows in daily.threshold_rewards]
        assert rewards == [[(CollectableKind.COINS, 500)], [(CollectableKind.RUBIES, 5)]]

    def test_a_falsy_rs_keeps_the_thresholds(self):
        first = DailyQuests.from_section({"PQL": 1, "RS": [[["W", 1]]]})

        again = DailyQuests.from_section({"PQL": 2, "RDQ": [{"QID": 3, "P": [2]}]}, first)

        assert again.threshold_rewards == first.threshold_rewards and again.level == 2
        assert again.quests == (DailyQuest(quest_id=3, progress=(2,)),)
