"""
Resource management and auto-balancing between castles.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from empire_core.state.models import Castle

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


@dataclass
class ResourceTransfer:
    """A pending resource transfer."""

    source_castle_id: int
    target_castle_id: int
    wood: int = 0
    stone: int = 0
    food: int = 0

    @property
    def total(self) -> int:
        return self.wood + self.stone + self.food

    @property
    def is_empty(self) -> bool:
        return self.total == 0


@dataclass
class CastleResourceStatus:
    """Resource status of a castle."""

    castle_id: int
    castle_name: str
    wood: int
    stone: int
    food: int
    wood_cap: int
    stone_cap: int
    food_cap: int
    wood_rate: float
    stone_rate: float
    food_rate: float

    @property
    def wood_percent(self) -> float:
        return (self.wood / self.wood_cap * 100) if self.wood_cap > 0 else 0

    @property
    def stone_percent(self) -> float:
        return (self.stone / self.stone_cap * 100) if self.stone_cap > 0 else 0

    @property
    def food_percent(self) -> float:
        return (self.food / self.food_cap * 100) if self.food_cap > 0 else 0

    @property
    def is_near_capacity(self) -> bool:
        """Check if any resource is above 90% capacity."""
        return self.wood_percent > 90 or self.stone_percent > 90 or self.food_percent > 90

    @property
    def is_low(self) -> bool:
        """Check if any resource is below 20% capacity."""
        return self.wood_percent < 20 or self.stone_percent < 20 or self.food_percent < 20

    def get_excess(self, threshold_percent: float = 70) -> Dict[str, int]:
        """Get excess resources above threshold."""
        excess = {}
        threshold_wood = int(self.wood_cap * threshold_percent / 100)
        threshold_stone = int(self.stone_cap * threshold_percent / 100)
        threshold_food = int(self.food_cap * threshold_percent / 100)

        if self.wood > threshold_wood:
            excess["wood"] = self.wood - threshold_wood
        if self.stone > threshold_stone:
            excess["stone"] = self.stone - threshold_stone
        if self.food > threshold_food:
            excess["food"] = self.food - threshold_food

        return excess

    def get_deficit(self, threshold_percent: float = 50) -> Dict[str, int]:
        """Get resource deficit below threshold."""
        deficit = {}
        threshold_wood = int(self.wood_cap * threshold_percent / 100)
        threshold_stone = int(self.stone_cap * threshold_percent / 100)
        threshold_food = int(self.food_cap * threshold_percent / 100)

        if self.wood < threshold_wood:
            deficit["wood"] = threshold_wood - self.wood
        if self.stone < threshold_stone:
            deficit["stone"] = threshold_stone - self.stone
        if self.food < threshold_food:
            deficit["food"] = threshold_food - self.food

        return deficit


class ResourceManager:
    """
    Manages resources across multiple castles.

    Features:
    - Monitor resource levels across all castles
    - Auto-balance resources between castles
    - Priority-based resource allocation
    - Overflow protection (send resources before cap)
    """

    # Default thresholds
    OVERFLOW_THRESHOLD = 85  # Send resources when above this %
    LOW_THRESHOLD = 30  # Castle needs resources when below this %
    TARGET_THRESHOLD = 60  # Target level after balancing

    def __init__(self, client: "EmpireClient"):
        self.client = client
        self._auto_balance_enabled = False
        self._balance_interval = 300  # 5 minutes
        self._running = False
        self._priority_castles: List[int] = []  # Castles that get resources first

    @property
    def castles(self) -> Dict[int, Castle]:
        """Get player's castles."""
        player = self.client.state.local_player
        if player:
            return player.castles
        return {}

    def set_priority_castle(self, castle_id: int):
        """Set a castle as high priority for receiving resources."""
        if castle_id not in self._priority_castles:
            self._priority_castles.append(castle_id)

    def remove_priority_castle(self, castle_id: int):
        """Remove castle from priority list."""
        if castle_id in self._priority_castles:
            self._priority_castles.remove(castle_id)

    def get_castle_status(self, castle_id: int) -> Optional[CastleResourceStatus]:
        """Get resource status for a specific castle."""
        castle = self.castles.get(castle_id)
        if not castle:
            return None

        r = castle.resources
        return CastleResourceStatus(
            castle_id=castle_id,
            castle_name=castle.name,
            wood=r.wood,
            stone=r.stone,
            food=r.food,
            wood_cap=r.wood_cap,
            stone_cap=r.stone_cap,
            food_cap=r.food_cap,
            wood_rate=r.wood_rate,
            stone_rate=r.stone_rate,
            food_rate=r.food_rate,
        )

    def get_all_status(self) -> List[CastleResourceStatus]:
        """Get resource status for all castles."""
        statuses = []
        for castle_id in self.castles:
            status = self.get_castle_status(castle_id)
            if status:
                statuses.append(status)
        return statuses

    def get_overflow_castles(self, threshold: float = OVERFLOW_THRESHOLD) -> List[CastleResourceStatus]:
        """Get castles with resources above threshold."""
        return [
            s
            for s in self.get_all_status()
            if s.wood_percent > threshold or s.stone_percent > threshold or s.food_percent > threshold
        ]

    def get_low_castles(self, threshold: float = LOW_THRESHOLD) -> List[CastleResourceStatus]:
        """Get castles with resources below threshold."""
        return [
            s
            for s in self.get_all_status()
            if s.wood_percent < threshold or s.stone_percent < threshold or s.food_percent < threshold
        ]

    def calculate_transfers(
        self,
        overflow_threshold: float = OVERFLOW_THRESHOLD,
        low_threshold: float = LOW_THRESHOLD,
        target_threshold: float = TARGET_THRESHOLD,
    ) -> List[ResourceTransfer]:
        """
        Calculate optimal resource transfers between castles.

        Returns:
            List of ResourceTransfer objects
        """
        transfers: List[ResourceTransfer] = []
        statuses = self.get_all_status()

        if len(statuses) < 2:
            return transfers  # Need at least 2 castles to balance

        # Find sources (overflow) and targets (low)
        sources = []
        targets = []

        for status in statuses:
            excess = status.get_excess(overflow_threshold)
            deficit = status.get_deficit(low_threshold)

            if excess:
                sources.append((status, excess))
            if deficit:
                targets.append((status, deficit))

        # Prioritize targets
        for castle_id in self._priority_castles:
            for i, (status, deficit) in enumerate(targets):
                if status.castle_id == castle_id:
                    targets.insert(0, targets.pop(i))
                    break

        # Match sources to targets
        for target_status, deficit in targets:
            for source_status, excess in sources:
                if source_status.castle_id == target_status.castle_id:
                    continue  # Can't transfer to self

                transfer = ResourceTransfer(
                    source_castle_id=source_status.castle_id,
                    target_castle_id=target_status.castle_id,
                )

                # Calculate transfer amounts
                for resource in ["wood", "stone", "food"]:
                    if resource in deficit and resource in excess:
                        # Transfer minimum of excess and deficit
                        amount = min(deficit[resource], excess[resource])
                        setattr(transfer, resource, amount)
                        # Update tracking
                        deficit[resource] -= amount
                        excess[resource] -= amount

                if not transfer.is_empty:
                    transfers.append(transfer)

        return transfers

    async def execute_transfer(self, transfer: ResourceTransfer) -> bool:
        """Execute a resource transfer."""
        if transfer.is_empty:
            return False

        try:
            success = await self.client.send_transport(
                origin_castle_id=transfer.source_castle_id,
                target_area_id=transfer.target_castle_id,
                wood=transfer.wood,
                stone=transfer.stone,
                food=transfer.food,
            )
            if success:
                logger.info(
                    f"Transferred {transfer.wood}W/{transfer.stone}S/{transfer.food}F "
                    f"from {transfer.source_castle_id} to {transfer.target_castle_id}"
                )
            return bool(success)
        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            return False

    async def auto_balance(self) -> int:
        """
        Automatically balance resources across castles.

        Returns:
            Number of transfers executed
        """
        # Refresh castle data first
        await self.client.get_detailed_castle_info()
        await asyncio.sleep(1)  # Wait for response

        transfers = self.calculate_transfers()

        if not transfers:
            logger.debug("No resource transfers needed")
            return 0

        executed = 0
        for transfer in transfers:
            success = await self.execute_transfer(transfer)
            if success:
                executed += 1
            await asyncio.sleep(0.5)  # Rate limit

        logger.info(f"Executed {executed}/{len(transfers)} resource transfers")
        return executed

    async def start_auto_balance(self, interval: int = 300):
        """
        Start automatic resource balancing.

        Args:
            interval: Balance check interval in seconds
        """
        self._auto_balance_enabled = True
        self._balance_interval = interval
        self._running = True

        logger.info(f"Auto-balance started (interval: {interval}s)")

        while self._running and self._auto_balance_enabled:
            try:
                await self.auto_balance()
            except Exception as e:
                logger.error(f"Auto-balance error: {e}")

            await asyncio.sleep(self._balance_interval)

    def stop_auto_balance(self):
        """Stop automatic resource balancing."""
        self._auto_balance_enabled = False
        self._running = False
        logger.info("Auto-balance stopped")

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of resource status across all castles."""
        statuses = self.get_all_status()

        if not statuses:
            return {"castle_count": 0}

        total_wood = sum(s.wood for s in statuses)
        total_stone = sum(s.stone for s in statuses)
        total_food = sum(s.food for s in statuses)
        total_wood_cap = sum(s.wood_cap for s in statuses)
        total_stone_cap = sum(s.stone_cap for s in statuses)
        total_food_cap = sum(s.food_cap for s in statuses)

        return {
            "castle_count": len(statuses),
            "total_wood": total_wood,
            "total_stone": total_stone,
            "total_food": total_food,
            "total_capacity": {
                "wood": total_wood_cap,
                "stone": total_stone_cap,
                "food": total_food_cap,
            },
            "overall_percent": {
                "wood": (total_wood / total_wood_cap * 100) if total_wood_cap > 0 else 0,
                "stone": (total_stone / total_stone_cap * 100) if total_stone_cap > 0 else 0,
                "food": (total_food / total_food_cap * 100) if total_food_cap > 0 else 0,
            },
            "overflow_castles": len(self.get_overflow_castles()),
            "low_castles": len(self.get_low_castles()),
            "priority_castles": self._priority_castles.copy(),
        }

    def format_status(self) -> str:
        """Format resource status as readable string."""
        lines = ["Resource Status:"]
        for status in self.get_all_status():
            lines.append(
                f"  {status.castle_name}:"
                f" W:{status.wood:,}/{status.wood_cap:,} ({status.wood_percent:.0f}%)"
                f" S:{status.stone:,}/{status.stone_cap:,} ({status.stone_percent:.0f}%)"
                f" F:{status.food:,}/{status.food_cap:,} ({status.food_percent:.0f}%)"
            )
        return "\n".join(lines)
