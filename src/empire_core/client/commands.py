"""
Additional game commands.
"""

import logging
from typing import Dict, Any, TYPE_CHECKING

from empire_core.exceptions import ActionError
from empire_core.protocol.packet import Packet

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class GameCommands:
    """Additional game commands beyond actions."""

    def __init__(self, client: "EmpireClient"):
        self.client = client
        self.config = client.config

    async def _send_command(
        self, command: str, payload: Dict[str, Any], action_name: str
    ) -> bool:
        """
        Send a command packet.

        Args:
            command: Command ID
            payload: Command payload
            action_name: Human-readable name for logging/errors

        Returns:
            True if successful

        Raises:
            ActionError: If command fails
        """
        packet = Packet.build_xt(self.config.default_zone, command, payload)
        try:
            await self.client.connection.send(packet)
            logger.info(f"{action_name} successful")
            return True
        except Exception as e:
            logger.error(f"Failed to {action_name.lower()}: {e}")
            raise ActionError(f"{action_name} failed: {e}")

    async def cancel_building(self, castle_id: int, queue_id: int) -> bool:
        """Cancel building upgrade."""
        return await self._send_command(
            "cbu",
            {"AID": castle_id, "QID": queue_id},
            f"Cancel building in castle {castle_id}",
        )

    async def speed_up_building(self, castle_id: int, queue_id: int) -> bool:
        """Speed up building with rubies."""
        return await self._send_command(
            "sbu",
            {"AID": castle_id, "QID": queue_id},
            f"Speed up building in castle {castle_id}",
        )

    async def collect_quest_reward(self, quest_id: int) -> bool:
        """Collect quest reward."""
        return await self._send_command(
            "cqr", {"QID": quest_id}, f"Collect quest {quest_id} reward"
        )

    async def recall_army(self, movement_id: int) -> bool:
        """Recall/cancel army movement."""
        return await self._send_command(
            "cam", {"MID": movement_id}, f"Recall movement {movement_id}"
        )

    async def get_battle_reports(self, count: int = 10) -> bool:
        """Get battle reports."""
        return await self._send_command(
            "rep", {"C": count}, f"Get {count} battle reports"
        )

    async def get_battle_report_details(self, report_id: int) -> bool:
        """Get detailed battle report."""
        return await self._send_command(
            "red", {"RID": report_id}, f"Get battle report {report_id} details"
        )

    async def send_message(self, player_id: int, subject: str, message: str) -> bool:
        """Send message to player."""
        return await self._send_command(
            "smg",
            {"RID": player_id, "S": subject, "M": message},
            f"Send message to player {player_id}",
        )

    async def read_mail(self, mail_id: int) -> bool:
        """Mark mail as read."""
        return await self._send_command("rma", {"MID": mail_id}, f"Read mail {mail_id}")

    async def delete_mail(self, mail_id: int) -> bool:
        """Delete mail."""
        return await self._send_command(
            "dma", {"MID": mail_id}, f"Delete mail {mail_id}"
        )
