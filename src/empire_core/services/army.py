"""
Army service for EmpireCore.

Provides high-level APIs for:
- Unit production
- Unit inventory management
- Hospital operations

Action methods return True when the server accepted the action and False
when it rejected it with an error code; transport failures (timeout,
disconnect) raise. Query methods raise on any failure.
"""

from __future__ import annotations

from empire_core.protocol.models import (
    CancelHealRequest,
    CancelProductionRequest,
    DeleteUnitsRequest,
    DeleteWoundedRequest,
    DoubleProductionRequest,
    GetProductionQueueRequest,
    GetProductionQueueResponse,
    GetUnitsRequest,
    GetUnitsResponse,
    HealAllRequest,
    HealAllResponse,
    HealUnitsRequest,
    ProduceUnitsRequest,
    ProductionQueueItem,
    SkipHealRequest,
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

        Returns:
            List of UnitCount objects (both soldiers and tools)
        """
        response = self.request(GetUnitsRequest(CID=castle_id), GetUnitsResponse, timeout=timeout)
        return response.units + response.tools

    def delete_units(self, castle_id: int, unit_id: int, count: int, timeout: float = 5.0) -> bool:
        """Delete units from inventory."""
        return self.execute(DeleteUnitsRequest(CID=castle_id, UID=unit_id, C=count), timeout=timeout)

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
        """
        request = ProduceUnitsRequest(CID=castle_id, BID=building_id, UID=unit_id, C=count, LID=list_id)
        return self.execute(request, timeout=timeout)

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
        """
        request = GetProductionQueueRequest(CID=castle_id, BID=building_id, LID=list_id)
        return self.request(request, GetProductionQueueResponse, timeout=timeout).queue

    def cancel_production(self, castle_id: int, building_id: int, queue_id: int, timeout: float = 5.0) -> bool:
        """Cancel a production queue item."""
        return self.execute(CancelProductionRequest(CID=castle_id, BID=building_id, QID=queue_id), timeout=timeout)

    def double_production_slot(self, castle_id: int, building_id: int, queue_id: int, timeout: float = 5.0) -> bool:
        """Double a production slot (produce twice as fast). Costs rubies."""
        return self.execute(DoubleProductionRequest(CID=castle_id, BID=building_id, QID=queue_id), timeout=timeout)

    # =========================================================================
    # Hospital
    # =========================================================================

    def heal_units(self, castle_id: int, unit_id: int, count: int, timeout: float = 5.0) -> bool:
        """Heal wounded units."""
        return self.execute(HealUnitsRequest(CID=castle_id, UID=unit_id, C=count), timeout=timeout)

    def heal_all(self, castle_id: int, timeout: float = 5.0) -> int:
        """
        Heal all wounded units.

        Returns:
            Number of units healed
        """
        return self.request(HealAllRequest(CID=castle_id), HealAllResponse, timeout=timeout).units_healed

    def cancel_heal(self, castle_id: int, queue_id: int, timeout: float = 5.0) -> bool:
        """Cancel healing queue item."""
        return self.execute(CancelHealRequest(CID=castle_id, QID=queue_id), timeout=timeout)

    def skip_heal_time(self, castle_id: int, queue_id: int, timeout: float = 5.0) -> bool:
        """Skip healing time using rubies."""
        return self.execute(SkipHealRequest(CID=castle_id, QID=queue_id), timeout=timeout)

    def delete_wounded(self, castle_id: int, unit_id: int, count: int, timeout: float = 5.0) -> bool:
        """Delete wounded units (don't heal them)."""
        return self.execute(DeleteWoundedRequest(CID=castle_id, UID=unit_id, C=count), timeout=timeout)
