"""
Building queue management and automation.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Dict, List

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
    target_level: int = 1
    priority: int = 1
    description: str = ""


class BuildingManager:
    """
    Manages building and upgrade queues for castles.

    Features:
    - Queue buildings for automatic upgrade.
    - Priority-based build order.
    - Monitor build progress.
    - Building recommendations.
    """

    def __init__(self, client: "EmpireClient"):
        self.client = client
        self.queue: List[BuildingTask] = []
        self.in_progress: Dict[int, BuildingTask] = {}  # castle_id -> current task
        self.is_running = False

    def queue_upgrade(self, castle_id: int, building_id: int, target_level: int = 1, priority: int = 1):
        """Add a building to the upgrade queue."""
        task = BuildingTask(
            castle_id=castle_id,
            building_id=building_id,
            target_level=target_level,
            priority=priority,
            description=f"Upgrade building {building_id} to level {target_level}",
        )
        self.queue.append(task)
        self._sort_queue()
        logger.info(f"Queued building {building_id} for castle {castle_id} (priority: {priority})")

    def cancel_task(self, castle_id: int, building_id: int):
        """Remove a task from the queue."""
        self.queue = [t for t in self.queue if not (t.castle_id == castle_id and t.building_id == building_id)]
        logger.info(f"Cancelled build task for building {building_id} in castle {castle_id}")

    async def process_queue(self):
        """Check queue and start next available build tasks."""
        if not self.queue:
            return

        # Check each castle's availability
        # Note: In this game, usually one build slot per castle (unless rubies/premium)
        active_castles = set(self.in_progress.keys())

        for task in list(self.queue):
            if task.castle_id in active_castles:
                continue

            # Attempt to start build
            success = await self._start_build(task)
            if success:
                self.in_progress[task.castle_id] = task
                self.queue.remove(task)
                logger.info(f"Started building {task.building_id} in castle {task.castle_id}")

    async def _start_build(self, task: BuildingTask) -> bool:
        """Internal: Send build command to server."""
        try:
            # Command: bui (Build)
            # Needs implementation in GameActionsMixin/EmpireClient
            success = await self.client.upgrade_building(
                castle_id=task.castle_id,
                building_id=task.building_id,
            )
            return bool(success)
        except Exception as e:
            logger.error(f"Failed to start build: {e}")
            return False

    async def refresh_status(self):
        """Update status of in-progress builds."""
        # Refresh state from server
        await self.client.get_detailed_castle_info()

        # Check if in-progress buildings are finished
        player = self.client.state.local_player
        if not player:
            return

        finished_castles = []
        for castle_id, task in self.in_progress.items():
            castle = player.castles.get(castle_id)
            if not castle:
                continue

            # Check if building reached target level
            # In this game, buildings list in dcl contains current level
            is_finished = False
            for building in castle.buildings:
                if building.id == task.building_id and building.level >= task.target_level:
                    is_finished = True
                    break

            if is_finished:
                finished_castles.append(castle_id)
                logger.info(f"Build finished: {task.description} in castle {castle_id}")

        for cid in finished_castles:
            del self.in_progress[cid]

    async def start_automation(self, interval: int = 60):
        """Start automatic build queue processing."""
        self.is_running = True
        logger.info("Building automation started")

        while self.is_running:
            try:
                await self.refresh_status()
                await self.process_queue()
            except Exception as e:
                logger.error(f"Building automation error: {e}")

            await asyncio.sleep(interval)

    def stop_automation(self):
        """Stop automatic build queue processing."""
        self.is_running = False
        logger.info("Building automation stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get current status of queue and active builds."""
        return {
            "queue_size": len(self.queue),
            "queue_by_castle": {
                castle_id: len([t for t in self.queue if t.castle_id == castle_id])
                for castle_id in set(t.castle_id for t in self.queue)
            },
            "in_progress": list(self.in_progress.keys()),
        }

    def _sort_queue(self):
        """Sort queue by priority (highest first)."""
        self.queue.sort(key=lambda t: t.priority, reverse=True)

    def get_recommendations(self, castle_id: int, focus: str = "balanced") -> List[BuildingTask]:
        """Get recommended buildings to build/upgrade."""
        recommendations: List[BuildingTask] = []
        castle = self.client.state.castles.get(castle_id)
        if not castle:
            return recommendations

        # Get current building levels
        buildings = {b.id: b.level for b in castle.buildings}

        # Define priority based on focus
        priority_types: List[int] = []
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
                if current_level < 10:  # Simple threshold
                    recommendations.append(
                        BuildingTask(
                            castle_id=castle_id,
                            building_id=building_type,
                            target_level=current_level + 1,
                            priority=len(priority_types) - i,  # Higher priority first
                        )
                    )

        return recommendations
