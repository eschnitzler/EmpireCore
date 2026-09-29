"""
Equipment service for EmpireCore.

Reads the equipment inventory and moves items on and off commanders and castellans.
"""

from __future__ import annotations

import logging

from empire_core.commanders.models.equipment import (
    EquipEquipmentRequest,
    Equipment,
    GetEquipmentInventoryRequest,
    GetEquipmentInventoryResponse,
)
from empire_core.services.base import BaseService, register_service

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

        Args:
            equipment_id: An item in the inventory, its ``Equipment.equipment_id``
                from :meth:`get_inventory`
            commander_id: The leader's ``commander_id``, a ``Commander`` or ``Castellan``
                from ``client.commanders.get_all()``
            timeout: Timeout in seconds

        Returns:
            False when the server rejects the request
        """
        request = EquipEquipmentRequest(EID=equipment_id, LID=commander_id, E=1)
        return self.execute(request, timeout=timeout)

    def unequip(self, equipment_id: int, commander_id: int, timeout: float = 5.0) -> bool:
        """
        Take an item off a commander or castellan.

        Args:
            equipment_id: An item the leader wears, the ``Equipment.equipment_id`` of an
                entry in its ``equipment`` list from ``client.commanders.get_all()``
            commander_id: The leader's ``commander_id``, a ``Commander`` or ``Castellan``
                from ``client.commanders.get_all()``
            timeout: Timeout in seconds

        Returns:
            False when the server rejects the request
        """
        request = EquipEquipmentRequest(EID=equipment_id, LID=commander_id, E=0)
        return self.execute(request, timeout=timeout)
