"""
Battle simulation engine.
"""

import logging
from dataclasses import dataclass
from typing import Dict

logger = logging.getLogger(__name__)


@dataclass
class UnitType:
    """Unit type definition."""

    id: int
    name: str
    attack: int
    defense: int
    health: int
    speed: float
    capacity: int
    food_cost: int


# Common unit definitions (example values - adjust based on actual game)
UNIT_TYPES = {
    620: UnitType(620, "Militia", 10, 10, 50, 20, 10, 1),
    614: UnitType(614, "Swordsman", 30, 20, 100, 18, 20, 2),
    611: UnitType(611, "Bowman", 25, 15, 80, 20, 15, 1),
    629: UnitType(629, "Cavalry", 50, 30, 150, 30, 30, 3),
    626: UnitType(626, "Archer", 35, 20, 90, 20, 15, 2),
    637: UnitType(637, "Knight", 80, 50, 200, 25, 50, 5),
}


@dataclass
class BattleResult:
    """Result of a battle simulation."""

    attacker_wins: bool
    attacker_losses: Dict[int, int]
    defender_losses: Dict[int, int]
    attacker_survivors: Dict[int, int]
    defender_survivors: Dict[int, int]
    loot: Dict[str, int]
    rounds: int


class BattleSimulator:
    """Simulate battles between armies."""

    def __init__(self):
        self.unit_types = UNIT_TYPES

    def simulate(
        self,
        attacker_army: Dict[int, int],
        defender_army: Dict[int, int],
        attacker_bonus: float = 0.0,
        defender_bonus: float = 0.0,
        defender_wall_level: int = 0,
    ) -> BattleResult:
        """
        Simulate a battle.

        Args:
            attacker_army: {unit_id: count}
            defender_army: {unit_id: count}
            attacker_bonus: Attack bonus % (0-100)
            defender_bonus: Defense bonus % (0-100)
            defender_wall_level: Wall level (adds defense)

        Returns:
            BattleResult
        """
        # Calculate total power
        attacker_power = self._calculate_power(attacker_army, attacker_bonus)
        defender_power = self._calculate_power(defender_army, defender_bonus)

        # Add wall bonus
        wall_bonus = defender_wall_level * 50  # 50 defense per level
        defender_power += wall_bonus

        # Determine winner
        attacker_wins = attacker_power > defender_power

        # Calculate losses (simplified)
        if attacker_wins:
            # Attacker wins - defender loses all, attacker loses some
            power_ratio = defender_power / attacker_power if attacker_power > 0 else 0
            attacker_losses = self._calculate_losses(attacker_army, power_ratio)
            defender_losses = defender_army.copy()
        else:
            # Defender wins - attacker loses all, defender loses some
            power_ratio = attacker_power / defender_power if defender_power > 0 else 0
            attacker_losses = attacker_army.copy()
            defender_losses = self._calculate_losses(defender_army, power_ratio)

        # Calculate survivors
        attacker_survivors = {uid: count - attacker_losses.get(uid, 0) for uid, count in attacker_army.items()}
        defender_survivors = {uid: count - defender_losses.get(uid, 0) for uid, count in defender_army.items()}

        # Calculate loot (if attacker wins)
        loot = {}
        if attacker_wins:
            total_capacity = sum(
                UNIT_TYPES.get(uid, UNIT_TYPES[620]).capacity * count for uid, count in attacker_survivors.items()
            )
            loot = {
                "wood": int(total_capacity * 0.33),
                "stone": int(total_capacity * 0.33),
                "food": int(total_capacity * 0.34),
            }

        return BattleResult(
            attacker_wins=attacker_wins,
            attacker_losses=attacker_losses,
            defender_losses=defender_losses,
            attacker_survivors=attacker_survivors,
            defender_survivors=defender_survivors,
            loot=loot,
            rounds=1,  # Simplified - single round
        )

    def _calculate_power(self, army: Dict[int, int], bonus: float = 0.0) -> float:
        """Calculate total army power."""
        total = 0.0

        for unit_id, count in army.items():
            unit = self.unit_types.get(unit_id)
            if not unit:
                continue

            unit_power = (unit.attack + unit.defense + unit.health) / 3
            total += unit_power * count

        # Apply bonus
        total *= 1 + bonus / 100

        return total

    def _calculate_losses(self, army: Dict[int, int], loss_ratio: float) -> Dict[int, int]:
        """Calculate unit losses."""
        losses = {}

        for unit_id, count in army.items():
            lost = int(count * loss_ratio)
            if lost > 0:
                losses[unit_id] = lost

        return losses

    def estimate_outcome(self, attacker_army: Dict[int, int], defender_army: Dict[int, int]) -> str:
        """Quick estimate of battle outcome."""
        att_power = self._calculate_power(attacker_army)
        def_power = self._calculate_power(defender_army)

        ratio = att_power / def_power if def_power > 0 else 999

        if ratio > 2.0:
            return "Easy Win"
        elif ratio > 1.5:
            return "Likely Win"
        elif ratio > 1.0:
            return "Close Win"
        elif ratio > 0.75:
            return "Close Loss"
        elif ratio > 0.5:
            return "Likely Loss"
        else:
            return "Heavy Loss"
