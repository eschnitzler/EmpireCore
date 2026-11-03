"""Your quests: the active quests (qli, qst, qpg, qfi and the quest popups of msp) and the daily quests (dql)."""

import logging
import time
from typing import Any

from empire_core.protocol.base import read_or_none
from empire_core.protocol.js import js_truthy
from empire_core.quests.models import (
    DailyQuests,
    PopupsResponse,
    Quest,
    QuestBook,
    QuestFinishedResponse,
    QuestListResponse,
    QuestProgressResponse,
    QuestsStartedResponse,
)
from empire_core.state.base import StateBase, loaded, read_section
from empire_core.utils import callbacks

logger = logging.getLogger(__name__)

_clock = time.monotonic


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

    def _handle_qli(self, data: Any) -> bool:
        """Handle the quest list: ``QL`` replaces the active quests, ``ANN``, ``R`` and ``D`` the quest book.

        The book is kept when the list lacks one of the three. The client empties its list first, so on
        a quest its items lack (``createQuest`` throws, bundle line 20210) it keeps the quests read
        before that one, and neither announces ``GET_QUESTLIST`` nor reads the book (bundle line 126589);
        the library reads every quest and the book.

        Client: ``QLICommand.exec`` (bundle line 126587), ``CastleQuestData.parseActiveQuestList``
        (bundle line 20248), which sorts the quests by id
        """
        if not isinstance(data, dict) or "raw" in data:
            return False
        now = _clock()
        listing = read_or_none(
            lambda body: QuestListResponse.model_validate(body, context={"now": now}),
            data,
            warn=logger,
            what="the quest list",
        )
        if listing is None:
            return False
        quests = sorted(listing.quests, key=lambda quest: quest.quest_id)
        self.quests = {quest.quest_id: quest for quest in quests}
        if listing.book is not None:
            self.quest_book = listing.book
        self._fire(self.on_quests_updated, dict(self.quests))
        return True

    def _handle_qst(self, data: Any) -> None:
        """Handle a quest start: each id in ``QIDS`` not active yet is a new active quest, without progress.

        A quest already active keeps its entry and progress, and is announced again.

        Client: ``QSTCommand.exec`` (bundle line 126619) calls ``startQuest`` (bundle lines 20233-20235) for
        each truthy id, which adds a second entry for an active quest; ``getActiveQuestByID`` finds the
        first. The library keeps one
        """
        push = read_section(QuestsStartedResponse, data, "the quests started")
        started = [int(qid) for qid in push.quest_ids] if push is not None else []
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
        progress = read_section(QuestProgressResponse, data, "a quest's progress")
        if progress is not None and progress.quest_id is not None:
            if (quest := self.quests.get(int(progress.quest_id))) is not None:
                self._fire(self.on_quest_progress, quest)

    def _handle_qfi(self, data: Any) -> None:
        """Handle a finished quest: the quest ``QID`` names is no longer active.

        Client: ``QFICommand.exec`` (bundle line 126566), ``CastleQuestData.finishQuest`` (bundle line 20246)
        """
        if (finished := read_section(QuestFinishedResponse, data, "a finished quest")) is not None:
            self._finish_quest(int(finished.quest_id))

    def _handle_msp(self, data: Any) -> None:
        """Handle the popups a ``msp`` shows: each quest-finished popup (``POP`` 4) finishes its ``VAL`` quest.

        Client: ``MSPCommand.exec`` (bundle line 125438), ``CastlePopUpHelper.displayPopUps`` and
        ``displayPopUp`` (bundle lines 12915, 12921)
        """
        shown = read_section(PopupsResponse, data, "the popups")
        for popup in shown.popups if shown is not None else ():
            if popup.finished_quest_id is not None:
                self._finish_quest(int(popup.finished_quest_id))

    def _finish_quest(self, qid: int) -> None:
        """Drop an active quest and announce it.

        The client announces any active quest it finishes; a hidden or starter quest only shows no
        dialog (bundle lines 126571, 13042).

        Client: ``CastleQuestData.finishQuest`` (bundle line 20254)
        """
        quest = self.quests.get(qid)
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

    def get_daily_quests(self) -> DailyQuests:
        """Your daily quests, from the last ``dql``; the login data brings one.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        with self._lock:
            return loaded(self.daily_quests, "Daily quests")
