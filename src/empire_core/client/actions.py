"""
Action commands for performing game actions (attack, transport, build, etc.)
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from empire_core.config import ResourceType, TroopActionType
from empire_core.exceptions import ActionError
from empire_core.protocol.packet import Packet

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class GameActionsMixin:
    """Mixin for game action commands."""

    async def _send_command_action(
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
        # self.client is now self (EmpireClient)
        client: "EmpireClient" = self  # type: ignore

        if wait_for_response:
            client.response_awaiter.create_waiter(command)

        packet = Packet.build_xt(client.config.default_zone, command, payload)

        try:
            await client.connection.send(packet)
            logger.info(f"{action_name} command sent successfully")

            if wait_for_response:
                logger.debug(f"Waiting for {command} response...")
                response = await client.response_awaiter.wait_for(command, timeout)
                logger.info(f"{action_name} response received: {response}")
                return response

            return True
        except Exception as e:
            if wait_for_response:
                client.response_awaiter.cancel_command(command)
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
                raise ActionError(f"Server rejected {action_name}: {response.get('error')}")
        return True

    def _build_unit_or_tool_payload(self, items: Optional[Dict[int, int]]) -> List[List[int]]:
        """Helper to build unit or tool list for cra payload."""
        if not items:
            return [[-1, 0]] * 6  # Fill with dummy values if empty, matches khan.py pattern

        payload = []
        for item_id, count in items.items():
            payload.append([item_id, count])

        # Pad with [-1, 0] if less than 6 items to match common packet structure
        while len(payload) < 6:
            payload.append([-1, 0])

        return payload[:6]  # Ensure max 6 items

    def _build_flank_payload(self, units: Optional[Dict[int, int]], tools: Optional[Dict[int, int]]) -> Dict[str, Any]:
        """Helper to build flank payload for cra command."""
        return {"T": self._build_unit_or_tool_payload(tools), "U": self._build_unit_or_tool_payload(units)}

    async def send_attack(
        self,
        origin_x: int,
        origin_y: int,
        target_x: int,
        target_y: int,
        target_area_id: int,  # LID
        kingdom_id: int = 0,
        attack_type: int = 0,  # ATT
        world_type: int = 0,  # WT
        middle_units: Optional[Dict[int, int]] = None,
        left_units: Optional[Dict[int, int]] = None,
        right_units: Optional[Dict[int, int]] = None,
        middle_tools: Optional[Dict[int, int]] = None,
        left_tools: Optional[Dict[int, int]] = None,
        right_tools: Optional[Dict[int, int]] = None,
        wait_for_response: bool = False,
        timeout: float = 5.0,
    ) -> bool:
        """
        Send a detailed attack using the 'cra' command, allowing flank deployment.

        Args:
            origin_x: Source castle X coordinate.
            origin_y: Source castle Y coordinate.
            target_x: Target X coordinate.
            target_y: Target Y coordinate.
            target_area_id: Target Location ID (LID).
            kingdom_id: Kingdom ID (KID, default 0).
            attack_type: Type of attack (ATT, default 0 for regular attack).
            world_type: World type (WT, default 0).
            middle_units: Units for the middle flank ({unit_id: count}).
            left_units: Units for the left flank.
            right_units: Units for the right flank.
            middle_tools: Tools for the middle flank.
            left_tools: Tools for the left flank.
            right_tools: Tools for the right flank.
            wait_for_response: Whether to wait for server confirmation.
            timeout: Response timeout in seconds.

        Returns:
            bool: True if attack sent successfully.

        Raises:
            ActionError: If attack fails or no units/tools are specified.
        """
        logger.info(
            f"Sending detailed attack from ({origin_x},{origin_y}) to ({target_x},{target_y}) LID:{target_area_id}"
        )

        # Ensure at least some units or tools are being sent
        if not any([middle_units, left_units, right_units, middle_tools, left_tools, right_tools]):
            raise ActionError("Must specify at least one unit or tool for attack.")

        # Construct the 'A' (Army) payload
        army_payload = {
            "L": self._build_flank_payload(left_units, left_tools),
            "R": self._build_flank_payload(right_units, right_tools),
            "M": self._build_flank_payload(middle_units, middle_tools),
        }

        # The 'A' field can be a list of these, representing waves. For now, a single wave.
        full_army_payload = [army_payload]

        payload = {
            "SX": origin_x,
            "SY": origin_y,
            "TX": target_x,
            "TY": target_y,
            "KID": kingdom_id,
            "LID": target_area_id,
            "WT": world_type,
            "ATT": attack_type,
            "A": full_army_payload,
            # Other fields from khan.py example can be added as needed or set to default/0
            "HBW": 0,
            "BPC": 0,
            "AV": 0,
            "LP": 1,
            "FC": 0,
            "PTT": 0,
            "SD": 0,
            "ICA": 0,
            "CD": 99,
            "BKS": [],
            "AST": [-1, -1, -1],
            "RW": [[-1, 0], [-1, 0], [-1, 0], [-1, 0], [-1, 0], [-1, 0], [-1, 0], [-1, 0]],
        }

        response = await self._send_command_action("cra", payload, "Detailed Attack", wait_for_response, timeout)

        if wait_for_response:
            return self._parse_action_response(response, "detailed attack")
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

        response = await self._send_command_action("tra", payload, "Transport", wait_for_response, timeout)

        if wait_for_response:
            return self._parse_action_response(response, "transport")
        return True

    async def send_spy(
        self,
        origin_castle_id: int,
        target_area_id: int,
        units: Dict[int, int],
        kingdom_id: int = 0,
        wait_for_response: bool = False,
        timeout: float = 5.0,
    ) -> bool:
        """
        Send spies to a target.

        Args:
            origin_castle_id: ID of attacking castle
            target_area_id: ID of target area
            units: Dictionary of {unit_id: count} (e.g., spies)
            kingdom_id: Kingdom ID (default 0)
            wait_for_response: Wait for server confirmation (default False)
            timeout: Response timeout in seconds (default 5.0)

        Returns:
            bool: True if spies sent successfully

        Raises:
            ActionError: If spy action fails
        """
        logger.info(f"Sending spies from {origin_castle_id} to {target_area_id}")

        if not units or all(count <= 0 for count in units.values()):
            raise ActionError("Must specify at least one unit")

        payload = {
            "OID": origin_castle_id,
            "TID": target_area_id,
            "UN": units,
            "TT": TroopActionType.SPY,
            "KID": kingdom_id,
        }

        response = await self._send_command_action("scl", payload, "Spy", wait_for_response, timeout)

        if wait_for_response:
            return self._parse_action_response(response, "spy")
        return True

    async def collect_taxes(
        self,
        castle_id: int,
        wait_for_response: bool = False,
        timeout: float = 5.0,
    ) -> bool:
        """
        Collect taxes/harvest resources from castle.

        Args:
            castle_id: ID of castle
            wait_for_response: Wait for server confirmation (default False)
            timeout: Response timeout in seconds (default 5.0)

        Returns:
            bool: True if collection successful
        """
        logger.info(f"Collecting taxes from castle {castle_id}")

        payload = {"AID": castle_id}

        response = await self._send_command_action("har", payload, "Harvest", wait_for_response, timeout)

        if wait_for_response:
            return self._parse_action_response(response, "harvest")
        return True

    async def use_item(
        self,
        castle_id: int,
        item_id: int,
        count: int = 1,
        target_id: int = 0,
        wait_for_response: bool = False,
        timeout: float = 5.0,
    ) -> bool:
        """
        Use a consumable item.

        Args:
            castle_id: ID of castle context
            item_id: ID of item to use
            count: Number of items to use
            target_id: Optional target ID (e.g. for specific building or unit boost)
            wait_for_response: Wait for server confirmation
            timeout: Response timeout

        Returns:
            bool: True if item used successfully
        """
        logger.info(f"Using item {item_id} (x{count}) in castle {castle_id}")

        payload = {
            "AID": castle_id,
            "IID": item_id,
            "C": count,
        }
        if target_id:
            payload["TID"] = target_id

        response = await self._send_command_action("itu", payload, "Use Item", wait_for_response, timeout)

        if wait_for_response:
            return self._parse_action_response(response, "use_item")
        return True

    async def upgrade_building(self, castle_id: int, building_id: int, building_type: Optional[int] = None) -> bool:
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

        await self._send_command_action("bui", payload, "Building upgrade")
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

        await self._send_command_action("tru", payload, "Unit recruitment")
        return True

    async def send_support(
        self,
        origin_castle_id: int,
        target_x: int,
        target_y: int,
        kingdom_id: int,
        units: List[List[int]],
        target_location_id: int = -14,
        world_type: int = 12,
        wait_for_response: bool = False,
        timeout: float = 5.0,
    ) -> bool:
        """
        Send troops as support to a location (used for birding troops).

        This uses the 'cds' command which sends troops to a map location
        for support/defense. Commonly used for sending troops to bird
        protection bookmarks.

        Args:
            origin_castle_id: ID of sending castle (SID)
            target_x: Target X coordinate
            target_y: Target Y coordinate
            kingdom_id: Kingdom ID (0=Green, 2=Ice, 1=Sands, 3=Storm, 4=Fire)
            units: List of [unit_id, count] pairs, max 10 per request
            target_location_id: Target location ID (default -14 for bird)
            world_type: World type (default 12)
            wait_for_response: Wait for server confirmation
            timeout: Response timeout in seconds

        Returns:
            bool: True if support sent successfully

        Raises:
            ActionError: If support fails

        Example:
            # Send 100 soldiers (unit 1) and 50 archers (unit 2) to bird
            await client.send_support(
                origin_castle_id=12345,
                target_x=100,
                target_y=200,
                kingdom_id=0,
                units=[[1, 100], [2, 50]]
            )
        """
        logger.info(f"Sending support from castle {origin_castle_id} to ({target_x},{target_y})")

        if not units or len(units) == 0:
            raise ActionError("Must specify at least one unit for support")

        # Limit to 10 units per request (game limitation)
        if len(units) > 10:
            logger.warning(f"Truncating units list from {len(units)} to 10 (max per request)")
            units = units[:10]

        payload = {
            "SID": origin_castle_id,
            "TX": target_x,
            "TY": target_y,
            "LID": target_location_id,
            "WT": world_type,
            "HBW": -1,
            "BPC": 1,
            "PTT": 1,
            "SD": 0,
            "A": units,
            "KID": kingdom_id,
        }

        response = await self._send_command_action("cds", payload, "Support", wait_for_response, timeout)

        if wait_for_response:
            return self._parse_action_response(response, "support")
        return True

    async def get_bookmarks(
        self,
        wait_for_response: bool = True,
        timeout: float = 5.0,
    ) -> Any:
        """
        Get alliance bookmarks.

        This uses the 'gbl' command to retrieve alliance bookmarks,
        which can include bird protection locations.

        Args:
            wait_for_response: Wait for server response
            timeout: Response timeout in seconds

        Returns:
            Bookmark data if wait_for_response, else True
        """
        logger.info("Getting alliance bookmarks")

        response = await self._send_command_action("gbl", {}, "Get bookmarks", wait_for_response, timeout)
        return response
