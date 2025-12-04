"""
Unit production and army management automation.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from empire_core.state.models import Castle

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class UnitType(IntEnum):
    """Common unit type IDs."""

    # Melee
    MILITIA = 620
    SWORDSMAN = 621
    SPEARMAN = 622
    KNIGHT = 623

    # Ranged
    BOWMAN = 630
    CROSSBOWMAN = 631
    LONGBOWMAN = 632

    # Cavalry
    LIGHT_CAVALRY = 640
    HEAVY_CAVALRY = 641
    LANCER = 642

    # Siege
    BATTERING_RAM = 650
    CATAPULT = 651
    SIEGE_TOWER = 652

    # Defense
    MANTLET = 660
    WALL_DEFENDER = 661

    # Special
    SPY = 670
    COMMANDER = 680


@dataclass
class RecruitmentTask:
    """A unit recruitment task."""

    castle_id: int
    unit_type: int
    count: int
    priority: int = 0


@dataclass
class UnitProductionTarget:
    """Target unit counts for a castle."""

    castle_id: int
    targets: Dict[int, int] = field(default_factory=dict)  # unit_type -> target_count


@dataclass
class ArmyStatus:
    """Current army status for a castle."""

    castle_id: int
    units: Dict[int, int] = field(default_factory=dict)  # unit_type -> count
    total_units: int = 0
    in_production: Dict[int, int] = field(default_factory=dict)


class UnitManager:
    """
    Manages unit production and army composition.

    Features:
    - Production queue management
    - Auto-recruitment based on targets
    - Army composition recommendations
    - Multi-castle coordination
    """

    def __init__(self, client: "EmpireClient"):
        self.client = client
        self.queue: List[RecruitmentTask] = []
        self.targets: Dict[int, UnitProductionTarget] = {}  # castle_id -> targets
        self._auto_recruit_enabled = False
        self._running = False

    @property
    def castles(self) -> Dict[int, Castle]:
        """Get player's castles."""
        player = self.client.state.local_player
        if player:
            return player.castles
        return {}

    def set_target(self, castle_id: int, unit_type: int, count: int):
        """
        Set target unit count for a castle.

        Args:
            castle_id: Castle ID
            unit_type: Unit type ID
            count: Target number of units
        """
        if castle_id not in self.targets:
            self.targets[castle_id] = UnitProductionTarget(castle_id=castle_id)

        self.targets[castle_id].targets[unit_type] = count
        logger.info(f"Set target: Castle {castle_id}, Unit {unit_type}, Count {count}")

    def set_army_composition(
        self,
        castle_id: int,
        composition: Dict[int, int],
    ):
        """
        Set complete army composition target.

        Args:
            castle_id: Castle ID
            composition: Dict of {unit_type: count}
        """
        self.targets[castle_id] = UnitProductionTarget(
            castle_id=castle_id,
            targets=composition.copy(),
        )
        logger.info(f"Set army composition for castle {castle_id}")

    def clear_targets(self, castle_id: Optional[int] = None):
        """Clear production targets."""
        if castle_id:
            self.targets.pop(castle_id, None)
        else:
            self.targets.clear()

    def add_task(
        self,
        castle_id: int,
        unit_type: int,
        count: int,
        priority: int = 0,
    ) -> RecruitmentTask:
        """Add a recruitment task to the queue."""
        task = RecruitmentTask(
            castle_id=castle_id,
            unit_type=unit_type,
            count=count,
            priority=priority,
        )
        self.queue.append(task)
        self._sort_queue()
        logger.info(
            f"Added recruitment: {count}x Unit {unit_type} in Castle {castle_id}"
        )
        return task

    def remove_task(self, castle_id: int, unit_type: int) -> bool:
        """Remove a task from the queue."""
        for i, task in enumerate(self.queue):
            if task.castle_id == castle_id and task.unit_type == unit_type:
                self.queue.pop(i)
                return True
        return False

    def clear_queue(self, castle_id: Optional[int] = None):
        """Clear recruitment queue."""
        if castle_id:
            self.queue = [t for t in self.queue if t.castle_id != castle_id]
        else:
            self.queue.clear()

    def get_army_status(self, castle_id: int) -> Optional[ArmyStatus]:
        """Get current army status for a castle."""
        # Get from state manager
        army = self.client.state.armies.get(castle_id)
        if not army:
            return ArmyStatus(castle_id=castle_id)

        units = army.units.copy()
        total = sum(units.values())

        return ArmyStatus(
            castle_id=castle_id,
            units=units,
            total_units=total,
        )

    def get_deficit(self, castle_id: int) -> Dict[int, int]:
        """
        Get unit deficit compared to targets.

        Returns:
            Dict of {unit_type: deficit_count}
        """
        deficit = {}
        target = self.targets.get(castle_id)
        if not target:
            return deficit

        status = self.get_army_status(castle_id)
        current_units = status.units if status else {}

        for unit_type, target_count in target.targets.items():
            current = current_units.get(unit_type, 0)
            if current < target_count:
                deficit[unit_type] = target_count - current

        return deficit

    def calculate_recruitment_tasks(
        self, castle_id: Optional[int] = None
    ) -> List[RecruitmentTask]:
        """
        Calculate recruitment tasks needed to meet targets.

        Args:
            castle_id: Specific castle or None for all

        Returns:
            List of RecruitmentTask objects
        """
        tasks = []
        castle_ids = [castle_id] if castle_id else list(self.targets.keys())

        for cid in castle_ids:
            deficit = self.get_deficit(cid)
            for unit_type, count in deficit.items():
                if count > 0:
                    tasks.append(
                        RecruitmentTask(
                            castle_id=cid,
                            unit_type=unit_type,
                            count=count,
                        )
                    )

        return tasks

    async def execute_task(self, task: RecruitmentTask) -> bool:
        """Execute a recruitment task."""
        try:
            success = await self.client.recruit_units(
                castle_id=task.castle_id,
                unit_id=task.unit_type,
                count=task.count,
            )

            if success:
                # Remove from queue
                self.queue = [
                    t
                    for t in self.queue
                    if not (
                        t.castle_id == task.castle_id and t.unit_type == task.unit_type
                    )
                ]
                logger.info(
                    f"Started recruitment: {task.count}x Unit {task.unit_type} "
                    f"in Castle {task.castle_id}"
                )

            return bool(success)
        except Exception as e:
            logger.error(f"Recruitment failed: {e}")
            return False

    async def process_queue(self) -> int:
        """Process the recruitment queue."""
        if not self.queue:
            return 0

        executed = 0
        for task in self.queue[:]:  # Copy to allow modification
            success = await self.execute_task(task)
            if success:
                executed += 1
            await asyncio.sleep(0.5)  # Rate limit

        return executed

    async def auto_recruit(self) -> int:
        """
        Automatically recruit units to meet targets.

        Returns:
            Number of recruitment tasks executed
        """
        # Calculate needed recruitments
        tasks = self.calculate_recruitment_tasks()

        if not tasks:
            logger.debug("No recruitment needed")
            return 0

        # Execute tasks
        executed = 0
        for task in tasks:
            success = await self.execute_task(task)
            if success:
                executed += 1
            await asyncio.sleep(0.5)

        logger.info(f"Auto-recruit: executed {executed} tasks")
        return executed

    async def start_auto_recruit(self, interval: int = 120):
        """
        Start automatic recruitment.

        Args:
            interval: Check interval in seconds
        """
        self._auto_recruit_enabled = True
        self._running = True

        logger.info(f"Auto-recruit started (interval: {interval}s)")

        while self._running and self._auto_recruit_enabled:
            try:
                await self.auto_recruit()
            except Exception as e:
                logger.error(f"Auto-recruit error: {e}")

            await asyncio.sleep(interval)

    def stop_auto_recruit(self):
        """Stop automatic recruitment."""
        self._auto_recruit_enabled = False
        self._running = False
        logger.info("Auto-recruit stopped")

    def get_summary(self) -> Dict[str, Any]:
        """Get recruitment summary."""
        return {
            "queue_length": len(self.queue),
            "castles_with_targets": len(self.targets),
            "total_deficit": sum(
                sum(self.get_deficit(cid).values()) for cid in self.targets
            ),
        }

    def recommend_composition(
        self, focus: str = "balanced", size: int = 500
    ) -> Dict[int, int]:
        """
        Recommend army composition.

        Args:
            focus: "balanced", "attack", "defense", "farming"
            size: Total army size

        Returns:
            Dict of {unit_type: count}
        """
        if focus == "attack":
            return {
                UnitType.SWORDSMAN: int(size * 0.3),
                UnitType.KNIGHT: int(size * 0.2),
                UnitType.CROSSBOWMAN: int(size * 0.2),
                UnitType.HEAVY_CAVALRY: int(size * 0.2),
                UnitType.CATAPULT: int(size * 0.1),
            }
        elif focus == "defense":
            return {
                UnitType.SPEARMAN: int(size * 0.3),
                UnitType.CROSSBOWMAN: int(size * 0.3),
                UnitType.WALL_DEFENDER: int(size * 0.2),
                UnitType.MANTLET: int(size * 0.2),
            }
        elif focus == "farming":
            return {
                UnitType.MILITIA: int(size * 0.5),
                UnitType.SWORDSMAN: int(size * 0.3),
                UnitType.BOWMAN: int(size * 0.2),
            }
        else:  # balanced
            return {
                UnitType.SWORDSMAN: int(size * 0.25),
                UnitType.SPEARMAN: int(size * 0.15),
                UnitType.CROSSBOWMAN: int(size * 0.2),
                UnitType.KNIGHT: int(size * 0.15),
                UnitType.LIGHT_CAVALRY: int(size * 0.15),
                UnitType.CATAPULT: int(size * 0.1),
            }

    def _sort_queue(self):
        """Sort queue by priority."""
        self.queue.sort(key=lambda t: t.priority, reverse=True)
