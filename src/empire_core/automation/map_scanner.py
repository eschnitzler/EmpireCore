"""
Map scanning and exploration automation.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple

from empire_core.config import MAP_CHUNK_SIZE
from empire_core.state.world_models import MapObject
from empire_core.utils.calculations import calculate_distance
from empire_core.utils.enums import MapObjectType

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Result of a map scan."""

    kingdom_id: int
    chunks_scanned: int
    objects_found: int
    duration: float
    targets_by_type: Dict[MapObjectType, int] = field(default_factory=dict)


@dataclass
class ScanProgress:
    """Progress of an ongoing scan."""

    total_chunks: int
    completed_chunks: int
    current_x: int
    current_y: int
    objects_found: int

    @property
    def percent_complete(self) -> float:
        if self.total_chunks == 0:
            return 0.0
        return (self.completed_chunks / self.total_chunks) * 100


class MapScanner:
    """
    Automated map scanning with intelligent chunk management.

    Features:
    - Spiral scan pattern from origin point
    - Chunk caching to avoid rescanning
    - Rate limiting to prevent server throttling
    - Progress callbacks for UI updates
    - Target filtering and analysis
    """

    # Default scan rate (chunks per second)
    DEFAULT_SCAN_RATE = 2.0

    def __init__(self, client: "EmpireClient"):
        self.client = client
        self._scanned_chunks: Dict[int, Set[Tuple[int, int]]] = {}  # kingdom -> chunks
        self._scan_timestamps: Dict[Tuple[int, int, int], float] = {}  # (kid, x, y) -> time
        self._progress_callbacks: List[Callable[[ScanProgress], None]] = []
        self._running = False
        self._stop_event = asyncio.Event()

    @property
    def map_objects(self) -> Dict[int, MapObject]:
        """Get all discovered map objects."""
        return self.client.state.map_objects

    def get_scanned_chunk_count(self, kingdom_id: int = 0) -> int:
        """Get number of scanned chunks in a kingdom."""
        return len(self._scanned_chunks.get(kingdom_id, set()))

    def is_chunk_scanned(self, kingdom_id: int, x: int, y: int) -> bool:
        """Check if a chunk has been scanned."""
        chunk_key = (x // MAP_CHUNK_SIZE, y // MAP_CHUNK_SIZE)
        return chunk_key in self._scanned_chunks.get(kingdom_id, set())

    def get_chunk_age(self, kingdom_id: int, x: int, y: int) -> Optional[float]:
        """Get age of chunk scan in seconds, or None if not scanned."""
        chunk_x = x // MAP_CHUNK_SIZE
        chunk_y = y // MAP_CHUNK_SIZE
        key = (kingdom_id, chunk_x, chunk_y)
        if key in self._scan_timestamps:
            return time.time() - self._scan_timestamps[key]
        return None

    def on_progress(self, callback: Callable[[ScanProgress], None]):
        """Register callback for scan progress updates."""
        self._progress_callbacks.append(callback)

    async def scan_area(
        self,
        center_x: int,
        center_y: int,
        radius: int = 5,
        kingdom_id: int = 0,
        rescan: bool = False,
        rate_limit: float = DEFAULT_SCAN_RATE,
    ) -> ScanResult:
        """
        Scan an area around a center point.

        Args:
            center_x: Center X coordinate
            center_y: Center Y coordinate
            radius: Radius in chunks (each chunk is MAP_CHUNK_SIZE tiles)
            kingdom_id: Kingdom to scan (0=Green, 1=Sands, 2=Ice, 3=Fire)
            rescan: Force rescan even if already scanned
            rate_limit: Maximum chunks per second

        Returns:
            ScanResult with scan statistics
        """
        start_time = time.time()
        objects_before = len(self.map_objects)

        # Generate spiral scan pattern
        chunks = self._generate_spiral_pattern(center_x, center_y, radius)
        total_chunks = len(chunks)
        completed = 0

        if kingdom_id not in self._scanned_chunks:
            self._scanned_chunks[kingdom_id] = set()

        self._running = True
        self._stop_event.clear()

        delay = 1.0 / rate_limit

        for chunk_x, chunk_y in chunks:
            if self._stop_event.is_set():
                logger.info("Scan cancelled")
                break

            chunk_key = (chunk_x, chunk_y)

            # Skip if already scanned (unless rescan requested)
            if not rescan and chunk_key in self._scanned_chunks[kingdom_id]:
                completed += 1
                continue

            # Request chunk from server
            tile_x = chunk_x * MAP_CHUNK_SIZE
            tile_y = chunk_y * MAP_CHUNK_SIZE

            try:
                await self.client.get_map_chunk(kingdom_id, tile_x, tile_y)
                self._scanned_chunks[kingdom_id].add(chunk_key)
                self._scan_timestamps[(kingdom_id, chunk_x, chunk_y)] = time.time()
            except Exception as e:
                logger.warning(f"Failed to scan chunk ({chunk_x}, {chunk_y}): {e}")

            completed += 1

            # Notify progress
            progress = ScanProgress(
                total_chunks=total_chunks,
                completed_chunks=completed,
                current_x=tile_x,
                current_y=tile_y,
                objects_found=len(self.map_objects) - objects_before,
            )
            for callback in self._progress_callbacks:
                try:
                    callback(progress)
                except Exception as e:
                    logger.error(f"Progress callback error: {e}")

            # Rate limit
            await asyncio.sleep(delay)

        self._running = False

        # Calculate results
        duration = time.time() - start_time
        objects_found = len(self.map_objects) - objects_before

        # Count by type
        targets_by_type: Dict[MapObjectType, int] = {}
        for obj in self.map_objects.values():
            obj_type = obj.type if isinstance(obj.type, MapObjectType) else MapObjectType.UNKNOWN
            targets_by_type[obj_type] = targets_by_type.get(obj_type, 0) + 1

        result = ScanResult(
            kingdom_id=kingdom_id,
            chunks_scanned=completed,
            objects_found=objects_found,
            duration=duration,
            targets_by_type=targets_by_type,
        )

        logger.info(f"Scan complete: {completed} chunks, {objects_found} new objects in {duration:.1f}s")
        return result

    async def scan_around_castles(
        self,
        radius: int = 3,
        rescan: bool = False,
    ) -> List[ScanResult]:
        """
        Scan around all player castles.

        Args:
            radius: Scan radius in chunks around each castle
            rescan: Force rescan

        Returns:
            List of ScanResults, one per castle
        """
        results = []
        player = self.client.state.local_player

        if not player or not player.castles:
            logger.warning("No castles available for scanning")
            return results

        for _castle_id, castle in player.castles.items():
            logger.info(f"Scanning around castle {castle.name} ({castle.x}, {castle.y})")
            result = await self.scan_area(
                center_x=castle.x,
                center_y=castle.y,
                radius=radius,
                kingdom_id=castle.KID,
                rescan=rescan,
            )
            results.append(result)

        return results

    def stop(self):
        """Stop an ongoing scan."""
        self._stop_event.set()

    def find_nearby_targets(
        self,
        origin_x: int,
        origin_y: int,
        max_distance: float = 50.0,
        target_types: Optional[List[MapObjectType]] = None,
        max_level: int = 999,
        exclude_player_ids: Optional[List[int]] = None,
    ) -> List[Tuple[MapObject, float]]:
        """
        Find targets near a point from scanned data.

        Args:
            origin_x: Origin X coordinate
            origin_y: Origin Y coordinate
            max_distance: Maximum distance to search
            target_types: Filter by object types (None = all)
            max_level: Maximum target level
            exclude_player_ids: Player IDs to exclude

        Returns:
            List of (MapObject, distance) tuples sorted by distance
        """
        targets = []
        exclude_ids = set(exclude_player_ids or [])

        for obj in self.map_objects.values():
            # Filter by type
            if target_types:
                obj_type = obj.type if isinstance(obj.type, MapObjectType) else MapObjectType.UNKNOWN
                if obj_type not in target_types:
                    continue

            # Filter by level
            if obj.level > max_level:
                continue

            # Filter by owner
            if obj.owner_id in exclude_ids:
                continue

            # Calculate distance
            distance = calculate_distance(origin_x, origin_y, obj.x, obj.y)
            if distance <= max_distance:
                targets.append((obj, distance))

        # Sort by distance
        targets.sort(key=lambda t: t[1])
        return targets

    def find_npc_targets(
        self,
        origin_x: int,
        origin_y: int,
        max_distance: float = 30.0,
    ) -> List[Tuple[MapObject, float]]:
        """Find NPC camps for farming."""
        npc_types = [
            MapObjectType.NOMAD_CAMP,
            MapObjectType.SAMURAI_CAMP,
            MapObjectType.ALIEN_CAMP,
            MapObjectType.FACTION_CAMP,
        ]
        return self.find_nearby_targets(origin_x, origin_y, max_distance, target_types=npc_types)

    def find_player_targets(
        self,
        origin_x: int,
        origin_y: int,
        max_distance: float = 50.0,
        max_level: int = 999,
    ) -> List[Tuple[MapObject, float]]:
        """Find player castles for attacking/scouting."""
        return self.find_nearby_targets(
            origin_x,
            origin_y,
            max_distance,
            target_types=[MapObjectType.CASTLE],
            max_level=max_level,
        )

    def get_scan_summary(self) -> Dict[str, Any]:
        """Get summary of all scanned data."""
        type_counts: Dict[str, int] = {}
        for obj in self.map_objects.values():
            obj_type = obj.type if isinstance(obj.type, MapObjectType) else MapObjectType.UNKNOWN
            type_name = obj_type.name
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        kingdoms_scanned = {kid: len(chunks) for kid, chunks in self._scanned_chunks.items()}

        return {
            "total_objects": len(self.map_objects),
            "objects_by_type": type_counts,
            "chunks_by_kingdom": kingdoms_scanned,
            "total_chunks": sum(kingdoms_scanned.values()),
        }

    def clear_cache(self, kingdom_id: Optional[int] = None):
        """Clear scan cache for a kingdom or all kingdoms."""
        if kingdom_id is not None:
            self._scanned_chunks.pop(kingdom_id, None)
            # Clear timestamps for this kingdom
            keys_to_remove = [k for k in self._scan_timestamps if k[0] == kingdom_id]
            for key in keys_to_remove:
                del self._scan_timestamps[key]
        else:
            self._scanned_chunks.clear()
            self._scan_timestamps.clear()

    def _generate_spiral_pattern(self, center_x: int, center_y: int, radius: int) -> List[Tuple[int, int]]:
        """Generate spiral scan pattern from center outward."""
        center_chunk_x = center_x // MAP_CHUNK_SIZE
        center_chunk_y = center_y // MAP_CHUNK_SIZE

        chunks = [(center_chunk_x, center_chunk_y)]

        for r in range(1, radius + 1):
            # Top row
            for x in range(center_chunk_x - r, center_chunk_x + r + 1):
                chunks.append((x, center_chunk_y - r))
            # Bottom row
            for x in range(center_chunk_x - r, center_chunk_x + r + 1):
                chunks.append((x, center_chunk_y + r))
            # Left column (excluding corners)
            for y in range(center_chunk_y - r + 1, center_chunk_y + r):
                chunks.append((center_chunk_x - r, y))
            # Right column (excluding corners)
            for y in range(center_chunk_y - r + 1, center_chunk_y + r):
                chunks.append((center_chunk_x + r, y))

        return chunks
