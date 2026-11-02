"""
Your quests as ``client.state`` keeps them: the active quests (``qli``), the quest book's main
quests, and the daily quests (``dql``); and the requests that donate for a quest (``qdr``, ``qdc``)
and finish a condition the client counts itself (``fcq``) or a quest starter (``qsc``).

The state has no game data, so a quest is its id (a ``QuestId`` or ``DailyQuestId``) and the
progress the server sent; its conditions, rewards and texts are in the items' ``quests`` and
``dailyactivities`` rows (``GameData.record``).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ConfigDict, Field, ValidationInfo, field_validator, model_validator

from empire_core.enums import PopupType, QuestConditionType
from empire_core.gamedata import Collectable, CollectableRows, CurrencyId, EnumOrInt, RewardId
from empire_core.protocol.base import BaseRequest, BaseResponse, EmpireModel
from empire_core.protocol.js import js_int, js_loose_equals, js_truthy

if TYPE_CHECKING:
    from empire_core.gamedata import DailyQuestId, MainQuest, QuestId


class Quest(EmpireModel):
    """
    One of your active quests, or a time-limited campaign's quest.

    ``progress`` holds one counter per condition, in the order of the quest's ``conditions``
    in the items; the client keeps the counters as sent, the library reads them through ``int()``.
    The client also counts a quest whose time has run out, and is not done, as failed.

    Client: ``CastleQuestVO.fillFromParams`` (bundle line 52463), ``remainingSeconds`` and
    ``isFailed`` (bundle lines 52592, 52583)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, populate_by_name=True)

    quest_id: EnumOrInt["QuestId"] = Field(validation_alias="QID", description="The quest")
    progress: tuple[int, ...] = Field(default=(), validation_alias="P", description="Each condition's counter")
    end_time: float | None = Field(
        default=None,
        validation_alias="RS",
        description="When the quest runs out, in time.monotonic() seconds; None without RS or for a negative one",
    )
    completed: bool = Field(default=False, description="Whether the quest is done, from S or QCS")
    failed: bool = Field(default=False, description="Whether the quest has failed, from S or QCS")
    locked: bool = Field(default=False, description="Whether the quest is not open yet, from QCS")
    campaign_quest_id: int = Field(default=0, validation_alias="CQID", description="The quest's place in a campaign")
    campaign_timestamp: int | None = Field(
        default=None,
        validation_alias="ST",
        description="When a campaign quest opens, as sent; None without one",
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


class QuestBook(EmpireModel):
    """
    The quest book's main quests, its chapters: those announced, running and finished.

    Client: ``CastleQuestBookMainQuestListVO.parseListsFromParamObject`` (bundle line 52419). An id is a
    main quest's ``mainQuestID``: the book and the main quest dialog load the same ``Quest_<id><status>``
    picture (bundle lines 52435, 93389)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, populate_by_name=True)

    announced_quest_ids: tuple[EnumOrInt["MainQuest"], ...] = Field(
        default=(), validation_alias="ANN", description="The main quests announced"
    )
    running_quest_ids: tuple[EnumOrInt["MainQuest"], ...] = Field(
        default=(), validation_alias="R", description="The main quests running"
    )
    finished_quest_ids: tuple[EnumOrInt["MainQuest"], ...] = Field(
        default=(), validation_alias="D", description="The main quests finished"
    )

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


def _quests_of(rows: Any, info: ValidationInfo) -> tuple[Quest, ...]:
    # createQuest(n.QID) throws for an entry that is no object or names a quest the items lack; the
    # library skips the first and keeps every id. A validation context's "now" dates the quests
    now = info.context.get("now") if info.context else None
    if not isinstance(rows, list):
        return ()
    return tuple(Quest.from_entry(row, now) for row in rows if isinstance(row, dict))


class QuestListResponse(BaseResponse):
    """
    Your active quests, replacing the ones held, and the quest book's main quests when all three lists are sent.

    Command: qli, a push and the reply to a quest list request.

    Client: ``QLICommand.exec`` (bundle line 126625), ``CastleQuestData.parseActiveQuestList`` (bundle line
    20256), which empties the list first, and ``CastleQuestBookMainQuestListVO.parseListsFromParamObject``
    (bundle line 52442), which reads ``ANN``, ``R`` and ``D`` only when all three are truthy
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "qli"

    quests: tuple[Quest, ...] = Field(validation_alias="QL", default=(), description="The active quests, as sent")
    book: QuestBook | None = Field(
        default=None, description="The quest book's main quests; None when one of its three lists is missing"
    )

    @model_validator(mode="before")
    @classmethod
    def _book(cls, data: Any) -> Any:
        if isinstance(data, dict) and "book" not in data:
            return {**data, "book": QuestBook.from_section(data)}
        return data

    @field_validator("quests", mode="before")
    @classmethod
    def _quests(cls, value: Any, info: ValidationInfo) -> Any:
        return _quests_of(value, info)


class QuestsStartedResponse(BaseResponse):
    """
    Quests that started: each becomes active, without progress.

    Command: qst, a push.

    Client: ``QSTCommand.exec`` (bundle line 126657) calls ``CastleQuestData.startQuest`` (bundle line 20241)
    for each truthy id of ``QIDS``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "qst"

    quest_ids: tuple[EnumOrInt["QuestId"], ...] = Field(
        validation_alias="QIDS", default=(), description="The quests started, in the order sent"
    )

    @field_validator("quest_ids", mode="before")
    @classmethod
    def _truthy_ids(cls, value: Any) -> Any:
        return tuple(js_int(qid) for qid in value if js_truthy(qid)) if isinstance(value, list) else ()


class QuestProgressResponse(BaseResponse):
    """
    A quest made progress: only the quest is named; its counters come with the next ``qli``.

    Command: qpg, a push.

    Client: ``QPGCommand.exec`` (bundle line 126641), ``CastleQuestData.parseQuestProgress`` (bundle line
    20251), which reads ``int(P[0])`` and nothing else of ``P``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "qpg"

    quest_id: EnumOrInt["QuestId"] | None = Field(
        validation_alias="P", default=None, description="The quest; None when P is no list with a first entry"
    )

    @field_validator("quest_id", mode="before")
    @classmethod
    def _first(cls, value: Any) -> Any:
        return js_int(value[0]) if isinstance(value, list) and value else None


class QuestFinishedResponse(BaseResponse):
    """
    A quest is finished: it is no longer active, and its random equipment rewards are shown.

    Command: qfi, a push.

    Client: ``QFICommand.exec`` (bundle line 126604) reads ``int(QID)`` for the quest's prototype and
    ``CastleQuestData.finishQuest`` (bundle line 20254) drops the active quest; ``GEQ`` goes to
    ``CastleQuestCompletedDialogProperties`` (bundle line 54013) as a collectable list
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "qfi"

    quest_id: EnumOrInt["QuestId"] = Field(validation_alias="QID", default=0, description="The quest finished")
    random_equipment_rewards: CollectableRows = Field(
        validation_alias="GEQ", default=(), description="The random equipment the quest gave, if any"
    )

    @field_validator("quest_id", mode="before")
    @classmethod
    def _int(cls, value: Any) -> int:
        return js_int(value)


class CampaignQuestStatusResponse(BaseResponse):
    """
    The time-limited campaign's quests and end reward, read over the running campaign event.

    Command: cqs, a push.

    Client: ``CQSCommand.exec`` (bundle line 126533) does nothing without the campaign running;
    ``TimeLimitedCampaignEventEventVO.parseCQS`` (bundle line 118593) and ``parseParamObject`` (bundle
    line 118574), which sort the quests by ``ST`` and then ``CQID``; ``CommKeys.END_REWARD_VALUE`` is
    ``ERV`` (dll)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "cqs"

    reward_ids: tuple[RewardId, ...] = Field(
        validation_alias="RIDS",
        default=(),
        description="The campaign's rewards; GameData.reward_list gives what they hold",
    )
    reward_collected: bool = Field(
        validation_alias="COL", default=False, description="You collected the end reward (1 == COL)"
    )
    end_reward_value: int = Field(validation_alias="ERV", default=0, description="The end reward's value, int(ERV)")
    quests: tuple[Quest, ...] = Field(
        validation_alias="CQS", default=(), description="The campaign's quests, in campaign order"
    )

    @field_validator("reward_ids", mode="before")
    @classmethod
    def _ids(cls, value: Any) -> Any:
        return tuple(js_int(rid) for rid in value) if isinstance(value, list) else ()

    @field_validator("reward_collected", mode="before")
    @classmethod
    def _collected(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @field_validator("end_reward_value", mode="before")
    @classmethod
    def _value(cls, value: Any) -> int:
        return js_int(value)

    @field_validator("quests", mode="before")
    @classmethod
    def _campaign_order(cls, value: Any, info: ValidationInfo) -> Any:
        quests = list(_quests_of(value, info))
        quests.sort(
            key=lambda quest: (quest.campaign_timestamp is None, quest.campaign_timestamp or 0, quest.campaign_quest_id)
        )
        return tuple(quests)


class Popup(EmpireModel):
    """
    One popup of an ``msp``: which, and the value its dialog reads.

    Client: ``CastlePopUpHelper.displayPopUps`` (bundle line 12922) reads ``int(POP)`` and hands ``VAL`` to
    ``displayPopUp`` (bundle line 12928), whose dialog reads what it needs of it
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    popup_id: EnumOrInt[PopupType] = Field(validation_alias="POP", default=0, description="The popup")
    value: Any = Field(validation_alias="VAL", default=None, description="What the popup's dialog reads, as sent")
    finished_quest_id: EnumOrInt["QuestId"] | None = Field(
        default=None, description="The quest a quest-finished popup names (its VAL's QID); None for any other popup"
    )

    @model_validator(mode="before")
    @classmethod
    def _quest(cls, data: Any) -> Any:
        if isinstance(data, dict) and "finished_quest_id" not in data:
            value = data.get("VAL")
            quest_id = None
            if js_int(data.get("POP")) == PopupType.QUEST_FINISH and isinstance(value, dict) and "QID" in value:
                quest_id = js_int(value["QID"])
            return {**data, "finished_quest_id": quest_id}
        return data

    @field_validator("popup_id", mode="before")
    @classmethod
    def _int(cls, value: Any) -> int:
        return js_int(value)


class PopupsResponse(BaseResponse):
    """
    Popups the server asks the client to show.

    Command: msp, a push.

    Client: ``MSPCommand.exec`` (bundle line 125476), ``CastlePopUpHelper.displayPopUps`` (bundle line
    12922), which reads every entry of ``P``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "msp"

    popups: tuple[Popup, ...] = Field(validation_alias="P", default=(), description="The popups, in the order sent")

    @field_validator("popups", mode="before")
    @classmethod
    def _entries(cls, value: Any) -> Any:
        return tuple(entry for entry in value if isinstance(entry, dict)) if isinstance(value, list) else ()


class DailyQuest(EmpireModel):
    """
    One of today's daily quests.

    Client: ``DailyQuestVO.setProgress`` and ``setFinished`` (bundle lines 134132, 134135)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, populate_by_name=True)

    quest_id: EnumOrInt["DailyQuestId"] = Field(validation_alias="QID", description="The daily quest")
    progress: tuple[int, ...] = Field(
        default=(),
        validation_alias="P",
        description="Each condition's counter, read through int(); empty for a finished quest, whose counters are full",
    )
    finished: bool = Field(default=False, description="Whether you finished it today (listed in FDQ)")


class DailyQuests(BaseResponse):
    """
    Your daily quests: your daily quest level, today's quests and the reward thresholds.

    Command: dql, as a login section of ``gbd`` and a push; the client has no request for it.
    Payload: {"PQL": level, "FDQ": [finished quest id, ...], "RDQ": [{"QID": id, "P": [counter, ...]}, ...],
    "RS": [threshold rewards, ...]}

    The client drops the ids its items lack; the library keeps every one.

    Client: ``DQLCommand.exec`` (bundle line 126550), ``CastleDailyQuestData.parse_DQL`` (bundle line 134062),
    ``parse_RDQ`` and ``parse_FDQ`` (bundle lines 134063, 134070)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "dql"

    level: int = Field(default=0, validation_alias="PQL", description="Your daily quest level")
    quests: tuple[DailyQuest, ...] = Field(
        default=(), description="The finished (FDQ) and running (RDQ) quests, by quest id"
    )
    threshold_rewards: tuple[tuple[Collectable, ...], ...] = Field(
        default=(),
        validation_alias="RS",
        description="Each reward threshold's rewards, in threshold order; empty when none were sent",
    )

    @model_validator(mode="before")
    @classmethod
    def _quest_lists(cls, data: Any) -> Any:
        if not isinstance(data, dict) or not ("FDQ" in data or "RDQ" in data):
            return data
        values = {key: value for key, value in data.items() if key not in ("FDQ", "RDQ")}
        finished, running = data.get("FDQ"), data.get("RDQ")
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
        values["quests"] = tuple(sorted(quests, key=lambda quest: quest.quest_id))
        return values

    @field_validator("level", mode="before")
    @classmethod
    def _level(cls, value: Any) -> int:
        return js_int(value)

    @field_validator("threshold_rewards", mode="before")
    @classmethod
    def _thresholds(cls, value: Any) -> Any:
        if isinstance(value, tuple):
            return value
        if js_truthy(value) and isinstance(value, list):
            return tuple(Collectable.from_rows(rows) for rows in value)
        return ()

    @classmethod
    def from_section(cls, section: dict[str, Any], previous: DailyQuests | None = None) -> DailyQuests:
        """The daily quests a ``dql`` makes; a falsy ``RS`` keeps the thresholds of ``previous``."""
        daily, rows = cls.model_validate(section), section.get("RS")
        if previous is not None and not (js_truthy(rows) and isinstance(rows, list)):
            daily = daily.model_copy(update={"threshold_rewards": previous.threshold_rewards})
        return daily


class QuestDonateResourcesRequest(BaseRequest):
    """
    Donate resources for a quest's donate condition.

    Command: qdr
    Payload: {"QID": quest_id, "F": food, "W": wood, "S": stone, "C1": coins, "O": oil, "C": coal,
    "I": iron, "G": glass, "PWR": 0, "PO": -1}

    ``DonateForQuestCommand.performAction`` puts the condition's amount in the one field of its
    resource and leaves the rest 0. ``PWR`` 1 with a merchant in ``PO`` buys missing resources
    with rubies, which only the resource wait dialog sends (bundle line 35225).

    Client: ``C2SQuestDonateRessourcesVO`` (bundle line 47687), sent by
    ``DonateForQuestCommand.performAction`` (bundle lines 101001-101021)
    """

    command = "qdr"

    quest_id: EnumOrInt["QuestId"] = Field(validation_alias="QID", description="The quest")
    food: int = Field(validation_alias="F", default=0, description="Food to donate")
    wood: int = Field(validation_alias="W", default=0, description="Wood to donate")
    stone: int = Field(validation_alias="S", default=0, description="Stone to donate")
    coins: int = Field(validation_alias="C1", default=0, description="Coins to donate")
    oil: int = Field(validation_alias="O", default=0, description="Oil to donate")
    coal: int = Field(validation_alias="C", default=0, description="Coal to donate")
    iron: int = Field(validation_alias="I", default=0, description="Iron to donate")
    glass: int = Field(validation_alias="G", default=0, description="Glass to donate")
    pay_with_rubies: int = Field(validation_alias="PWR", default=0, description="0: donate what you hold")
    private_offer: int = Field(validation_alias="PO", default=-1, description="The ruby merchant; -1 for none")


class QuestDonateResourcesResponse(BaseResponse):
    """
    The answer to a resource donation; the client reads nothing from it.

    Command: qdr

    Client: ``QDRCommand.executeCommand`` (bundle line 126553)
    """

    command = "qdr"


class QuestDonateCurrencyRequest(BaseRequest):
    """
    Donate a currency, khan medals or samurai tokens, for a quest's donate condition.

    Command: qdc
    Payload: {"QID": quest_id, "CID": currency_id, "A": amount}

    Client: ``C2SQuestDonateCurrencyVO`` (bundle line 101033), sent by
    ``DonateForQuestCommand.performAction`` (bundle lines 101019-101021)
    """

    command = "qdc"

    quest_id: EnumOrInt["QuestId"] = Field(validation_alias="QID", description="The quest")
    currency_id: CurrencyId = Field(validation_alias="CID", description="The currency donated")
    amount: int = Field(validation_alias="A", description="How much to donate")


class QuestDonateCurrencyResponse(BaseResponse):
    """
    The answer to a currency donation; the client reads nothing from it.

    Command: qdc

    Client: ``QDCCommand.executeCommand`` (bundle line 126540)
    """

    command = "qdc"


class FinishQuestConditionRequest(BaseRequest):
    """
    Report a quest condition done that only the client sees done, such as visiting a screen.

    Command: fcq
    Payload: {"QC": condition_type, "QTID": target_id}

    The client has no handler for an answer.

    Client: ``C2SFinishQuestConditionVO`` (bundle line 41691)
    """

    command = "fcq"

    condition_type: QuestConditionType = Field(validation_alias="QC", description="The condition done")
    target_id: int = Field(validation_alias="QTID", default=-1, description="The condition's target; -1 for none")


class QuestStarterClickRequest(BaseRequest):
    """
    Report a quest starter seen through: the dialog or tutorial step that introduces a quest is done.

    Command: qsc
    Payload: {"QID": quest_id}

    The client has no handler for an answer.

    Client: ``C2SQuestStarterClickVO`` (bundle line 37187), sent by ``CastleStartQuestDialog.finishQuestStarter``
    (bundle line 17052), ``TutorialBasicActionCommand.finishTriggerQuest`` (bundle line 9024) and
    ``TutorialAttackRobberBaronCommand.onPlayernameSelected`` (bundle line 143104)
    """

    command = "qsc"

    quest_id: EnumOrInt["QuestId"] = Field(validation_alias="QID", description="The quest the starter introduces")
