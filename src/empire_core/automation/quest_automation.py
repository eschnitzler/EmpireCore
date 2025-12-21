"""
Quest automation for daily quests and achievements.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from empire_core.protocol.packet import Packet
from empire_core.state.quest_models import DailyQuest, Quest

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class QuestService:
    """Service for quest automation and rewards."""

    def __init__(self, client: "EmpireClient"):
        self.client = client

    @property
    def daily_quests(self) -> Optional[DailyQuest]:
        """Get current daily quests."""
        return self.client.state.daily_quests

    async def refresh_quests(self) -> bool:
        """Refresh quest data from server."""
        packet = Packet.build_xt(self.client.config.default_zone, "dql", {})
        await self.client.connection.send(packet)
        return True

    async def collect_available_rewards(self) -> List[int]:
        """Collect rewards for completed quests. Returns list of collected quest IDs."""
        if not self.daily_quests:
            logger.debug("No daily quests data available")
            return []

        collected = []
        for quest_id in self.daily_quests.finished_quests:
            try:
                # Using client method
                success = await self.client.collect_quest_reward(quest_id)
                if success:
                    collected.append(quest_id)
                    logger.info(f"Collected reward for quest {quest_id}")
                else:
                    logger.warning(f"Failed to collect reward for quest {quest_id}")
            except Exception as e:
                logger.error(f"Error collecting quest {quest_id} reward: {e}")

        return collected

    def get_completed_quests(self) -> List[int]:
        """Get list of completed quest IDs."""
        if not self.daily_quests:
            return []
        return self.daily_quests.finished_quests.copy()

    def get_active_quests(self) -> List[Quest]:
        """Get list of active quests."""
        if not self.daily_quests:
            return []
        return self.daily_quests.active_quests.copy()

    def get_quest_progress(self, quest_id: int) -> Optional[List[int]]:
        """Get progress for a specific quest."""
        active_quests = self.get_active_quests()
        for quest in active_quests:
            if quest.quest_id == quest_id:
                return quest.progress.copy()
        return None

    async def auto_collect_rewards(self) -> int:
        """Automatically collect all available quest rewards. Returns count collected."""
        collected = await self.collect_available_rewards()
        if collected:
            logger.info(f"Auto-collected rewards for {len(collected)} quests: {collected}")
        return len(collected)

    def get_daily_quest_summary(self) -> Dict[str, Any]:
        """Get summary of daily quest status."""
        if not self.daily_quests:
            return {"available": False}

        return {
            "available": True,
            "level": self.daily_quests.level,
            "active_count": len(self.daily_quests.active_quests),
            "completed_count": len(self.daily_quests.finished_quests),
            "active_quests": [q.quest_id for q in self.daily_quests.active_quests],
            "completed_quests": self.daily_quests.finished_quests.copy(),
        }
