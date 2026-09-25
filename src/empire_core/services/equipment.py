"""
Equipment service for EmpireCore.

Reads the equipment inventory and moves items on and off commanders and castellans.
"""

from __future__ import annotations

import logging

from empire_core.protocol.models import (
    EquipEquipmentRequest,
    Equipment,
    GetEquipmentInventoryRequest,
    GetEquipmentInventoryResponse,
)

from .base import BaseService, register_service

logger = logging.getLogger(__name__)


@register_service("equipment")
class EquipmentService(BaseService):
    """
    Service for equipment operations.

    Accessible via client.equipment after auto-registration. What a leader
    wears comes with ``client.commanders`` (``gli`` ``EQ``).
    """

    def get_inventory(self, timeout: float = 5.0) -> list[Equipment]:
        """
        The items in the player's inventory, the ones no leader wears.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError on failure
        """
        return self.request(GetEquipmentInventoryRequest(), GetEquipmentInventoryResponse, timeout=timeout).items

    def equip(self, equipment_id: int, commander_id: int, timeout: float = 5.0) -> bool:
        """
        Put an item on a commander or castellan.

        The client moves an item between leaders by taking it off the first
        and then putting it on the second. The reply carries no data; re-read
        ``client.commanders.get_all()`` to see the change.

        Returns:
            False when the server rejects the request
        """
        request = EquipEquipmentRequest(EID=equipment_id, LID=commander_id, E=1)
        return self.execute(request, timeout=timeout)

    def unequip(self, equipment_id: int, commander_id: int, timeout: float = 5.0) -> bool:
        """
        Take an item off a commander or castellan.

        Returns:
            False when the server rejects the request
        """
        request = EquipEquipmentRequest(EID=equipment_id, LID=commander_id, E=0)
        return self.execute(request, timeout=timeout)
