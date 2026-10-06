"""
Your quests as ``client.state`` keeps them: the active quests (``qli``), the quest book's main
quests, and the daily quests (``dql``).

The state has no game data, so a quest is its id (a ``QuestId`` or ``DailyQuestId``) and the
progress the server sent; its conditions, rewards and texts are in the items' ``quests`` and
``dailyactivities`` rows (``GameData.record``).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from empire_core.gamedata import Collectable, EnumOrInt
from empire_core.protocol.js import js_int, js_loose_equals, js_truthy

if TYPE_CHECKING:
    from empire_core.gamedata import DailyQuestId, QuestId


class Quest(BaseModel):
    """
    One of your active quests, or a time-limited campaign's quest.

    ``progress`` holds one counter per condition, in the order of the quest's ``conditions``
    in the items; the client keeps the counters as sent, the library reads them through ``int()``.
    The client also counts a quest whose time has run out, and is not done, as failed.

    Client: ``CastleQuestVO.fillFromParams`` (bundle line 52463), ``remainingSeconds`` and
    ``isFailed`` (bundle lines 52592, 52583)
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    quest_id: EnumOrInt["QuestId"] = Field(alias="QID", description="The quest")
    progress: tuple[int, ...] = Field(default=(), alias="P", description="Each condition's counter")
    end_time: float | None = Field(
        default=None,
        alias="RS",
        description="When the quest runs out, in time.monotonic() seconds; None without RS or for a negative one",
    )
    completed: bool = Field(default=False, description="Whether the quest is done, from S or QCS")
    failed: bool = Field(default=False, description="Whether the quest has failed, from S or QCS")
    locked: bool = Field(default=False, description="Whether the quest is not open yet, from QCS")
    campaign_quest_id: int = Field(default=0, alias="CQID", description="The quest's place in a campaign")
    campaign_timestamp: int | None = Field(
        default=None, alias="ST", description="When a campaign quest opens, as sent; None without one"
    )

    @classmethod
    def from_entry(cls, entry: dict[str, Any], now: float | None = None) -> Quest:
        """
        A quest read from its entry.

        ``S`` decides done or failed (1 or 0) and wins over ``QCS`` ("C" done, "F" failed,
        "N" locked); without either the quest is neither.
        """
        now = time.monotonic() if now is None else now
        values: dict[str, Any] = {"quest_id": js_int(entry.get("QID"))}
        if isinstance(progress := entry.get("P"), list):
            values["progress"] = tuple(map(js_int, progress))
        if "RS" in entry and (seconds := js_int(entry["RS"])) >= 0:
            values["end_time"] = now + seconds
        if "S" in entry:
            values["completed"] = js_loose_equals(entry["S"], 1)
            values["failed"] = js_loose_equals(entry["S"], 0)
        elif "QCS" in entry:
            values["completed"] = entry["QCS"] == "C"
            values["failed"] = entry["QCS"] == "F"
            values["locked"] = entry["QCS"] == "N"
        if "CQID" in entry:
            values["campaign_quest_id"] = js_int(entry["CQID"])
        if "ST" in entry:
            values["campaign_timestamp"] = js_int(entry["ST"])
        return cls(**values)

    def remaining_seconds(self, now: float | None = None) -> float | None:
        """Seconds until the quest runs out, 0 once it has; None for a quest without a time limit."""
        if self.end_time is None:
            return None
        return max(0.0, self.end_time - (time.monotonic() if now is None else now))


class QuestBook(BaseModel):
    """
    The quest book's main quests: those announced, running and finished.

    Client: ``CastleQuestBookMainQuestListVO.parseListsFromParamObject`` (bundle line 52419)
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    announced_quest_ids: tuple[int, ...] = Field(default=(), alias="ANN", description="The main quests announced")
    running_quest_ids: tuple[int, ...] = Field(default=(), alias="R", description="The main quests running")
    finished_quest_ids: tuple[int, ...] = Field(default=(), alias="D", description="The main quests finished")

    @classmethod
    def from_section(cls, section: dict[str, Any]) -> QuestBook | None:
        """The book a ``qli`` carries, or None when one of ``ANN``, ``R`` and ``D`` is missing or no list.

        The client then keeps its own.
        """
        lists = [section.get(key) for key in ("ANN", "R", "D")]
        if not all(isinstance(ids, list) for ids in lists):
            return None
        announced, running, finished = (tuple(map(js_int, ids)) for ids in lists if isinstance(ids, list))
        return cls(announced_quest_ids=announced, running_quest_ids=running, finished_quest_ids=finished)


class DailyQuest(BaseModel):
    """
    One of today's daily quests.

    Client: ``DailyQuestVO.setProgress`` and ``setFinished`` (bundle lines 134132, 134135)
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    quest_id: EnumOrInt["DailyQuestId"] = Field(alias="QID", description="The daily quest")
    progress: tuple[int, ...] = Field(
        default=(),
        alias="P",
        description="Each condition's counter, read through int(); empty for a finished quest, whose counters are full",
    )
    finished: bool = Field(default=False, description="Whether you finished it today (listed in FDQ)")


class DailyQuests(BaseModel):
    """
    Your daily quests: your daily quest level, today's quests and the reward thresholds.

    Client: ``CastleDailyQuestData.parse_DQL`` (bundle line 134062), ``parse_RDQ`` and ``parse_FDQ``
    (bundle lines 134063, 134070)
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    level: int = Field(default=0, alias="PQL", description="Your daily quest level")
    quests: tuple[DailyQuest, ...] = Field(
        default=(), description="The finished (FDQ) and running (RDQ) quests, by quest id"
    )
    threshold_rewards: tuple[tuple[Collectable, ...], ...] = Field(
        default=(), alias="RS", description="Each reward threshold's rewards, in threshold order"
    )

    @classmethod
    def from_section(cls, section: dict[str, Any], previous: DailyQuests | None = None) -> DailyQuests:
        """
        The daily quests a ``dql`` makes; a falsy ``RS`` keeps the thresholds of ``previous``.

        The client drops the ids its items lack; the library keeps every one.
        """
        finished, running = section.get("FDQ"), section.get("RDQ")
        quests = [
            DailyQuest(quest_id=js_int(qid), finished=True) for qid in (finished if isinstance(finished, list) else ())
        ]
        for entry in running if isinstance(running, list) else ():
            if isinstance(entry, dict):
                progress = entry.get("P")
                quests.append(
                    DailyQuest(
                        quest_id=js_int(entry.get("QID")),
                        progress=tuple(map(js_int, progress)) if isinstance(progress, list) else (),
                    )
                )
        thresholds = section.get("RS")
        if js_truthy(thresholds) and isinstance(thresholds, list):
            rewards = tuple(Collectable.from_rows(rows) for rows in thresholds)
        else:
            rewards = previous.threshold_rewards if previous is not None else ()
        return cls(
            level=js_int(section.get("PQL")),
            quests=tuple(sorted(quests, key=lambda quest: quest.quest_id)),
            threshold_rewards=rewards,
        )
