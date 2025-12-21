"""
Helper functions for common game operations.
"""

from typing import Dict, List, Optional

from empire_core.state.models import Castle, Player
from empire_core.state.world_models import Movement
from empire_core.utils.enums import MovementType


class CastleHelper:
    """Helper for castle operations."""

    @staticmethod
    def has_sufficient_resources(castle: Castle, wood: int = 0, stone: int = 0, food: int = 0) -> bool:
        """Check if castle has sufficient resources."""
        return castle.resources.wood >= wood and castle.resources.stone >= stone and castle.resources.food >= food

    @staticmethod
    def get_resource_overflow(castle: Castle) -> Dict[str, int]:
        """Get resources exceeding capacity."""
        overflow = {}

        if castle.resources.wood > castle.resources.wood_cap:
            overflow["wood"] = castle.resources.wood - castle.resources.wood_cap

        if castle.resources.stone > castle.resources.stone_cap:
            overflow["stone"] = castle.resources.stone - castle.resources.stone_cap

        if castle.resources.food > castle.resources.food_cap:
            overflow["food"] = castle.resources.food - castle.resources.food_cap

        return overflow

    @staticmethod
    def can_upgrade_building(
        castle: Castle,
        building_id: int,
        cost_wood: int = 0,
        cost_stone: int = 0,
        cost_food: int = 0,
    ) -> bool:
        """Check if building can be upgraded."""
        return CastleHelper.has_sufficient_resources(castle, cost_wood, cost_stone, cost_food)


class MovementHelper:
    """Helper for movement operations."""

    @staticmethod
    def get_incoming_attacks(movements: Dict[int, Movement]) -> List[Movement]:
        """Get all incoming attacks."""
        return [m for m in movements.values() if m.is_incoming and m.is_attack]

    @staticmethod
    def get_outgoing_attacks(movements: Dict[int, Movement]) -> List[Movement]:
        """Get all outgoing attacks."""
        return [m for m in movements.values() if m.is_outgoing and m.is_attack]

    @staticmethod
    def get_returning_movements(movements: Dict[int, Movement]) -> List[Movement]:
        """Get all returning movements."""
        return [m for m in movements.values() if m.is_returning]

    @staticmethod
    def get_movements_to_area(movements: Dict[int, Movement], area_id: int) -> List[Movement]:
        """Get all movements to specific area."""
        return [m for m in movements.values() if m.target_area_id == area_id]

    @staticmethod
    def get_movements_from_area(movements: Dict[int, Movement], area_id: int) -> List[Movement]:
        """Get all movements from specific area."""
        return [m for m in movements.values() if m.source_area_id == area_id]

    @staticmethod
    def get_movements_by_type(movements: Dict[int, Movement], movement_type: MovementType) -> List[Movement]:
        """Get all movements of a specific type."""
        return [m for m in movements.values() if m.T == movement_type]

    @staticmethod
    def estimate_arrival_time(movement: Movement) -> float:
        """
        Estimate arrival timestamp (Unix time).

        Returns:
            Unix timestamp of estimated arrival
        """
        return movement.last_updated + movement.time_remaining

    @staticmethod
    def get_soonest_arrival(movements: Dict[int, Movement]) -> Optional[Movement]:
        """Get the movement arriving soonest."""
        if not movements:
            return None
        return min(movements.values(), key=lambda m: m.time_remaining)

    @staticmethod
    def get_soonest_incoming_attack(
        movements: Dict[int, Movement],
    ) -> Optional[Movement]:
        """Get the soonest incoming attack."""
        attacks = MovementHelper.get_incoming_attacks(movements)
        if not attacks:
            return None
        return min(attacks, key=lambda m: m.time_remaining)

    @staticmethod
    def sort_by_arrival(movements: List[Movement], ascending: bool = True) -> List[Movement]:
        """Sort movements by arrival time."""
        return sorted(movements, key=lambda m: m.time_remaining, reverse=not ascending)

    @staticmethod
    def get_movements_arriving_within(movements: Dict[int, Movement], seconds: int) -> List[Movement]:
        """Get all movements arriving within specified seconds."""
        return [m for m in movements.values() if m.time_remaining <= seconds]

    @staticmethod
    def get_total_units_in_movements(movements: List[Movement]) -> Dict[int, int]:
        """Get total units across all movements."""
        totals: Dict[int, int] = {}
        for m in movements:
            for unit_id, count in m.units.items():
                totals[unit_id] = totals.get(unit_id, 0) + count
        return totals

    @staticmethod
    def get_total_resources_in_movements(movements: List[Movement]) -> Dict[str, int]:
        """Get total resources across all movements (transports/returns)."""
        totals = {"wood": 0, "stone": 0, "food": 0}
        for m in movements:
            totals["wood"] += m.resources.wood
            totals["stone"] += m.resources.stone
            totals["food"] += m.resources.food
        return totals

    @staticmethod
    def format_movement(movement: Movement) -> str:
        """Format a movement for display."""
        direction = "→" if movement.is_outgoing else "←" if movement.is_incoming else "↺"
        if movement.is_returning:
            direction = "↩"

        return (
            f"[{movement.MID}] {movement.movement_type_name} {direction} "
            f"{movement.source_area_id} → {movement.target_area_id} "
            f"({movement.format_time_remaining()}, {movement.unit_count} units)"
        )

    @staticmethod
    def format_movements_table(movements: List[Movement]) -> str:
        """Format a list of movements as a table."""
        if not movements:
            return "No movements."

        lines = [f"{'ID':<10} {'Type':<12} {'From':<10} {'To':<10} {'Units':<8} {'Time':<12}"]
        lines.append("-" * 65)

        for m in sorted(movements, key=lambda x: x.time_remaining):
            lines.append(
                f"{m.MID:<10} {m.movement_type_name:<12} "
                f"{m.source_area_id:<10} {m.target_area_id:<10} "
                f"{m.unit_count:<8} {m.format_time_remaining():<12}"
            )

        return "\n".join(lines)

    @staticmethod
    def is_attack_imminent(movements: Dict[int, Movement], threshold_seconds: int = 60) -> bool:
        """Check if any attack is arriving within threshold."""
        attacks = MovementHelper.get_incoming_attacks(movements)
        return any(a.time_remaining <= threshold_seconds for a in attacks)

    @staticmethod
    def count_movements_by_type(movements: Dict[int, Movement]) -> Dict[str, int]:
        """Count movements grouped by type."""
        counts: Dict[str, int] = {}
        for m in movements.values():
            type_name = m.movement_type_name
            counts[type_name] = counts.get(type_name, 0) + 1
        return counts


class ResourceHelper:
    """Helper for resource management."""

    @staticmethod
    def calculate_production_until_full(castle: Castle) -> Dict[str, float]:
        """Calculate hours until resources are full."""
        result = {}

        if castle.resources.wood_rate > 0:
            space = castle.resources.wood_cap - castle.resources.wood
            if space > 0:
                result["wood"] = space / castle.resources.wood_rate

        if castle.resources.stone_rate > 0:
            space = castle.resources.stone_cap - castle.resources.stone
            if space > 0:
                result["stone"] = space / castle.resources.stone_rate

        if castle.resources.food_rate > 0:
            space = castle.resources.food_cap - castle.resources.food
            if space > 0:
                result["food"] = space / castle.resources.food_rate

        return result

    @staticmethod
    def get_optimal_transport_amount(source: Castle, target_capacity: int, resource_type: str = "wood") -> int:
        """Calculate optimal amount to transport."""
        if resource_type == "wood":
            available = source.resources.wood
            safe = source.resources.wood_safe
        elif resource_type == "stone":
            available = source.resources.stone
            safe = source.resources.stone_safe
        elif resource_type == "food":
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
        totals = {"wood": 0, "stone": 0, "food": 0}

        for castle in player.castles.values():
            totals["wood"] += castle.resources.wood
            totals["stone"] += castle.resources.stone
            totals["food"] += castle.resources.food

        return totals

    @staticmethod
    def get_total_population(player: Player) -> int:
        """Get total population across all castles."""
        return sum(c.population for c in player.castles.values())

    @staticmethod
    def get_total_buildings(player: Player) -> int:
        """Get total buildings across all castles."""
        return sum(len(c.buildings) for c in player.castles.values())
