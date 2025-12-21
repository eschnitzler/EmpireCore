"""
Game calculation utilities.
"""

import math
from typing import Tuple


def calculate_distance(x1: int, y1: int, x2: int, y2: int) -> float:
    """
    Calculate distance between two coordinates.

    Args:
        x1, y1: First coordinate
        x2, y2: Second coordinate

    Returns:
        float: Distance
    """
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def calculate_travel_time(distance: float, speed: float = 20.0, speed_bonus: float = 0.0) -> int:
    """
    Calculate travel time for army movement.

    Args:
        distance: Distance to travel
        speed: Base speed (default 20)
        speed_bonus: Speed bonus percentage (0-100)

    Returns:
        int: Travel time in seconds
    """
    effective_speed = speed * (1 + speed_bonus / 100)
    return int(distance / effective_speed * 60)  # Convert to seconds


def calculate_resource_production(production_rate: float, hours: float) -> int:
    """
    Calculate resource production over time.

    Args:
        production_rate: Resources per hour
        hours: Number of hours

    Returns:
        int: Total resources produced
    """
    return int(production_rate * hours)


def calculate_building_cost(base_cost: int, level: int, multiplier: float = 1.5) -> int:
    """
    Calculate building upgrade cost.

    Args:
        base_cost: Base cost at level 1
        level: Target level
        multiplier: Cost multiplier per level

    Returns:
        int: Total cost
    """
    return int(base_cost * (multiplier ** (level - 1)))


def calculate_unit_power(unit_stats: dict, count: int) -> int:
    """
    Calculate total unit power.

    Args:
        unit_stats: Dict with attack, defense, health
        count: Number of units

    Returns:
        int: Total power
    """
    attack = unit_stats.get("attack", 0)
    defense = unit_stats.get("defense", 0)
    health = unit_stats.get("health", 0)

    base_power = (attack + defense + health) / 3
    return int(base_power * count)


def is_within_range(x1: int, y1: int, x2: int, y2: int, max_range: float) -> bool:
    """
    Check if coordinates are within range.

    Args:
        x1, y1: First coordinate
        x2, y2: Second coordinate
        max_range: Maximum range

    Returns:
        bool: True if within range
    """
    distance = calculate_distance(x1, y1, x2, y2)
    return distance <= max_range


def format_time(seconds: int) -> str:
    """
    Format seconds to human readable time.

    Args:
        seconds: Time in seconds

    Returns:
        str: Formatted time (e.g., "1h 30m 45s")
    """
    if seconds < 0:
        return "0s"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


def calculate_coordinates_in_radius(center_x: int, center_y: int, radius: float) -> list[Tuple[int, int]]:
    """
    Get all coordinates within radius.

    Args:
        center_x: Center X coordinate
        center_y: Center Y coordinate
        radius: Radius

    Returns:
        list: List of (x, y) tuples
    """
    coords = []
    r = int(math.ceil(radius))

    for x in range(center_x - r, center_x + r + 1):
        for y in range(center_y - r, center_y + r + 1):
            if calculate_distance(center_x, center_y, x, y) <= radius:
                coords.append((x, y))

    return coords


def calculate_loot_capacity(unit_capacities: dict, unit_counts: dict) -> int:
    """
    Calculate total loot capacity.

    Args:
        unit_capacities: Dict of {unit_id: capacity}
        unit_counts: Dict of {unit_id: count}

    Returns:
        int: Total capacity
    """
    total = 0
    for unit_id, count in unit_counts.items():
        capacity = unit_capacities.get(unit_id, 0)
        total += capacity * count

    return total
