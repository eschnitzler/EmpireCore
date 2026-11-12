"""Your active quests, the quest book's main quests and your daily quests, as ``client.state`` keeps them;
donating for a quest."""

from typing import TYPE_CHECKING

from empire_core.enums import PopupType, QuestConditionType
from empire_core.utils.lazy import lazy_exports

from .models import (
    CampaignQuestStatusResponse,
    DailyQuest,
    DailyQuests,
    FinishQuestConditionRequest,
    Popup,
    PopupsResponse,
    Quest,
    QuestBook,
    QuestDonateCurrencyRequest,
    QuestDonateCurrencyResponse,
    QuestDonateResourcesRequest,
    QuestDonateResourcesResponse,
    QuestFinishedResponse,
    QuestListResponse,
    QuestProgressResponse,
    QuestsStartedResponse,
    QuestStarterClickRequest,
)
from .service import QuestsService

if TYPE_CHECKING:
    from empire_core.gamedata import CurrencyId, DailyQuestId, Event, MainQuest, QuestId

__all__ = [
    "DailyQuest",
    "DailyQuests",
    "CampaignQuestStatusResponse",
    "Popup",
    "PopupsResponse",
    "QuestFinishedResponse",
    "QuestListResponse",
    "QuestProgressResponse",
    "QuestsStartedResponse",
    "FinishQuestConditionRequest",
    "Quest",
    "QuestBook",
    "PopupType",
    "QuestConditionType",
    "QuestDonateCurrencyRequest",
    "QuestDonateCurrencyResponse",
    "QuestDonateResourcesRequest",
    "QuestDonateResourcesResponse",
    "QuestStarterClickRequest",
    "QuestsService",
    "CurrencyId",
    "DailyQuestId",
    "Event",
    "MainQuest",
    "QuestId",
]


if not TYPE_CHECKING:
    __getattr__ = lazy_exports(
        __name__, "empire_core.gamedata.ids", ("CurrencyId", "DailyQuestId", "Event", "MainQuest", "QuestId")
    )
