"""Your quests: the active quests (qli, qst, qpg, qfi and the quest popups of msp) and the daily quests (dql)."""

import time
from typing import Any

from empire_core.protocol.js import js_int, js_truthy
from empire_core.quests.models import DailyQuests, Quest, QuestBook
from empire_core.state.base import StateBase
from empire_core.utils import callbacks

_clock = time.monotonic

# The popup that says a quest is finished. Client: PopupConst.QUEST_FINISH (dll line 19620)
_QUEST_FINISH_POPUP = 4


class QuestState(StateBase):
    on_quests_updated = callbacks.Event[dict[int, Quest]]()
    """Register a callback for every ``qli`` applied: called with every active quest (a copy of :meth:`get_quests`).

    Client: ``CastleQuestDataEvent.GET_QUESTLIST`` from ``parseActiveQuestList`` (bundle line 20248)
    """

    on_quest_started = callbacks.Event[Quest]()
    """Register a callback for each quest a ``qst`` starts, called with the quest as :meth:`get_quest` then gives it.

    Client: ``CastleQuestDataEvent.QUEST_START`` from ``startQuest`` (bundle line 20233)
    """

    on_quest_progress = callbacks.Event[Quest]()
    """Register a callback for a ``qpg`` naming an active quest, called with the quest as the last ``qli`` left it.

    The push changes nothing: its counters come with the next ``qli``.

    Client: ``CastleQuestDataEvent.QUEST_PROGRESS`` from ``parseQuestProgress`` (bundle line 20243)
    """

    on_quest_finished = callbacks.Event[Quest]()
    """Register a callback for an active quest a ``qfi`` or a quest popup (``msp``) finishes.

    It is called with the quest as it last stood.

    Client: ``CastleQuestDataEvent.QUEST_FINISHED`` from ``finishQuest`` (bundle line 20246)
    """

    on_daily_quests_updated = callbacks.Event[DailyQuests]()
    """Register a callback for every ``dql`` applied, the login data's included, called with the daily quests.

    Client: ``CastleQuestDataEvent.DAILYQUEST_REFRESHED`` from ``parse_DQL`` (bundle line 134062)
    """

    def _handle_qli(self, data: Any) -> None:
        """Handle the quest list: ``QL`` replaces the active quests, ``ANN``, ``R`` and ``D`` the quest book.

        The book is kept when the list lacks one of the three. The client empties its list first, so on
        a quest its items lack (``createQuest`` throws, bundle line 20210) it keeps the quests read
        before that one, and neither announces ``GET_QUESTLIST`` nor reads the book (bundle line 126589);
        the library reads every quest and the book.

        Client: ``QLICommand.exec`` (bundle line 126587), ``CastleQuestData.parseActiveQuestList``
        (bundle line 20248), which sorts the quests by id
        """
        if not isinstance(data, dict):
            return
        entries, now = data.get("QL"), _clock()
        quests = (
            [Quest.from_entry(entry, now) for entry in entries if isinstance(entry, dict)]
            if isinstance(entries, list)
            else []
        )
        self.quests = {quest.quest_id: quest for quest in sorted(quests, key=lambda quest: quest.quest_id)}
        if (book := QuestBook.from_section(data)) is not None:
            self.quest_book = book
        self._fire(self.on_quests_updated, dict(self.quests))

    def _handle_qst(self, data: Any) -> None:
        """Handle a quest start: each id in ``QIDS`` not active yet is a new active quest, without progress.

        A quest already active keeps its entry and progress, and is announced again.

        Client: ``QSTCommand.exec`` (bundle line 126619) calls ``startQuest`` (bundle lines 20233-20235) for
        each truthy id, which adds a second entry for an active quest; ``getActiveQuestByID`` finds the
        first. The library keeps one
        """
        ids = data.get("QIDS") if isinstance(data, dict) else None
        started = [js_int(qid) for qid in ids if js_truthy(qid)] if isinstance(ids, list) else []
        if not started:
            return
        quests = {**{qid: Quest(quest_id=qid) for qid in started}, **self.quests}
        self.quests = dict(sorted(quests.items()))
        for qid in started:
            self._fire(self.on_quest_started, self.quests[qid])

    def _handle_qpg(self, data: Any) -> None:
        """Handle quest progress: ``P[0]`` names the quest; the rest of ``P`` the client does not read.

        Client: ``QPGCommand.exec`` (bundle line 126603), ``CastleQuestData.parseQuestProgress``
        (bundle line 20243)
        """
        progress = data.get("P") if isinstance(data, dict) else None
        if isinstance(progress, list) and progress and (quest := self.quests.get(js_int(progress[0]))) is not None:
            self._fire(self.on_quest_progress, quest)

    def _handle_qfi(self, data: Any) -> None:
        """Handle a finished quest: the quest ``QID`` names is no longer active.

        Client: ``QFICommand.exec`` (bundle line 126566), ``CastleQuestData.finishQuest`` (bundle line 20246)
        """
        if isinstance(data, dict):
            self._finish_quest(data.get("QID"))

    def _handle_msp(self, data: Any) -> None:
        """Handle the popups a ``msp`` shows: each quest-finished popup (``POP`` 4) finishes its ``VAL`` quest.

        Client: ``MSPCommand.exec`` (bundle line 125438), ``CastlePopUpHelper.displayPopUps`` and
        ``displayPopUp`` (bundle lines 12915, 12921)
        """
        popups = data.get("P") if isinstance(data, dict) else None
        for popup in popups if isinstance(popups, list) else ():
            if isinstance(popup, dict) and js_int(popup.get("POP")) == _QUEST_FINISH_POPUP:
                value = popup.get("VAL")
                self._finish_quest(value.get("QID") if isinstance(value, dict) else None)

    def _finish_quest(self, qid: Any) -> None:
        """Drop an active quest and announce it.

        The client announces any active quest it finishes; a hidden or starter quest only shows no
        dialog (bundle lines 126571, 13042).

        Client: ``CastleQuestData.finishQuest`` (bundle lines 20246-20247)
        """
        quest = self.quests.get(js_int(qid))
        if quest is None:
            return
        self.quests = {key: value for key, value in self.quests.items() if key != quest.quest_id}
        self._fire(self.on_quest_finished, quest)

    def _parse_daily_quests(self, data: dict[str, Any]) -> bool:
        """Apply a ``dql`` section: daily quest level, today's quests and reward thresholds; whether it was applied.

        Client: ``CastleDailyQuestData.parse_DQL`` (bundle line 134062), from ``GBDCommand.exec``
        (bundle line 129381) and ``DQLCommand.exec`` (bundle line 126512); it does nothing for a falsy section
        """
        dql = data.get("dql")
        if not (js_truthy(dql) and isinstance(dql, dict)):
            return False
        self.daily_quests = DailyQuests.from_section(dql, self.daily_quests)
        self._fire(self.on_daily_quests_updated, self.daily_quests)
        return True

    def get_quests(self) -> dict[int, Quest]:
        """Your active quests by id, in id order, as the last ``qli`` and the quest pushes since left them; a copy.

        Empty until a ``qli`` arrived (the server pushes it after login, not inside the login data).
        """
        with self._lock:
            return dict(self.quests)

    def get_quest(self, quest_id: int) -> Quest | None:
        """An active quest, or None when it is not active."""
        with self._lock:
            return self.quests.get(quest_id)

    def get_quest_book(self) -> QuestBook | None:
        """The quest book's main quests, from the last ``qli`` that had them; None until one did."""
        with self._lock:
            return self.quest_book

    def get_daily_quests(self) -> DailyQuests | None:
        """Your daily quests, from the last ``dql`` (the login data has one); None until one arrived."""
        with self._lock:
            return self.daily_quests
