"""
Army service for EmpireCore.

Provides high-level APIs for:
- Unit production
- Unit inventory management
- Hospital operations
"""

from __future__ import annotations

from empire_core.protocol.models import (
    CancelHealRequest,
    CancelHealResponse,
    CancelProductionRequest,
    CancelProductionResponse,
    DeleteUnitsRequest,
    DeleteUnitsResponse,
    DeleteWoundedRequest,
    DeleteWoundedResponse,
    DoubleProductionRequest,
    DoubleProductionResponse,
    GetProductionQueueRequest,
    GetProductionQueueResponse,
    GetUnitsRequest,
    GetUnitsResponse,
    HealAllRequest,
    HealAllResponse,
    HealUnitsRequest,
    HealUnitsResponse,
    ProduceUnitsRequest,
    ProduceUnitsResponse,
    ProductionQueueItem,
    SkipHealRequest,
    SkipHealResponse,
    UnitCount,
)

from .base import BaseService, register_service


@register_service("army")
class ArmyService(BaseService):
    """
    Service for army operations.

    Accessible via client.army after auto-registration.

    Usage:
        client = EmpireClient(...)

        # Get units
        units = client.army.get_units(castle_id=123)

        # Produce units
        client.army.produce_units(castle_id=123, unit_id=5, count=10)
    """

    # =========================================================================
    # Unit Inventory
    # =========================================================================

    def get_units(self, castle_id: int, timeout: float = 5.0) -> list[UnitCount]:
        """
        Get units inventory for a castle.

        Args:
            castle_id: The castle ID
            timeout: Timeout in seconds

        Returns:
            List of UnitCount objects (both soldiers and tools)
        """
        request = GetUnitsRequest(CID=castle_id)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, GetUnitsResponse):
            # Combine units and tools into a single list
            return response.units + response.tools

        return []

    def delete_units(self, castle_id: int, unit_id: int, count: int, timeout: float = 5.0) -> bool:
        """
        Delete units from inventory.

        Args:
            castle_id: The castle ID
            unit_id: The unit ID to delete
            count: Number of units to delete
            timeout: Timeout in seconds

        Returns:
            True if successful
        """
        request = DeleteUnitsRequest(CID=castle_id, UID=unit_id, C=count)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, DeleteUnitsResponse):
            return response.success

        return False

    # =========================================================================
    # Production
    # =========================================================================

    def produce_units(
        self, castle_id: int, building_id: int, unit_id: int, count: int, list_id: int = 0, timeout: float = 5.0
    ) -> bool:
        """
        Start production of units or tools.

        Args:
            castle_id: The castle ID
            building_id: The barracks/workshop ID
            unit_id: Unit type ID to produce
            count: Amount to produce
            list_id: 0 for soldiers, 1 for tools (default: 0)
            timeout: Timeout in seconds

        Returns:
            True if successful
        """
        request = ProduceUnitsRequest(CID=castle_id, BID=building_id, UID=unit_id, C=count, LID=list_id)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, ProduceUnitsResponse):
            return response.error_code == 0

        return False

    def get_production_queue(
        self, castle_id: int, building_id: int, list_id: int = 0, timeout: float = 5.0
    ) -> list[ProductionQueueItem]:
        """
        Get production queue for a building.

        Args:
            castle_id: The castle ID
            building_id: The barracks/workshop ID
            list_id: 0 for soldiers, 1 for tools (default: 0)
            timeout: Timeout in seconds

        Returns:
            List of ProductionQueueItem objects
        """
        request = GetProductionQueueRequest(CID=castle_id, BID=building_id, LID=list_id)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, GetProductionQueueResponse):
            return response.queue

        return []

    def cancel_production(self, castle_id: int, building_id: int, queue_id: int, timeout: float = 5.0) -> bool:
        """
        Cancel a production queue item.

        Args:
            castle_id: The castle ID
            building_id: The barracks/workshop ID
            queue_id: The queue ID to cancel
            timeout: Timeout in seconds

        Returns:
            True if successful
        """
        request = CancelProductionRequest(CID=castle_id, BID=building_id, QID=queue_id)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, CancelProductionResponse):
            return response.success

        return False

    def double_production_slot(self, castle_id: int, building_id: int, queue_id: int, timeout: float = 5.0) -> bool:
        """
        Double a production slot (produce twice as fast).
        Costs rubies.

        Args:
            castle_id: The castle ID
            building_id: The barracks/workshop ID
            queue_id: The queue ID to double
            timeout: Timeout in seconds

        Returns:
            True if successful
        """
        request = DoubleProductionRequest(CID=castle_id, BID=building_id, QID=queue_id)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, DoubleProductionResponse):
            return response.success

        return False

    # =========================================================================
    # Hospital
    # =========================================================================

    def heal_units(self, castle_id: int, unit_id: int, count: int, timeout: float = 5.0) -> bool:
        """
        Heal wounded units.

        Args:
            castle_id: The castle ID
            unit_id: The unit ID to heal
            count: Amount to heal
            timeout: Timeout in seconds

        Returns:
            True if successful
        """
        request = HealUnitsRequest(CID=castle_id, UID=unit_id, C=count)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, HealUnitsResponse):
            return response.error_code == 0

        return False

    def heal_all(self, castle_id: int, timeout: float = 5.0) -> int:
        """
        Heal all wounded units.

        Args:
            castle_id: The castle ID
            timeout: Timeout in seconds

        Returns:
            Number of units healed (0 on failure)
        """
        request = HealAllRequest(CID=castle_id)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, HealAllResponse):
            return response.units_healed

        return 0

    def cancel_heal(self, castle_id: int, queue_id: int, timeout: float = 5.0) -> bool:
        """
        Cancel healing queue item.

        Args:
            castle_id: The castle ID
            queue_id: The queue ID to cancel
            timeout: Timeout in seconds

        Returns:
            True if successful
        """
        request = CancelHealRequest(CID=castle_id, QID=queue_id)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, CancelHealResponse):
            return response.success

        return False

    def skip_heal_time(self, castle_id: int, queue_id: int, timeout: float = 5.0) -> bool:
        """
        Skip healing time using rubies.

        Args:
            castle_id: The castle ID
            queue_id: The queue ID to skip
            timeout: Timeout in seconds

        Returns:
            True if successful
        """
        request = SkipHealRequest(CID=castle_id, QID=queue_id)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, SkipHealResponse):
            return response.success

        return False

    def delete_wounded(self, castle_id: int, unit_id: int, count: int, timeout: float = 5.0) -> bool:
        """
        Delete wounded units (don't heal them).

        Args:
            castle_id: The castle ID
            unit_id: The unit ID to delete
            count: Amount to delete
            timeout: Timeout in seconds

        Returns:
            True if successful
        """
        request = DeleteWoundedRequest(CID=castle_id, UID=unit_id, C=count)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, DeleteWoundedResponse):
            return response.success

        return False
