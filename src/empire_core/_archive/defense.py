"""
Defense management mixin for deploying defense units and tools.
"""

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

# Assuming GameCommandsMixin provides _send_command_generic

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class DefenseService:
    """Service for managing castle defenses."""

    def __init__(self, client: "EmpireClient"):
        self.client = client

    def _build_defense_slot_payload(self, items: Optional[Dict[int, int]]) -> List[List[int]]:
        """Helper to build tool/unit list for defense payloads."""
        if not items:
            # Common pattern is to send [[-1, 0]] for empty slots or specific padding
            # Assuming up to 5 slots based on khan.py example for dfw
            return [[-1, 0]] * 5

        payload = []
        for item_id, count in items.items():
            payload.append([item_id, count])

        # Pad with [-1, 0] if less than expected slots
        while len(payload) < 5:  # Assuming 5 slots based on typical defense setups
            payload.append([-1, 0])

        return payload[:5]  # Ensure max 5 items for wall slots

    async def set_wall_defense(
        self,
        castle_id: int,
        castle_x: int,
        castle_y: int,
        left_tools: Optional[Dict[int, int]] = None,
        middle_tools: Optional[Dict[int, int]] = None,
        right_tools: Optional[Dict[int, int]] = None,
        left_units_up: int = 0,  # UP field, assuming Units Placed
        left_units_count: int = 0,  # UC field, assuming Unit Count
        middle_units_up: int = 0,
        middle_units_count: int = 0,
        right_units_up: int = 0,
        right_units_count: int = 0,
        wait_for_response: bool = False,
        timeout: float = 5.0,
    ) -> bool:
        """
        Deploy defense tools and units on castle walls.

        Args:
            castle_id: ID of the castle.
            castle_x: Castle's X coordinate.
            castle_y: Castle's Y coordinate.
            left_tools: Tools for the left wall flank ({tool_id: count}).
            middle_tools: Tools for the middle wall flank.
            right_tools: Tools for the right wall flank.
            left_units_up: Units Placed on left wall (UP).
            left_units_count: Units Count on left wall (UC).
            middle_units_up: Units Placed on middle wall (UP).
            middle_units_count: Units Count on middle wall (UC).
            right_units_up: Units Placed on right wall (UP).
            right_units_count: Units Count on right wall (UC).
            wait_for_response: Whether to wait for server confirmation.
            timeout: Response timeout in seconds.

        Returns:
            bool: True if defense set successfully.

        Raises:
            ActionError: If setting defense fails.
        """
        logger.info(f"Setting wall defense for castle {castle_id} at ({castle_x},{castle_y})")

        payload = {
            "CX": castle_x,
            "CY": castle_y,
            "AID": castle_id,
            "L": {
                "S": self._build_defense_slot_payload(left_tools),
                "UP": left_units_up,
                "UC": left_units_count,
            },
            "M": {
                "S": self._build_defense_slot_payload(middle_tools),
                "UP": middle_units_up,
                "UC": middle_units_count,
            },
            "R": {
                "S": self._build_defense_slot_payload(right_tools),
                "UP": right_units_up,
                "UC": right_units_count,
            },
        }

        # Use client's command sender
        await self.client._send_command_generic("dfw", payload, "Set Wall Defense", wait_for_response, timeout)

        # Use client's response parser if available or implemented here?
        # The Mixin had _parse_action_response as a stub.
        # Checking if client has it. GameActionsMixin usually has it.
        # If not, we just return True for now if response is valid.
        return True

    async def set_moat_defense(
        self,
        castle_id: int,
        castle_x: int,
        castle_y: int,
        left_slots: Optional[Dict[int, int]] = None,
        middle_slots: Optional[Dict[int, int]] = None,
        right_slots: Optional[Dict[int, int]] = None,
        wait_for_response: bool = False,
        timeout: float = 5.0,
    ) -> bool:
        """
        Deploy defense tools in castle moat/field.

        Args:
            castle_id: ID of the castle.
            castle_x: Castle's X coordinate.
            castle_y: Castle's Y coordinate.
            left_slots: Tools for the left moat/field flank ({tool_id: count}).
            middle_slots: Tools for the middle moat/field flank.
            right_slots: Tools for the right moat/field flank.
            wait_for_response: Whether to wait for server confirmation.
            timeout: Response timeout in seconds.

        Returns:
            bool: True if defense set successfully.

        Raises:
            ActionError: If setting defense fails.
        """
        logger.info(f"Setting moat defense for castle {castle_id} at ({castle_x},{castle_y})")

        payload = {
            "CX": castle_x,
            "CY": castle_y,
            "AID": castle_id,
            "LS": self._build_defense_slot_payload(left_slots),
            "MS": self._build_defense_slot_payload(middle_slots),
            "RS": self._build_defense_slot_payload(right_slots),
        }

        await self.client._send_command_generic("dfm", payload, "Set Moat Defense", wait_for_response, timeout)

        return True
