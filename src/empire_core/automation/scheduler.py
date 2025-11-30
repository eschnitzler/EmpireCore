"""
Task scheduler for automation.
"""
import asyncio
import logging
from typing import Callable, Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    """A scheduled task."""
    name: str
    callback: Callable
    interval: int  # seconds
    last_run: Optional[datetime] = None
    enabled: bool = True


class TaskScheduler:
    """Manages scheduled tasks."""
    
    def __init__(self):
        self.tasks: Dict[str, ScheduledTask] = {}
        self.running = False
    
    def add_task(
        self,
        name: str,
        callback: Callable,
        interval: int
    ):
        """Add a scheduled task."""
        task = ScheduledTask(
            name=name,
            callback=callback,
            interval=interval
        )
        self.tasks[name] = task
        logger.info(f"Added task: {name} (interval: {interval}s)")
    
    def remove_task(self, name: str):
        """Remove a task."""
        if name in self.tasks:
            del self.tasks[name]
            logger.info(f"Removed task: {name}")
    
    def enable_task(self, name: str):
        """Enable a task."""
        if name in self.tasks:
            self.tasks[name].enabled = True
    
    def disable_task(self, name: str):
        """Disable a task."""
        if name in self.tasks:
            self.tasks[name].enabled = False
    
    async def start(self):
        """Start scheduler."""
        self.running = True
        logger.info("Task scheduler started")
        
        while self.running:
            try:
                await self._check_tasks()
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(5)
    
    def stop(self):
        """Stop scheduler."""
        self.running = False
        logger.info("Task scheduler stopped")
    
    async def _check_tasks(self):
        """Check and run due tasks."""
        now = datetime.now()
        
        for task in self.tasks.values():
            if not task.enabled:
                continue
            
            # Check if due
            if task.last_run is None:
                should_run = True
            else:
                elapsed = (now - task.last_run).total_seconds()
                should_run = elapsed >= task.interval
            
            if should_run:
                try:
                    logger.debug(f"Running task: {task.name}")
                    
                    # Run async or sync
                    if asyncio.iscoroutinefunction(task.callback):
                        await task.callback()
                    else:
                        task.callback()
                    
                    task.last_run = now
                except Exception as e:
                    logger.error(f"Task {task.name} failed: {e}")
    
    def get_task_status(self) -> List[Dict]:
        """Get status of all tasks."""
        status = []
        now = datetime.now()
        
        for name, task in self.tasks.items():
            if task.last_run:
                elapsed = (now - task.last_run).total_seconds()
                next_run = task.interval - elapsed
            else:
                next_run = 0
            
            status.append({
                'name': name,
                'enabled': task.enabled,
                'interval': task.interval,
                'last_run': task.last_run,
                'next_run_in': max(0, int(next_run))
            })
        
        return status
