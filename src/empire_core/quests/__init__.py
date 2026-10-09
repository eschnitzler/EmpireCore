"""Your active quests, the quest book's main quests and your daily quests, as ``client.state`` keeps them."""

from typing import TYPE_CHECKING

from empire_core.utils.lazy import lazy_exports

from .models import DailyQuest, DailyQuests, Quest, QuestBook

if TYPE_CHECKING:
    from empire_core.gamedata import DailyQuestId, MainQuest, QuestId

__all__ = [
    "DailyQuest",
    "DailyQuests",
    "Quest",
    "QuestBook",
    "DailyQuestId",
    "MainQuest",
    "QuestId",
]


if not TYPE_CHECKING:
    __getattr__ = lazy_exports(__name__, "empire_core.gamedata.ids", ("DailyQuestId", "MainQuest", "QuestId"))
