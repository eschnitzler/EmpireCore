"""
Automated farming logic.
"""
import asyncio
import logging
from typing import Optional, Dict
from empire_core.client.client import EmpireClient
from empire_core.automation.target_finder import TargetFinder
from empire_core.state.models import Castle
from empire_core.utils.enums import MapObjectType

logger = logging.getLogger(__name__)


class FarmingBot:
    """Automated farming bot."""
    
    def __init__(self, client: EmpireClient):
        self.client = client
        self.running = False
        self.farm_interval = 300  # 5 minutes
        self.max_distance = 30.0
        self.max_target_level = 10
        self.default_units = {620: 100}  # 100 militia
    
    async def start(self):
        """Start farming bot."""
        self.running = True
        logger.info("Farming bot started")
        
        while self.running:
            try:
                await self._farm_cycle()
                await asyncio.sleep(self.farm_interval)
            except Exception as e:
                logger.error(f"Farming error: {e}")
                await asyncio.sleep(60)
    
    def stop(self):
        """Stop farming bot."""
        self.running = False
        logger.info("Farming bot stopped")
    
    async def _farm_cycle(self):
        """Execute one farming cycle."""
        player = self.client.state.local_player
        if not player or not player.castles:
            logger.warning("No player/castles for farming")
            return
        
        # Get castle coordinates (would need to be stored)
        # For now, use first castle
        castle_id = list(player.castles.keys())[0]
        castle = player.castles[castle_id]
        
        # TODO: Need castle coordinates in state
        origin_x, origin_y = 500, 500  # Placeholder
        
        # Find targets
        finder = TargetFinder(self.client.state.map_objects)
        targets = finder.find_npc_camps(origin_x, origin_y, self.max_distance)
        
        if not targets:
            logger.info("No farming targets found")
            return
        
        # Attack first target
        target, distance = targets[0]
        logger.info(f"Attacking target at ({target.x}, {target.y}), distance: {distance:.1f}")
        
        try:
            await self.client.send_attack(
                origin_castle_id=castle_id,
                target_area_id=target.area_id,
                units=self.default_units,
                kingdom_id=0
            )
            logger.info("Attack sent successfully")
        except Exception as e:
            logger.error(f"Failed to send attack: {e}")


class ResourceCollector:
    """Automated resource collection."""
    
    def __init__(self, client: EmpireClient):
        self.client = client
        self.running = False
        self.collect_interval = 600  # 10 minutes
    
    async def start(self):
        """Start resource collector."""
        self.running = True
        logger.info("Resource collector started")
        
        while self.running:
            try:
                await self._collect_cycle()
                await asyncio.sleep(self.collect_interval)
            except Exception as e:
                logger.error(f"Collection error: {e}")
                await asyncio.sleep(60)
    
    def stop(self):
        """Stop resource collector."""
        self.running = False
        logger.info("Resource collector stopped")
    
    async def _collect_cycle(self):
        """Execute collection cycle."""
        player = self.client.state.local_player
        if not player:
            return
        
        # Check each castle
        for castle_id, castle in player.castles.items():
            # Check if resources near capacity
            wood_pct = (castle.resources.wood / castle.resources.wood_cap * 100) if castle.resources.wood_cap > 0 else 0
            stone_pct = (castle.resources.stone / castle.resources.stone_cap * 100) if castle.resources.stone_cap > 0 else 0
            food_pct = (castle.resources.food / castle.resources.food_cap * 100) if castle.resources.food_cap > 0 else 0
            
            if wood_pct > 90 or stone_pct > 90 or food_pct > 90:
                logger.info(f"Castle {castle_id} resources high: W:{wood_pct:.0f}% S:{stone_pct:.0f}% F:{food_pct:.0f}%")
                # TODO: Transport to other castles or use
