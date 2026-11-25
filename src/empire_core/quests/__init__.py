"""Your active quests, the quest book's main quests and your daily quests, as ``client.state`` keeps them;
donating for a quest."""

from typing import TYPE_CHECKING

from empire_core.enums import GrandNobilityPrizeSkin, PopupType, QuestConditionType, RewardGrantType
from empire_core.utils.lazy import lazy_exports

from .models import (
    BuyCampaignQuestRequest,
    BuyCampaignQuestResponse,
    BuyCampaignRewardRequest,
    BuyCampaignRewardResponse,
    CampaignQuestStatusResponse,
    DailyQuest,
    DailyQuests,
    EventRewardPopup,
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
    RewardsUnlockedPopup,
)
from .service import QuestsService

if TYPE_CHECKING:
    from empire_core.gamedata import CurrencyId, DailyQuestId, Event, MainQuest, QuestId

__all__ = [
    "DailyQuest",
    "DailyQuests",
    "CampaignQuestStatusResponse",
    "EventRewardPopup",
    "Popup",
    "PopupsResponse",
    "RewardsUnlockedPopup",
    "QuestFinishedResponse",
    "QuestListResponse",
    "QuestProgressResponse",
    "QuestsStartedResponse",
    "FinishQuestConditionRequest",
    "Quest",
    "QuestBook",
    "GrandNobilityPrizeSkin",
    "PopupType",
    "RewardGrantType",
    "QuestConditionType",
    "QuestDonateCurrencyRequest",
    "QuestDonateCurrencyResponse",
    "QuestDonateResourcesRequest",
    "QuestDonateResourcesResponse",
    "QuestStarterClickRequest",
    "BuyCampaignQuestRequest",
    "BuyCampaignQuestResponse",
    "BuyCampaignRewardRequest",
    "BuyCampaignRewardResponse",
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
