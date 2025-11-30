"""
Helper functions for common game operations.
"""
from typing import List, Dict, Tuple, Optional
from empire_core.state.models import Castle, Player
from empire_core.state.world_models import Movement
from empire_core.utils.calculations import calculate_distance, calculate_travel_time


class CastleHelper:
    """Helper for castle operations."""
    
    @staticmethod
    def has_sufficient_resources(
        castle: Castle,
        wood: int = 0,
        stone: int = 0,
        food: int = 0
    ) -> bool:
        """Check if castle has sufficient resources."""
        return (
            castle.resources.wood >= wood and
            castle.resources.stone >= stone and
            castle.resources.food >= food
        )
    
    @staticmethod
    def get_resource_overflow(castle: Castle) -> Dict[str, int]:
        """Get resources exceeding capacity."""
        overflow = {}
        
        if castle.resources.wood > castle.resources.wood_cap:
            overflow['wood'] = castle.resources.wood - castle.resources.wood_cap
        
        if castle.resources.stone > castle.resources.stone_cap:
            overflow['stone'] = castle.resources.stone - castle.resources.stone_cap
        
        if castle.resources.food > castle.resources.food_cap:
            overflow['food'] = castle.resources.food - castle.resources.food_cap
        
        return overflow
    
    @staticmethod
    def can_upgrade_building(
        castle: Castle,
        building_id: int,
        cost_wood: int = 0,
        cost_stone: int = 0,
        cost_food: int = 0
    ) -> bool:
        """Check if building can be upgraded."""
        return CastleHelper.has_sufficient_resources(
            castle, cost_wood, cost_stone, cost_food
        )


class MovementHelper:
    """Helper for movement operations."""
    
    @staticmethod
    def get_incoming_attacks(movements: Dict[int, Movement]) -> List[Movement]:
        """Get all incoming attacks."""
        return [
            m for m in movements.values()
            if m.is_incoming and m.movement_type != 11  # Not return
        ]
    
    @staticmethod
    def get_outgoing_attacks(movements: Dict[int, Movement]) -> List[Movement]:
        """Get all outgoing attacks."""
        return [
            m for m in movements.values()
            if m.is_outgoing
        ]
    
    @staticmethod
    def get_returning_movements(movements: Dict[int, Movement]) -> List[Movement]:
        """Get all returning movements."""
        return [
            m for m in movements.values()
            if m.movement_type == 11
        ]
    
    @staticmethod
    def get_movements_to_area(
        movements: Dict[int, Movement],
        area_id: int
    ) -> List[Movement]:
        """Get all movements to specific area."""
        return [
            m for m in movements.values()
            if m.target_area_id == area_id
        ]
    
    @staticmethod
    def estimate_arrival_time(movement: Movement) -> int:
        """Estimate arrival timestamp."""
        # Simplified - would need server time sync
        import time
        return int(time.time()) + movement.time_remaining


class ResourceHelper:
    """Helper for resource management."""
    
    @staticmethod
    def calculate_production_until_full(castle: Castle) -> Dict[str, float]:
        """Calculate hours until resources are full."""
        result = {}
        
        if castle.resources.wood_rate > 0:
            space = castle.resources.wood_cap - castle.resources.wood
            if space > 0:
                result['wood'] = space / castle.resources.wood_rate
        
        if castle.resources.stone_rate > 0:
            space = castle.resources.stone_cap - castle.resources.stone
            if space > 0:
                result['stone'] = space / castle.resources.stone_rate
        
        if castle.resources.food_rate > 0:
            space = castle.resources.food_cap - castle.resources.food
            if space > 0:
                result['food'] = space / castle.resources.food_rate
        
        return result
    
    @staticmethod
    def get_optimal_transport_amount(
        source: Castle,
        target_capacity: int,
        resource_type: str = 'wood'
    ) -> int:
        """Calculate optimal amount to transport."""
        if resource_type == 'wood':
            available = source.resources.wood
            safe = source.resources.wood_safe
        elif resource_type == 'stone':
            available = source.resources.stone
            safe = source.resources.stone_safe
        elif resource_type == 'food':
            available = source.resources.food
            safe = source.resources.food_safe
        else:
            return 0
        
        # Transport excess over safe storage, up to capacity
        excess = max(0, available - safe)
        return min(int(excess), target_capacity)


class PlayerHelper:
    """Helper for player operations."""
    
    @staticmethod
    def get_total_resources(player: Player) -> Dict[str, int]:
        """Get total resources across all castles."""
        totals = {'wood': 0, 'stone': 0, 'food': 0}
        
        for castle in player.castles.values():
            totals['wood'] += castle.resources.wood
            totals['stone'] += castle.resources.stone
            totals['food'] += castle.resources.food
        
        return totals
    
    @staticmethod
    def get_total_population(player: Player) -> int:
        """Get total population across all castles."""
        return sum(c.population for c in player.castles.values())
    
    @staticmethod
    def get_total_buildings(player: Player) -> int:
        """Get total buildings across all castles."""
        return sum(len(c.buildings) for c in player.castles.values())
