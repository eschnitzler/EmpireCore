"""
Your active quests, the quest book's main quests and your daily quests; donating for a quest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.enums import QuestConditionType
from empire_core.gamedata import CurrencyId
from empire_core.quests.models import (
    FinishQuestConditionRequest,
    QuestDonateCurrencyRequest,
    QuestDonateResourcesRequest,
)
from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.gamedata import QuestId
    from empire_core.quests.models import DailyQuests, Quest, QuestBook

# DonateForQuestCommand.performAction (bundle lines 101001-101021)
_DONATED_RESOURCES: dict[str, str] = {
    QuestConditionType.DONATE_FOOD: "food",
    QuestConditionType.DONATE_WOOD: "wood",
    QuestConditionType.DONATE_STONE: "stone",
    QuestConditionType.DONATE_C1: "coins",
    QuestConditionType.DONATE_COAL: "coal",
    QuestConditionType.DONATE_OIL: "oil",
    QuestConditionType.DONATE_GLASS: "glass",
    QuestConditionType.DONATE_IRON: "iron",
}
_DONATED_CURRENCIES: dict[str, CurrencyId] = {
    QuestConditionType.DONATE_KHAN_MEDALS: CurrencyId.KHAN_MEDALS,
    QuestConditionType.DONATE_SAMURAI_TOKENS: CurrencyId.SAMURAI_TOKENS,
}


class QuestsService(BaseService):
    """
    Your quests as the login data and the quest pushes left them, which send nothing,
    and the requests that donate for a quest or finish a condition.

    Reached as client.quests.
    """

    @property
    def active(self) -> dict[int, Quest]:
        """Your active quests by id, in id order, as the last ``qli`` and the quest pushes since left them; a copy."""
        return self.client.state.get_quests()

    def quest(self, quest_id: int) -> Quest | None:
        """An active quest, or None when it is not active."""
        return self.client.state.get_quest(quest_id)

    @property
    def book(self) -> QuestBook | None:
        """The quest book's main quests, from the last ``qli`` that had them; None until one did."""
        return self.client.state.get_quest_book()

    @property
    def daily(self) -> DailyQuests:
        """Your daily quests, from the last ``dql`` (the login data has one).

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_daily_quests()

    def donate(self, quest_id: QuestId | int, *, timeout: float = 5.0) -> None:
        """
        Donate what the quest's donate condition asks for, the whole amount at once, without rubies.

        The quest's first donate condition in the game data picks the request: a resource is
        sent with ``qdr`` in its field, khan medals and samurai tokens with ``qdc``. A quest the
        donation finishes is reported as any other, through ``client.state.on_quest_finished``.

        Raises:
            ValueError: The game data has no such quest, or the quest has no donate condition
            GameDataNotLoadedError: The game data cannot be loaded
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``DonateForQuestCommand.performAction`` (bundle line 101001), which sends the
        condition's ``conditionMaxCounter`` (``ABasicQuestConditionVO.loadFromParamArray``, bundle line 52833)
        """
        row = self._require_game_data().quests.get(quest_id)
        condition = next(
            (
                condition
                for condition in (row.conditions if row is not None else ())
                if condition.condition_type in _DONATED_RESOURCES or condition.condition_type in _DONATED_CURRENCIES
            ),
            None,
        )
        if condition is None:
            raise ValueError(f"quest {quest_id} has no donate condition")
        currency_id = _DONATED_CURRENCIES.get(condition.condition_type)
        if currency_id is not None:
            request = QuestDonateCurrencyRequest(quest_id=quest_id, currency_id=currency_id, amount=condition.amount)
            self.execute(request, timeout=timeout)
            return
        resource = _DONATED_RESOURCES[condition.condition_type]
        self.execute(QuestDonateResourcesRequest(quest_id=quest_id, **{resource: condition.amount}), timeout=timeout)

    def finish_condition(self, condition_type: QuestConditionType, target_id: int = -1) -> None:
        """
        Report a quest condition done that only the client sees done. The client has no handler for an
        answer, so none is waited for.

        The client sends it only for the two visit conditions of the generals introduction:
        ``VISIT_GENERALS_OVERVIEW`` when the generals overview opens while the active introduction
        quest's first condition is that type, and ``VISIT_GENERALS_INN`` with the current condition's
        target id after the inn's introduction cinematic. What the server checks is unverified.

        Args:
            condition_type: The condition done
            target_id: The condition's target, -1 for none as the client defaults it

        Client: ``C2SFinishQuestConditionVO`` (bundle line 41691), sent by ``GeneralsOverviewDialog.showLoaded``
        (bundle line 15812) and ``GeneralHubIntroductionHandler`` (bundle lines 74775, 74778)
        """
        self.send(FinishQuestConditionRequest(condition_type=condition_type, target_id=target_id))


__all__ = ["QuestsService"]
