"""
Models for units and armies.
"""

from typing import Dict

from pydantic import BaseModel, ConfigDict, Field


class UnitStats(BaseModel):
    """Unit statistics."""

    model_config = ConfigDict(extra="ignore")

    unit_id: int
    attack: int = 0
    defense: int = 0
    health: int = 0
    speed: float = 20.0
    capacity: int = 0  # Loot capacity
    food_consumption: int = 0


class Army(BaseModel):
    """Army composition."""

    model_config = ConfigDict(extra="ignore")

    units: Dict[int, int] = Field(default_factory=dict)  # {unit_id: count}

    def add_unit(self, unit_id: int, count: int):
        """Add units to army."""
        if unit_id in self.units:
            self.units[unit_id] += count
        else:
            self.units[unit_id] = count

    def remove_unit(self, unit_id: int, count: int):
        """Remove units from army."""
        if unit_id in self.units:
            self.units[unit_id] = max(0, self.units[unit_id] - count)
            if self.units[unit_id] == 0:
                del self.units[unit_id]

    @property
    def total_units(self) -> int:
        """Total number of units."""
        return sum(self.units.values())

    @property
    def is_empty(self) -> bool:
        """Check if army is empty."""
        return len(self.units) == 0


class UnitProduction(BaseModel):
    """Unit production/training queue."""

    model_config = ConfigDict(extra="ignore")

    unit_id: int
    count: int
    finish_time: int  # Timestamp
    castle_id: int


# Common unit IDs (may vary by game version)
UNIT_IDS = {
    "MILITIA": 620,
    "SWORDSMAN": 614,
    "BOWMAN": 611,
    "CAVALRY": 629,
    "ARCHER": 626,
    "KNIGHT": 637,
}
