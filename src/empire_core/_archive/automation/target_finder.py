"""
Target finding and world scanning.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from empire_core.state.world_models import MapObject
from empire_core.utils.calculations import calculate_distance
from empire_core.utils.enums import MapObjectType

logger = logging.getLogger(__name__)


class TargetFilter:
    """Filter criteria for targets."""

    def __init__(self):
        self.max_distance: Optional[float] = None
        self.min_level: int = 0
        self.max_level: int = 999
        self.object_types: List[MapObjectType] = []
        self.exclude_alliances: List[int] = []
        self.only_inactive: bool = False


class TargetFinder:
    """Find and evaluate targets for attacks."""

    def __init__(self, map_objects: Dict[int, MapObject]):
        self.map_objects = map_objects

    def find_targets(
        self,
        origin_x: int,
        origin_y: int,
        max_distance: float = 50.0,
        target_type: MapObjectType = MapObjectType.CASTLE,
        max_level: int = 10,
    ) -> List[Tuple[MapObject, float]]:
        """
        Find targets near origin.

        Returns:
            List of (map_object, distance) tuples sorted by distance
        """
        targets = []

        for obj in self.map_objects.values():
            if obj.type != target_type:
                continue

            if obj.level > max_level:
                continue

            distance = calculate_distance(origin_x, origin_y, obj.x, obj.y)

            if distance <= max_distance:
                targets.append((obj, distance))

        # Sort by distance
        targets.sort(key=lambda t: t[1])

        logger.info(f"Found {len(targets)} targets within {max_distance} distance")
        return targets

    def find_npc_camps(self, origin_x: int, origin_y: int, max_distance: float = 30.0) -> List[Tuple[MapObject, float]]:
        """Find NPC camps (robber camps, etc.)."""
        npc_types = [
            MapObjectType.NOMAD_CAMP,
            MapObjectType.SAMURAI_CAMP,
            MapObjectType.ALIEN_CAMP,
            MapObjectType.FACTION_CAMP,
        ]

        targets = []
        for obj in self.map_objects.values():
            if obj.type in npc_types:
                distance = calculate_distance(origin_x, origin_y, obj.x, obj.y)
                if distance <= max_distance:
                    targets.append((obj, distance))

        targets.sort(key=lambda t: t[1])
        return targets

    def find_resources(self, origin_x: int, origin_y: int, max_distance: float = 20.0) -> List[Tuple[MapObject, float]]:
        """Find resource locations."""
        targets = []
        for obj in self.map_objects.values():
            if obj.type == MapObjectType.ISLE_RESOURCE:
                distance = calculate_distance(origin_x, origin_y, obj.x, obj.y)
                if distance <= max_distance:
                    targets.append((obj, distance))

        targets.sort(key=lambda t: t[1])
        return targets

    def evaluate_target(self, target: MapObject, player_level: int) -> Dict[str, Any]:
        """Evaluate target profitability/safety."""
        score = 0
        risk = "low"

        # Level difference
        level_diff = player_level - target.level
        if level_diff > 5:
            score += 50
            risk = "low"
        elif level_diff > 0:
            score += 30
            risk = "medium"
        else:
            score += 10
            risk = "high"

        # Target type bonuses
        if target.type == MapObjectType.NOMAD_CAMP:
            score += 40  # Good loot
        elif target.type == MapObjectType.CASTLE:
            score += 20  # Variable loot

        return {"score": score, "risk": risk, "level_diff": level_diff, "recommended": score > 40 and risk != "high"}


class WorldScanner:
    """Scan and map the world."""

    def __init__(self):
        self.scanned_chunks: set = set()

    def generate_scan_pattern(self, center_x: int, center_y: int, radius: int = 10) -> List[Tuple[int, int]]:
        """Generate spiral scan pattern."""
        coords = []

        # Spiral outward
        for r in range(1, radius + 1):
            for x in range(center_x - r, center_x + r + 1):
                coords.append((x, center_y - r))
                coords.append((x, center_y + r))
            for y in range(center_y - r + 1, center_y + r):
                coords.append((center_x - r, y))
                coords.append((center_x + r, y))

        return coords

    def mark_scanned(self, kingdom_id: int, chunk_x: int, chunk_y: int):
        """Mark chunk as scanned."""
        key = f"{kingdom_id}:{chunk_x}:{chunk_y}"
        self.scanned_chunks.add(key)

    def is_scanned(self, kingdom_id: int, chunk_x: int, chunk_y: int) -> bool:
        """Check if chunk is scanned."""
        key = f"{kingdom_id}:{chunk_x}:{chunk_y}"
        return key in self.scanned_chunks
