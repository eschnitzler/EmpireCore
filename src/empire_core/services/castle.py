"""
Castle service for EmpireCore.

Provides high-level APIs for:
- Castle management (list, select, rename, relocate)
- Resource information
- Production rates

Action methods return True when the server accepted the action and False
when it rejected it with an error code; transport failures (timeout,
disconnect) raise. Query methods raise on any failure.
"""

from __future__ import annotations

from empire_core.protocol.models import (
    CastleInfo,
    DetailedCastleInfo,
    GetCastlesRequest,
    GetCastlesResponse,
    GetDetailedCastleRequest,
    GetDetailedCastleResponse,
    GetProductionRequest,
    GetProductionResponse,
    GetResourcesRequest,
    GetResourcesResponse,
    ProductionRates,
    RenameCastleRequest,
    ResourceAmount,
    SelectCastleRequest,
    SendSupportRequest,
)

from .base import BaseService, register_service


@register_service("castle")
class CastleService(BaseService):
    """
    Service for castle operations.

    Accessible via client.castle after auto-registration.

    Usage:
        client = EmpireClient(...)
        client.login()

        # Get all castles
        castles = client.castle.get_all()
        for c in castles:
            print(f"{c.castle_name} at ({c.x}, {c.y})")

        # Select a castle
        client.castle.select(castle_id=12345)

        # Get resources
        resources = client.castle.get_resources(castle_id=12345)
    """

    # =========================================================================
    # Castle List Operations
    # =========================================================================

    def get_all(self, timeout: float = 5.0) -> list[CastleInfo]:
        """
        Get list of all player's castles.

        Example:
            castles = client.castle.get_all()
            for c in castles:
                print(f"{c.castle_name} (ID: {c.castle_id}) at ({c.x}, {c.y})")
        """
        return self.request(GetCastlesRequest(), GetCastlesResponse, timeout=timeout).castles

    def get_details(self, castle_id: int, timeout: float = 5.0) -> DetailedCastleInfo | None:
        """
        Get detailed information about a specific castle.

        Example:
            details = client.castle.get_details(12345)
            if details:
                print(f"Buildings: {len(details.buildings)}")
        """
        request = GetDetailedCastleRequest(CID=castle_id)
        return self.request(request, GetDetailedCastleResponse, timeout=timeout).castle

    # =========================================================================
    # Castle Selection
    # =========================================================================

    def select(self, castle_id: int, kingdom_id: int = 0, timeout: float = 5.0) -> bool:
        """
        Select/jump to a castle (makes it the active castle).

        Example:
            if client.castle.select(12345, kingdom_id=2):
                print("Castle selected!")
        """
        return self.execute(SelectCastleRequest(CID=castle_id, KID=kingdom_id), timeout=timeout)

    # =========================================================================
    # Castle Modification
    # =========================================================================

    def rename(self, castle_id: int, new_name: str, timeout: float = 5.0) -> bool:
        """
        Rename a castle.

        Example:
            if client.castle.rename(12345, "My Fortress"):
                print("Castle renamed!")
        """
        return self.execute(RenameCastleRequest(CID=castle_id, CN=new_name), timeout=timeout)

    # =========================================================================
    # Resource Operations
    # =========================================================================

    def get_resources(self, castle_id: int, timeout: float = 5.0) -> ResourceAmount | None:
        """
        Get current resources for a castle.

        Example:
            resources = client.castle.get_resources(12345)
            if resources:
                print(f"Wood: {resources.wood}")
        """
        return self.request(GetResourcesRequest(CID=castle_id), GetResourcesResponse, timeout=timeout).resources

    def get_production(
        self, castle_id: int, timeout: float = 5.0
    ) -> tuple[ProductionRates | None, ProductionRates | None]:
        """
        Get production and consumption rates for a castle.

        Returns:
            Tuple of (production_rates, consumption_rates)

        Example:
            production, consumption = client.castle.get_production(12345)
            if production:
                print(f"Wood/hr: {production.wood}")
        """
        response = self.request(GetProductionRequest(CID=castle_id), GetProductionResponse, timeout=timeout)
        return response.production, response.consumption

    # =========================================================================
    # Support Operations
    # =========================================================================

    def send_support(
        self,
        source_castle_id: int,
        target_x: int,
        target_y: int,
        units: list[list[int]],
        kingdom_id: int = 0,
        wait_time: int = 12,
        boost_with_coins: bool = True,
        horses_type: int = -1,
        feathers: int = 1,
        slowdown: int = 0,
        lord_id: int = -14,
        timeout: float = 5.0,
    ) -> bool:
        """
        Send support troops from a castle to a target location.

        Args:
            source_castle_id: Source castle ID
            target_x: Target X coordinate
            target_y: Target Y coordinate
            units: List of [unit_id, count] pairs
            kingdom_id: Target kingdom ID (0=Green, 2=Ice, 1=Sand, 3=Fire, default: 0)
            wait_time: Station duration in hours (0-12, default: 12)
            boost_with_coins: Use coins to speed up travel (default: True)
            horses_type: Type of horses for speed bonus (-1 = none, default: -1)
            feathers: Use feathers for speed boost (1 = use, 0 = don't, default: 1)
            slowdown: Movement slowdown modifier (0 = none, default: 0)
            lord_id: Lord/General ID (-14 = coordinates/no lord, default: -14)
            timeout: Timeout in seconds
        """
        request = SendSupportRequest(
            SID=source_castle_id,
            TX=target_x,
            TY=target_y,
            KID=kingdom_id,
            A=units,
            WT=wait_time,
            BPC=1 if boost_with_coins else 0,
            HBW=horses_type,
            PTT=feathers,
            SD=slowdown,
            LID=lord_id,
        )
        return self.execute(request, timeout=timeout)


__all__ = ["CastleService"]
