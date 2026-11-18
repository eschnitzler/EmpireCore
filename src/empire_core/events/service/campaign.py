"""The time-limited campaign: buying a quest or the end reward with rubies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.events.models import CampaignEvent
from empire_core.events.service.base import EventsBaseMixin
from empire_core.exceptions import EventNotRunningError
from empire_core.gamedata.ids.events import Event
from empire_core.quests.models import (
    BuyCampaignQuestRequest,
    BuyCampaignQuestResponse,
    BuyCampaignRewardRequest,
    BuyCampaignRewardResponse,
)

if TYPE_CHECKING:
    from empire_core.quests.models import Quest


class CampaignMixin(EventsBaseMixin):
    def _require_campaign(self) -> CampaignEvent:
        campaign = self._require_running(Event.TIME_LIMITED_CAMPAIGN_EVENT)
        if not isinstance(campaign, CampaignEvent):
            raise EventNotRunningError(int(Event.TIME_LIMITED_CAMPAIGN_EVENT))
        return campaign

    def buy_campaign_quest(self, quest: Quest, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Buy a quest of the running time-limited campaign done, with rubies; see "Spending rubies" in the guides.

        The client offers it for a campaign quest that is open, not done, and failed, which counts one whose
        time ran out; the server checks the last. Its price, the quest's ``c2Cost`` less the ``c2Reduction``
        of each condition done, is not worked out here, so this always needs ``spend_rubies``.

        Args:
            quest: One of the campaign's quests, from its ``CampaignEvent.quests``
            spend_rubies: Allow the rubies it costs; without it nothing is sent
            timeout: Timeout in seconds

        Raises:
            EventNotRunningError: No time-limited campaign runs
            ValueError: The quest is not one of the campaign's, is done or not open yet, or ``spend_rubies``
                is False
            CommandError: The server refused

        Client: ``QuestInfoComponent.showQuest`` (bundle line 458508) shows the buy button and ``onClick``
        (bundle line 458577) opens ``CastleQuestBuyRewardDialog``, priced by ``CastleQuestVO.buyCost``
        (bundle line 269537), whose ``onClick`` (bundle line 270612) sends ``bcq``; ``BCQCommand.exec``
        (bundle line 640412)
        """
        campaign = self._require_campaign()
        if not any(entry.campaign_quest_id == quest.campaign_quest_id for entry in campaign.quests):
            raise ValueError(f"quest {quest.quest_id!r} is not one of the running campaign's")
        if quest.completed or quest.locked:
            raise ValueError(f"campaign quest {quest.quest_id!r} is done or not open yet")
        self._require_spend_rubies(spend_rubies, "buying a campaign quest costs rubies")
        request = BuyCampaignQuestRequest(campaign_quest_id=quest.campaign_quest_id)
        self.request(request, BuyCampaignQuestResponse, timeout=timeout, spend_rubies=spend_rubies)

    def buy_campaign_reward(self, *, spend_rubies: bool = False, timeout: float = 5.0) -> BuyCampaignRewardResponse:
        """
        Buy the running time-limited campaign's end reward, with rubies; see "Spending rubies" in the guides.

        Its price falls with each campaign quest done and is not worked out here, so this always needs
        ``spend_rubies``.

        Args:
            spend_rubies: Allow the rubies it costs; without it nothing is sent
            timeout: Timeout in seconds

        Returns:
            Your coins and rubies after

        Raises:
            EventNotRunningError: No time-limited campaign runs
            ValueError: The end reward was collected, or ``spend_rubies`` is False
            CommandError: The server refused

        Client: ``CampaignQuestListComponent.show`` (bundle line 458237) shows the buy button until the reward is
        received (``COL``), and its ``onClick`` (bundle line 458293) opens ``CastleQuestBuyRewardDialog``, priced by
        ``TimeLimitedCampaignEventEventVO.buyCost`` (bundle line 607691) through
        ``TimeLimitedCampaignConst.calculateEndRewardPurchaseCost`` (dll); ``BCRCommand.exec`` (bundle line 640456)
        """
        if self._require_campaign().reward_collected:
            raise ValueError("the campaign's end reward was collected")
        self._require_spend_rubies(spend_rubies, "buying a campaign's end reward costs rubies")
        return self.request(
            BuyCampaignRewardRequest(), BuyCampaignRewardResponse, timeout=timeout, spend_rubies=spend_rubies
        )
