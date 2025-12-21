"""
Additional game commands.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict

from empire_core.exceptions import ActionError
from empire_core.protocol.packet import Packet

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class GameCommandsMixin:
    """Mixin for additional game commands."""

    async def _send_command_generic(
        self,
        command: str,
        payload: Dict[str, Any],
        action_name: str,
        wait_for_response: bool = False,
        timeout: float = 5.0,
    ) -> Any:
        """
        Send a command packet.

        Args:
            command: Command ID
            payload: Command payload
            action_name: Human-readable name for logging/errors
            wait_for_response: If True, waits for server response
            timeout: Timeout for response in seconds

        Returns:
            True if successful (fire-and-forget), or response payload if waiting

        Raises:
            ActionError: If command fails
            TimeoutError: If response times out
        """
        # self is EmpireClient
        client: "EmpireClient" = self  # type: ignore

        if wait_for_response:
            client.response_awaiter.create_waiter(command)

        packet = Packet.build_xt(client.config.default_zone, command, payload)
        try:
            await client.connection.send(packet)
            logger.info(f"{action_name} sent")

            if wait_for_response:
                try:
                    response = await client.response_awaiter.wait_for(command, timeout=timeout)

                    # Check for Packet object with error code
                    if hasattr(response, "error_code"):
                        if response.error_code != 0:
                            raise ActionError(f"{action_name} failed with error code {response.error_code}")

                        logger.info(f"{action_name} response received (OK)")
                        return response.payload

                    # Legacy/fallback behavior (if response is just payload)
                    logger.info(f"{action_name} response received")
                    return response

                except asyncio.TimeoutError:
                    raise ActionError(f"{action_name} timed out waiting for response")

            return True
        except Exception as e:
            logger.error(f"Failed to {action_name.lower()}: {e}")
            raise ActionError(f"{action_name} failed: {e}")

    async def cancel_building(self, castle_id: int, queue_id: int) -> bool:
        """Cancel building upgrade."""
        return await self._send_command_generic(
            "cbu",
            {"AID": castle_id, "QID": queue_id},
            f"Cancel building in castle {castle_id}",
        )

    async def speed_up_building(self, castle_id: int, queue_id: int) -> bool:
        """Speed up building with rubies."""
        return await self._send_command_generic(
            "sbu",
            {"AID": castle_id, "QID": queue_id},
            f"Speed up building in castle {castle_id}",
        )

    async def collect_quest_reward(self, quest_id: int) -> bool:
        """Collect quest reward."""
        return await self._send_command_generic("cqr", {"QID": quest_id}, f"Collect quest {quest_id} reward")

    async def recall_army(self, movement_id: int) -> bool:
        """Recall/cancel army movement."""
        return await self._send_command_generic("cam", {"MID": movement_id}, f"Recall movement {movement_id}")

    async def get_battle_reports(self, count: int = 10) -> bool:
        """Get battle reports."""
        return await self._send_command_generic("rep", {"C": count}, f"Get {count} battle reports")

    async def get_battle_report_details(self, report_id: int) -> bool:
        """Get detailed battle report."""
        return await self._send_command_generic("red", {"RID": report_id}, f"Get battle report {report_id} details")

    async def send_message(self, player_id: int, subject: str, message: str) -> bool:
        """Send message to player."""
        return await self._send_command_generic(
            "smg",
            {"RID": player_id, "S": subject, "M": message},
            f"Send message to player {player_id}",
        )

    async def read_mail(self, mail_id: int) -> bool:
        """Mark mail as read."""
        return await self._send_command_generic("rma", {"MID": mail_id}, f"Read mail {mail_id}")

    async def delete_mail(self, mail_id: int) -> bool:
        """Delete mail."""
        return await self._send_command_generic("dma", {"MID": mail_id}, f"Delete mail {mail_id}")

    async def send_direct_message(self, recipient_name: str, subject: str, body: str) -> bool:
        """
        Send a direct message (mail) to a player by name.

        Args:
            recipient_name: Name of the player
            subject: Subject of the message
            body: Message content

        Returns:
            True if command sent successfully and confirmed by server
        """
        # This command requires verification
        await self._send_command_generic(
            "sms",
            {"RN": recipient_name, "MH": subject, "TXT": body},
            f"Send DM to '{recipient_name}'",
            wait_for_response=True,
        )

        return True

    async def search_player(self, name: str) -> bool:
        """
        Search for a player by name.

        Args:
            name: Player name to search for

        Returns:
            True if command sent successfully
        """
        return await self._send_command_generic("wsp", {"PN": name}, f"Search player '{name}'")

    async def get_player_details(self, player_id: int) -> bool:
        """
        Get detailed public profile of a player.

        Args:
            player_id: Player ID

        Returns:
            True if command sent successfully
        """
        return await self._send_command_generic("gdi", {"PID": player_id}, f"Get details for player {player_id}")

    async def get_attack_info(self, origin_id: int, target_id: int, units: Dict[int, int]) -> bool:
        """
        Get attack pre-calculation info (travel time, loot, etc.).

        Args:
            origin_id: Origin castle ID
            target_id: Target castle/area ID
            units: Unit dictionary {unit_id: count}

        Returns:
            True if command sent successfully
        """
        return await self._send_command_generic(
            "gai", {"OID": origin_id, "TID": target_id, "UN": units}, f"Get attack info from {origin_id} to {target_id}"
        )

    async def get_castle_defense_info(self, target_id: int) -> bool:
        """
        Get defense information for a target castle.

        Args:
            target_id: Target castle/area ID

        Returns:
            True if command sent successfully
        """
        return await self._send_command_generic("aci", {"TID": target_id}, f"Get defense info for {target_id}")
