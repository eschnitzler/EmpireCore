"""GameState quests: the qli list, qst, qpg, qfi and msp pushes, the dql section, and their callbacks."""

import threading
from typing import Any

import pytest

from empire_core.enums import CollectableKind
from empire_core.gamedata import Collectable
from empire_core.quests import DailyQuest, DailyQuests, Quest, QuestBook
from empire_core.state import quests as quest_state


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(quest_state, "_clock", lambda: now[0])
    return now


def settle(state) -> None:
    """Wait until every callback queued so far has run."""
    done = threading.Event()
    state._dispatch_callback(done.set)
    assert done.wait(5)


QLI: dict[str, Any] = {
    "QL": [{"QID": 1203, "P": [1]}, {"QID": 1001, "P": [0, 2], "RS": 300, "S": 1}],
    "ANN": [1300],
    "R": [1203],
    "D": [1001, 1002],
}


class TestQuestList:
    def test_a_qli_replaces_the_quests_and_the_book(self, state, clock):
        state.update_from_packet("qli", QLI)

        assert list(state.get_quests()) == [1001, 1203]
        assert state.get_quest(1001) == Quest(quest_id=1001, progress=(0, 2), end_time=1300.0, completed=True)
        assert state.get_quest_book() == QuestBook(
            announced_quest_ids=(1300,), running_quest_ids=(1203,), finished_quest_ids=(1001, 1002)
        )
        assert state.get_last_packet_time("qli") is not None

        state.update_from_packet("qli", {"QL": [{"QID": 7}]})

        assert list(state.get_quests()) == [7]
        assert state.get_quest_book().running_quest_ids == (1203,)

    def test_every_qli_and_only_a_qli_fires_the_list_callback(self, state):
        seen: list[dict[int, Quest]] = []
        state.on_quests_updated(seen.append)

        state.update_from_packet("qli", QLI)
        state.update_from_packet("qst", {"QIDS": [9]})
        state.update_from_packet("qfi", {"QID": 9})
        state.update_from_packet("qli", {"QL": []})
        settle(state)

        assert [list(quests) for quests in seen] == [[1001, 1203], []]
        seen[0].clear()
        assert state.get_quests() == {}

    def test_a_qli_without_ql_empties_the_quests(self, state):
        state.update_from_packet("qli", QLI)
        state.update_from_packet("qli", {})

        assert state.get_quests() == {}

    def test_an_error_reply_is_not_applied(self, state):
        state.update_from_packet("qli", QLI, error_code=1)

        assert state.get_quests() == {} and state.get_last_packet_time("qli") is None

    def test_the_snapshot_is_a_copy(self, state):
        state.update_from_packet("qli", QLI)

        state.get_quests().clear()

        assert len(state.get_quests()) == 2


class TestQuestPushes:
    def test_start_progress_and_finish(self, state):
        seen: list[tuple[str, Any]] = []
        state.on_quest_started(lambda quest: seen.append(("started", quest.quest_id)))
        state.on_quest_progress(lambda quest: seen.append(("progress", quest.quest_id)))
        state.on_quest_finished(lambda quest: seen.append(("finished", quest.quest_id)))
        state.update_from_packet("qli", {"QL": [{"QID": 5, "P": [1]}]})

        state.update_from_packet("qst", {"QIDS": [9, 0, None, 3]})
        state.update_from_packet("qpg", {"P": [5, 2]})
        state.update_from_packet("qpg", {"P": [404, 1]})
        state.update_from_packet("qfi", {"QID": 5})
        state.update_from_packet("qfi", {"QID": 5})
        settle(state)

        assert seen == [("started", 9), ("started", 3), ("progress", 5), ("finished", 5)]
        assert state.get_quests() == {3: Quest(quest_id=3), 9: Quest(quest_id=9)}

    def test_progress_changes_nothing(self, state):
        state.update_from_packet("qli", {"QL": [{"QID": 5, "P": [1]}]})

        state.update_from_packet("qpg", {"P": [5, 7]})

        assert state.get_quest(5).progress == (1,)

    def test_starting_an_active_quest_keeps_its_progress(self, state):
        started: list[Quest] = []
        state.on_quest_started(started.append)
        state.update_from_packet("qli", {"QL": [{"QID": 5, "P": [3]}]})

        state.update_from_packet("qst", {"QIDS": [5]})
        settle(state)

        assert state.get_quest(5).progress == (3,)
        assert [quest.progress for quest in started] == [(3,)]

    def test_a_quest_finished_popup_finishes_the_quest(self, state):
        finished: list[Quest] = []
        state.on_quest_finished(finished.append)
        state.update_from_packet("qli", {"QL": [{"QID": 5}, {"QID": 6}]})

        state.update_from_packet("msp", {"P": [{"POP": 3, "VAL": {"QID": 6}}, {"POP": "4", "VAL": {"QID": 5}}]})
        settle(state)

        assert finished == [Quest(quest_id=5)] and list(state.get_quests()) == [6]

    @pytest.mark.parametrize("command", ["qst", "qfi", "qpg", "msp"])
    def test_an_error_reply_changes_nothing(self, state, command):
        state.update_from_packet("qli", {"QL": [{"QID": 5}]})
        payload = {"QIDS": [9], "QID": 5, "P": [{"POP": 4, "VAL": {"QID": 5}}]}

        state.update_from_packet(command, payload, error_code=1)

        assert list(state.get_quests()) == [5]


class TestDailyQuests:
    DQL: dict[str, Any] = {"PQL": 3, "FDQ": [2], "RDQ": [{"QID": 1, "P": [4]}], "RS": [[["C1", 100]]]}

    def test_the_login_section_and_its_push(self, state):
        seen: list[DailyQuests] = []
        state.on_daily_quests_updated(seen.append)

        state.update_from_packet("gbd", {"dql": self.DQL})
        state.update_from_packet("dql", {"PQL": 4, "RDQ": [{"QID": 5, "P": [0]}]})
        settle(state)

        assert [daily.level for daily in seen] == [3, 4]
        daily = state.get_daily_quests()
        assert daily.quests == (DailyQuest(quest_id=5, progress=(0,)),)
        assert daily.threshold_rewards == ((Collectable(kind=CollectableKind.COINS, key="C1", amount=100),),)
        assert state.get_last_packet_time("dql") is not None

    @pytest.mark.parametrize("dql", [None, 0, ""])
    def test_a_falsy_section_is_not_applied_or_stamped(self, state, dql):
        state.update_from_packet("gbd", {"dql": dql})

        assert state.get_daily_quests() is None and state.get_last_packet_time("dql") is None

    def test_an_error_push_is_not_applied(self, state):
        state.update_from_packet("dql", self.DQL, error_code=1)

        assert state.get_daily_quests() is None


def test_reset_forgets_the_quests(state):
    state.update_from_packet("qli", QLI)
    state.update_from_packet("dql", {"PQL": 1})

    state.reset()

    assert state.get_quests() == {} and state.get_quest_book() is None and state.get_daily_quests() is None
