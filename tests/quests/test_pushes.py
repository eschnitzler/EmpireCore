"""The quest pushes: qli, qst, qpg, qfi, cqs, and the popups of msp."""

import pytest

from empire_core.enums import PopupType
from empire_core.gamedata import CollectableKind
from empire_core.protocol.models import parse_response
from empire_core.quests.models import (
    CampaignQuestStatusResponse,
    PopupsResponse,
    QuestFinishedResponse,
    QuestListResponse,
    QuestProgressResponse,
    QuestsStartedResponse,
)


class TestQuestList:
    def test_quests_and_the_book(self):
        listing = parse_response(
            "qli", {"QL": [{"QID": 5, "P": [1]}, "x", {"QID": "7"}], "ANN": [1], "R": [2], "D": []}
        )
        assert isinstance(listing, QuestListResponse)
        assert [(q.quest_id, q.progress) for q in listing.quests] == [(5, (1,)), (7, ())]
        assert listing.book is not None and listing.book.running_quest_ids == (2,)

    def test_the_book_needs_all_three_lists(self):
        # parseListsFromParamObject: e.ANN && e.R && e.D
        assert QuestListResponse.model_validate({"QL": [], "ANN": [1], "R": [2]}).book is None

    def test_a_context_dates_the_quests(self):
        listing = QuestListResponse.model_validate({"QL": [{"QID": 5, "RS": 10}]}, context={"now": 100.0})
        assert listing.quests[0].end_time == 110.0


class TestQuestIds:
    def test_started_ids_are_the_truthy_ones_through_int(self):
        assert QuestsStartedResponse.model_validate({"QIDS": [9, 0, None, "3"]}).quest_ids == (9, 3)
        assert QuestsStartedResponse.model_validate({}).quest_ids == ()

    def test_progress_names_the_first_entry_only(self):
        assert QuestProgressResponse.model_validate({"P": ["5", 2]}).quest_id == 5
        assert QuestProgressResponse.model_validate({"P": []}).quest_id is None
        assert QuestProgressResponse.model_validate({}).quest_id is None

    def test_a_finished_quest_and_its_equipment(self):
        finished = parse_response("qfi", {"QID": "5", "GEQ": [["W", 8]]})
        assert isinstance(finished, QuestFinishedResponse) and finished.quest_id == 5
        assert [(g.kind, g.amount) for g in finished.random_equipment_rewards] == [(CollectableKind.WOOD, 8)]


class TestCampaignQuestStatus:
    def test_the_campaign_in_order(self):
        status = parse_response(
            "cqs",
            {
                "RIDS": ["12", 13],
                "COL": "1",
                "ERV": "20",
                "CQS": [{"QID": 50, "CQID": 2, "ST": 5}, {"QID": 51, "CQID": 1}, {"QID": 52, "CQID": 1, "ST": 5}],
            },
        )
        assert isinstance(status, CampaignQuestStatusResponse)
        assert (tuple(int(r) for r in status.reward_ids), status.reward_collected, status.end_reward_value) == (
            (12, 13),
            True,
            20,
        )
        assert [q.quest_id for q in status.quests] == [52, 50, 51]


class TestPopups:
    def test_a_quest_finished_popup_names_its_quest(self):
        shown = parse_response("msp", {"P": [{"POP": 3, "VAL": {"QID": 6}}, {"POP": "4", "VAL": {"QID": "5"}}, "x"]})
        assert isinstance(shown, PopupsResponse)
        assert [(p.popup_id, p.finished_quest_id) for p in shown.popups] == [(3, None), (PopupType.QUEST_FINISH, 5)]
        assert shown.popups[0].value == {"QID": 6}

    @pytest.mark.parametrize("body", [{}, {"P": None}, {"P": "x"}])
    def test_no_popups(self, body):
        assert PopupsResponse.model_validate(body).popups == ()
