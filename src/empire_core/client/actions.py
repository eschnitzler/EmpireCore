"""
Action commands for performing game actions (attack, transport, build, etc.)
"""

import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from empire_core.exceptions import ActionError
from empire_core.protocol.packet import Packet
from empire_core.config import ResourceType, TroopActionType

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class GameActions:
    """Handles game action commands."""

    def __init__(self, client: "EmpireClient"):
        """
        Initialize with reference to client.

        Args:
            client: EmpireClient instance
        """
        self.client = client
        self.config = client.config

    async def _send_command(
        self,
        command: str,
        payload: Dict[str, Any],
        action_name: str,
        wait_for_response: bool = False,
        timeout: float = 5.0,
    ) -> Any:
        """
        Send a command packet and optionally wait for response.

        Args:
            command: Command ID (e.g., 'att', 'tra', 'bui')
            payload: Command payload dictionary
            action_name: Human-readable action name for logging
            wait_for_response: Whether to wait for server response
            timeout: Response timeout in seconds

        Returns:
            Response payload if wait_for_response, else True

        Raises:
            ActionError: If command fails
        """
        if wait_for_response:
            self.client.response_awaiter.create_waiter(command)

        packet = Packet.build_xt(self.config.default_zone, command, payload)

        try:
            await self.client.connection.send(packet)
            logger.info(f"{action_name} command sent successfully")

            if wait_for_response:
                logger.debug(f"Waiting for {command} response...")
                response = await self.client.response_awaiter.wait_for(command, timeout)
                logger.info(f"{action_name} response received: {response}")
                return response

            return True
        except Exception as e:
            if wait_for_response:
                self.client.response_awaiter.cancel_command(command)
            logger.error(f"Failed to {action_name.lower()}: {e}")
            raise ActionError(f"{action_name} failed: {e}")

    def _parse_action_response(self, response: Any, action_name: str) -> bool:
        """
        Parse a standard action response from server.

        Args:
            response: Server response
            action_name: Action name for error messages

        Returns:
            True if successful

        Raises:
            ActionError: If server rejected the action
        """
        if isinstance(response, dict):
            if response.get("success") or response.get("MID"):
                return True
            if response.get("error"):
                raise ActionError(
                    f"Server rejected {action_name}: {response.get('error')}"
                )
        return True

    async def send_attack(
        self,
        origin_castle_id: int,
        target_area_id: int,
        units: Dict[int, int],
        kingdom_id: int = 0,
        wait_for_response: bool = False,
        timeout: float = 5.0,
    ) -> bool:
        """
        Send an attack from one castle to a target.

        Args:
            origin_castle_id: ID of attacking castle
            target_area_id: ID of target area
            units: Dictionary of {unit_id: count}
            kingdom_id: Kingdom ID (default 0)
            wait_for_response: Wait for server confirmation (default False)
            timeout: Response timeout in seconds (default 5.0)

        Returns:
            bool: True if attack sent successfully

        Raises:
            ActionError: If attack fails
        """
        logger.info(f"Sending attack from {origin_castle_id} to {target_area_id}")

        if not units or all(count <= 0 for count in units.values()):
            raise ActionError("Must specify at least one unit")

        payload = {
            "OID": origin_castle_id,
            "TID": target_area_id,
            "UN": units,
            "TT": TroopActionType.ATTACK,
            "KID": kingdom_id,
        }

        response = await self._send_command(
            "att", payload, "Attack", wait_for_response, timeout
        )

        if wait_for_response:
            return self._parse_action_response(response, "attack")
        return True

    async def send_transport(
        self,
        origin_castle_id: int,
        target_area_id: int,
        wood: int = 0,
        stone: int = 0,
        food: int = 0,
        wait_for_response: bool = False,
        timeout: float = 5.0,
    ) -> bool:
        """
        Send resources from one castle to another.

        Args:
            origin_castle_id: ID of sending castle
            target_area_id: ID of receiving area
            wood: Amount of wood
            stone: Amount of stone
            food: Amount of food
            wait_for_response: Wait for server confirmation (default False)
            timeout: Response timeout in seconds (default 5.0)

        Returns:
            bool: True if transport sent successfully

        Raises:
            ActionError: If transport fails
        """
        logger.info(f"Sending transport from {origin_castle_id} to {target_area_id}")

        if wood <= 0 and stone <= 0 and food <= 0:
            raise ActionError("Must send at least one resource")

        payload = {
            "OID": origin_castle_id,
            "TID": target_area_id,
            "RES": {
                ResourceType.WOOD: wood,
                ResourceType.STONE: stone,
                ResourceType.FOOD: food,
            },
        }

        response = await self._send_command(
            "tra", payload, "Transport", wait_for_response, timeout
        )

        if wait_for_response:
            return self._parse_action_response(response, "transport")
        return True

    async def upgrade_building(
        self, castle_id: int, building_id: int, building_type: Optional[int] = None
    ) -> bool:
        """
        Upgrade or build a building in a castle.

        Args:
            castle_id: ID of castle
            building_id: ID of building to upgrade
            building_type: Type of building (if constructing new)

        Returns:
            bool: True if upgrade started successfully

        Raises:
            ActionError: If upgrade fails
        """
        logger.info(f"Upgrading building {building_id} in castle {castle_id}")

        payload = {"AID": castle_id, "BID": building_id}
        if building_type is not None:
            payload["BTYP"] = building_type

        await self._send_command("bui", payload, "Building upgrade")
        return True

    async def recruit_units(self, castle_id: int, unit_id: int, count: int) -> bool:
        """
        Recruit/train units in a castle.

        Args:
            castle_id: ID of castle
            unit_id: ID of unit type to recruit
            count: Number of units to recruit

        Returns:
            bool: True if recruitment started successfully

        Raises:
            ActionError: If recruitment fails
        """
        logger.info(f"Recruiting {count}x unit {unit_id} in castle {castle_id}")

        if count <= 0:
            raise ActionError("Must recruit at least one unit")

        payload = {"AID": castle_id, "UID": unit_id, "C": count}

        await self._send_command("tru", payload, "Unit recruitment")
        return True
