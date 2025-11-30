"""
Building queue management and automation.
"""
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from empire_core.state.models import Castle, Building

logger = logging.getLogger(__name__)


@dataclass
class BuildingTask:
    """A building task in the queue."""
    castle_id: int
    building_id: int
    building_type: Optional[int] = None
    priority: int = 0
    cost_wood: int = 0
    cost_stone: int = 0
    cost_food: int = 0


class BuildingQueueManager:
    """Manages building upgrade queues."""
    
    def __init__(self):
        self.queue: List[BuildingTask] = []
        self.in_progress: Dict[int, BuildingTask] = {}
    
    def add_task(self, castle_id: int, building_id: int, priority: int = 0):
        """Add building task to queue."""
        task = BuildingTask(castle_id=castle_id, building_id=building_id, priority=priority)
        self.queue.append(task)
        self.queue.sort(key=lambda t: t.priority, reverse=True)
        logger.info(f"Added: Castle {castle_id}, Building {building_id}")
    
    def get_next_task(self, castle_id: Optional[int] = None) -> Optional[BuildingTask]:
        """Get next task."""
        if not self.queue:
            return None
        if castle_id:
            for task in self.queue:
                if task.castle_id == castle_id:
                    return task
        return self.queue[0]
    
    def can_afford(self, castle: Castle, task: BuildingTask) -> bool:
        """Check if affordable."""
        return (castle.resources.wood >= task.cost_wood and
                castle.resources.stone >= task.cost_stone and
                castle.resources.food >= task.cost_food)
