"""
Building queue management and automation.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from empire_core.state.models import Castle

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class BuildingType(IntEnum):
    """Common building type IDs."""

    # Resource production
    WOODCUTTER = 1
    QUARRY = 2
    FARM = 3

    # Storage
    WAREHOUSE = 4

    # Military
    BARRACKS = 5
    ARCHERY_RANGE = 6
    STABLE = 7
    SIEGE_WORKSHOP = 8
    DEFENSE_WORKSHOP = 9

    # Other
    KEEP = 10
    TAVERN = 11
    MARKETPLACE = 12
    HOSPITAL = 13
    WALL = 14


@dataclass
class BuildingTask:
    """A building task in the queue."""

    castle_id: int
    building_id: int
    building_type: Optional[int] = None
    target_level: int = 1
    priority: int = 0
    cost_wood: int = 0
    cost_stone: int = 0
    cost_food: int = 0


@dataclass
class BuildingStatus:
    """Status of a building."""

    building_id: int
    building_type: int
    level: int
    is_upgrading: bool = False
    upgrade_time_remaining: int = 0


class BuildingManager:
    """
    Manages building upgrades and construction.

    Features:
    - Priority-based build queue
    - Auto-upgrade when resources available
    - Build order recommendations
    - Progress tracking
    """

    def __init__(self, client: "EmpireClient"):
        self.client = client
        self.queue: List[BuildingTask] = []
        self.in_progress: Dict[int, BuildingTask] = {}  # castle_id -> active task
        self._auto_build_enabled = False
        self._running = False

    @property
    def castles(self) -> Dict[int, Castle]:
        """Get player's castles."""
        player = self.client.state.local_player
        if player:
            return player.castles
        return {}

    def add_task(
        self,
        castle_id: int,
        building_id: int,
        building_type: Optional[int] = None,
        target_level: int = 1,
        priority: int = 0,
    ) -> BuildingTask:
        """
        Add a building task to the queue.

        Args:
            castle_id: Castle to build in
            building_id: Building slot ID
            building_type: Type of building (for new construction)
            target_level: Target level to reach
            priority: Higher = built first

        Returns:
            The created BuildingTask
        """
        task = BuildingTask(
            castle_id=castle_id,
            building_id=building_id,
            building_type=building_type,
            target_level=target_level,
            priority=priority,
        )
        self.queue.append(task)
        self._sort_queue()
        logger.info(
            f"Added build task: Castle {castle_id}, Building {building_id}, "
            f"Target Level {target_level}, Priority {priority}"
        )
        return task

    def add_upgrade_all(
        self,
        castle_id: int,
        building_type: int,
        target_level: int,
        priority: int = 0,
    ):
        """
        Add tasks to upgrade all buildings of a type to target level.

        Args:
            castle_id: Castle ID
            building_type: Type of buildings to upgrade
            target_level: Target level
            priority: Task priority
        """
        castle = self.castles.get(castle_id)
        if not castle:
            logger.warning(f"Castle {castle_id} not found")
            return

        for building in castle.buildings:
            if building.id == building_type and building.level < target_level:
                self.add_task(
                    castle_id=castle_id,
                    building_id=building.id,
                    target_level=target_level,
                    priority=priority,
                )

    def remove_task(self, castle_id: int, building_id: int) -> bool:
        """Remove a task from the queue."""
        for i, task in enumerate(self.queue):
            if task.castle_id == castle_id and task.building_id == building_id:
                self.queue.pop(i)
                logger.info(f"Removed task: Castle {castle_id}, Building {building_id}")
                return True
        return False

    def clear_queue(self, castle_id: Optional[int] = None):
        """Clear the build queue, optionally for a specific castle."""
        if castle_id:
            self.queue = [t for t in self.queue if t.castle_id != castle_id]
        else:
            self.queue.clear()
        logger.info(f"Cleared build queue for castle {castle_id or 'all'}")

    def get_next_task(self, castle_id: Optional[int] = None) -> Optional[BuildingTask]:
        """Get the next task to execute."""
        if not self.queue:
            return None

        if castle_id:
            for task in self.queue:
                if task.castle_id == castle_id:
                    return task
            return None

        return self.queue[0]

    def get_queue_for_castle(self, castle_id: int) -> List[BuildingTask]:
        """Get all queued tasks for a castle."""
        return [t for t in self.queue if t.castle_id == castle_id]

    def can_afford(self, castle: Castle, task: BuildingTask) -> bool:
        """Check if castle can afford the building task."""
        r = castle.resources
        return r.wood >= task.cost_wood and r.stone >= task.cost_stone and r.food >= task.cost_food

    def get_building_status(self, castle_id: int, building_id: int) -> Optional[BuildingStatus]:
        """Get status of a specific building."""
        castle = self.castles.get(castle_id)
        if not castle:
            return None

        for building in castle.buildings:
            if building.id == building_id:
                return BuildingStatus(
                    building_id=building.id,
                    building_type=building.id,  # In this game, building_id is often the type
                    level=building.level,
                    is_upgrading=castle_id in self.in_progress,
                )
        return None

    def get_castle_buildings(self, castle_id: int) -> List[BuildingStatus]:
        """Get all buildings in a castle."""
        castle = self.castles.get(castle_id)
        if not castle:
            return []

        return [
            BuildingStatus(
                building_id=b.id,
                building_type=b.id,
                level=b.level,
                is_upgrading=castle_id in self.in_progress,
            )
            for b in castle.buildings
        ]

    async def execute_task(self, task: BuildingTask) -> bool:
        """Execute a building task."""
        try:
            success = await self.client.upgrade_building(
                castle_id=task.castle_id,
                building_id=task.building_id,
                building_type=task.building_type,
            )

            if success:
                self.in_progress[task.castle_id] = task
                # Remove from queue
                self.queue = [
                    t for t in self.queue if not (t.castle_id == task.castle_id and t.building_id == task.building_id)
                ]
                logger.info(f"Started building: Castle {task.castle_id}, Building {task.building_id}")

            return bool(success)
        except Exception as e:
            logger.error(f"Build task failed: {e}")
            return False

    async def process_queue(self) -> int:
        """
        Process the build queue, executing tasks where possible.

        Returns:
            Number of tasks executed
        """
        executed = 0

        # Group tasks by castle
        tasks_by_castle: Dict[int, List[BuildingTask]] = {}
        for task in self.queue:
            if task.castle_id not in tasks_by_castle:
                tasks_by_castle[task.castle_id] = []
            tasks_by_castle[task.castle_id].append(task)

        for castle_id, tasks in tasks_by_castle.items():
            # Skip if castle already has a build in progress
            if castle_id in self.in_progress:
                continue

            castle = self.castles.get(castle_id)
            if not castle:
                continue

            # Try to execute first affordable task
            for task in tasks:
                if self.can_afford(castle, task):
                    success = await self.execute_task(task)
                    if success:
                        executed += 1
                        break  # Only one build per castle at a time

            await asyncio.sleep(0.5)  # Rate limit

        return executed

    async def start_auto_build(self, interval: int = 60):
        """
        Start automatic building.

        Args:
            interval: Check interval in seconds
        """
        self._auto_build_enabled = True
        self._running = True

        logger.info(f"Auto-build started (interval: {interval}s)")

        while self._running and self._auto_build_enabled:
            try:
                # Refresh castle data
                await self.client.get_detailed_castle_info()
                await asyncio.sleep(1)

                # Process queue
                executed = await self.process_queue()
                if executed:
                    logger.info(f"Auto-build: executed {executed} tasks")
            except Exception as e:
                logger.error(f"Auto-build error: {e}")

            await asyncio.sleep(interval)

    def stop_auto_build(self):
        """Stop automatic building."""
        self._auto_build_enabled = False
        self._running = False
        logger.info("Auto-build stopped")

    def get_summary(self) -> Dict[str, Any]:
        """Get build queue summary."""
        return {
            "queue_length": len(self.queue),
            "in_progress_count": len(self.in_progress),
            "tasks_by_castle": {
                castle_id: len([t for t in self.queue if t.castle_id == castle_id])
                for castle_id in set(t.castle_id for t in self.queue)
            },
            "in_progress": list(self.in_progress.keys()),
        }

    def _sort_queue(self):
        """Sort queue by priority (highest first)."""
        self.queue.sort(key=lambda t: t.priority, reverse=True)

    def recommend_upgrades(self, castle_id: int, focus: str = "balanced") -> List[BuildingTask]:
        """
        Recommend building upgrades for a castle.

        Args:
            castle_id: Castle to analyze
            focus: "balanced", "military", "economy", "defense"

        Returns:
            List of recommended BuildingTask objects
        """
        recommendations = []
        castle = self.castles.get(castle_id)
        if not castle:
            return recommendations

        # Get current building levels
        buildings = {b.id: b.level for b in castle.buildings}

        # Define priority based on focus
        if focus == "military":
            priority_types = [
                BuildingType.BARRACKS,
                BuildingType.STABLE,
                BuildingType.ARCHERY_RANGE,
            ]
        elif focus == "economy":
            priority_types = [
                BuildingType.WOODCUTTER,
                BuildingType.QUARRY,
                BuildingType.FARM,
                BuildingType.WAREHOUSE,
            ]
        elif focus == "defense":
            priority_types = [
                BuildingType.WALL,
                BuildingType.DEFENSE_WORKSHOP,
                BuildingType.KEEP,
            ]
        else:  # balanced
            priority_types = [
                BuildingType.KEEP,
                BuildingType.WOODCUTTER,
                BuildingType.QUARRY,
                BuildingType.FARM,
                BuildingType.BARRACKS,
            ]

        # Find buildings that need upgrading
        for i, building_type in enumerate(priority_types):
            if building_type in buildings:
                current_level = buildings[building_type]
                recommendations.append(
                    BuildingTask(
                        castle_id=castle_id,
                        building_id=building_type,
                        target_level=current_level + 1,
                        priority=len(priority_types) - i,  # Higher priority first
                    )
                )

        return recommendations[:5]  # Return top 5 recommendations
