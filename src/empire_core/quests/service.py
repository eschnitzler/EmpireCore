"""
Your active quests, the quest book's main quests and your daily quests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.quests.models import DailyQuests, Quest, QuestBook


class QuestsService(BaseService):
    """
    Your quests as the login data and the quest pushes left them; nothing here sends a request.

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
    def daily(self) -> DailyQuests | None:
        """Your daily quests, from the last ``dql`` (the login data has one); None until one arrived."""
        return self.client.state.get_daily_quests()


__all__ = ["QuestsService"]
