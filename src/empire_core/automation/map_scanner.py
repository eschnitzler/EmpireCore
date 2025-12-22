"""
Map scanning and exploration automation with asynchronous database persistence.
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
    Automated map scanning with intelligent chunk management and persistence.

    Features:
    - Spiral scan pattern from origin point
    - Persistent chunk caching in SQLite database (async)
    - Rate limiting to prevent server throttling
    - Progress callbacks for UI updates
    - Database-backed target discovery
    """

    # Default scan rate (chunks per second)
    DEFAULT_SCAN_RATE = 2.0

    def __init__(self, client: "EmpireClient"):
        self.client = client
        self._scanned_chunks: Dict[int, Set[Tuple[int, int]]] = {}  # kingdom -> chunks
        self._progress_callbacks: List[Callable[[ScanProgress], None]] = []
        self._running = False
        self._stop_event = asyncio.Event()

    async def initialize(self):
        """Initialize scanner and load cache from database."""
        try:
            for kid in [0, 1, 2, 3, 4]:
                chunks = await self.client.db.get_scanned_chunks(kid)
                if chunks:
                    self._scanned_chunks[kid] = chunks
            logger.debug(f"MapScanner: Loaded cache for {len(self._scanned_chunks)} kingdoms from DB")
        except Exception as e:
            logger.warning(f"MapScanner: Failed to load cache from DB: {e}")

    @property
    def map_objects(self) -> Dict[int, MapObject]:
        """Get all discovered map objects in current session memory."""
        return self.client.state.map_objects

    def get_scanned_chunk_count(self, kingdom_id: int = 0) -> int:
        """Get number of scanned chunks in a kingdom."""
        return len(self._scanned_chunks.get(kingdom_id, set()))

    def is_chunk_scanned(self, kingdom_id: int, x: int, y: int) -> bool:
        """Check if a chunk has been scanned."""
        chunk_key = (x // MAP_CHUNK_SIZE, y // MAP_CHUNK_SIZE)
        return chunk_key in self._scanned_chunks.get(kingdom_id, set())

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
        Scan an area around a center point and persist results.
        """
        start_time = time.time()
        objects_before = len(self.map_objects)

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

            if not rescan and chunk_key in self._scanned_chunks[kingdom_id]:
                completed += 1
                continue

            tile_x = chunk_x * MAP_CHUNK_SIZE
            tile_y = chunk_y * MAP_CHUNK_SIZE

            try:
                await self.client.get_map_chunk(kingdom_id, tile_x, tile_y)

                # Wait for state update
                await asyncio.sleep(0.2)

                # Persist discovered objects to DB
                await self.client.db.save_map_objects(list(self.map_objects.values()))

                # Update cache
                self._scanned_chunks[kingdom_id].add(chunk_key)
                await self.client.db.mark_chunk_scanned(kingdom_id, chunk_x, chunk_y)

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

            await asyncio.sleep(delay)

        self._running = False
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

        logger.info(f"Scan complete: {completed} chunks, {objects_found} new objects saved to DB")
        return result

    async def scan_around_castles(self, radius: int = 5, rescan: bool = False) -> List[ScanResult]:
        """Scan areas around all player castles."""
        results: List[ScanResult] = []
        player = self.client.state.local_player
        if not player or not player.castles:
            return results

        for _castle_id, castle in player.castles.items():
            result = await self.scan_area(
                center_x=castle.x,
                center_y=castle.y,
                radius=radius,
                kingdom_id=castle.KID,
                rescan=rescan,
            )
            results.append(result)

        return results

    async def find_nearby_targets(
        self,
        origin_x: int,
        origin_y: int,
        max_distance: float = 50.0,
        target_types: Optional[List[MapObjectType]] = None,
        max_level: int = 999,
        exclude_player_ids: Optional[List[int]] = None,
        use_db: bool = True,
    ) -> List[Tuple[Any, float]]:
        """
        Find targets near a point, searching both memory and database.
        """
        targets_dict: Dict[int, Tuple[Any, float]] = {}
        exclude_ids = set(exclude_player_ids or [])

        # 1. Search Database first
        if use_db:
            db_types = [int(t) for t in target_types] if target_types else None
            db_results = await self.client.db.find_targets(0, max_level=max_level, types=db_types)
            for record in db_results:
                if record.owner_id in exclude_ids:
                    continue
                dist = calculate_distance(origin_x, origin_y, record.x, record.y)
                if dist <= max_distance:
                    targets_dict[record.area_id] = (record, dist)

        # 2. Search Memory
        for obj in self.map_objects.values():
            if target_types and obj.type not in target_types:
                continue
            if obj.level > max_level:
                continue
            if obj.owner_id in exclude_ids:
                continue
            dist = calculate_distance(origin_x, origin_y, obj.x, obj.y)
            if dist <= max_distance:
                targets_dict[obj.area_id] = (obj, dist)

        # Sort and return
        results = list(targets_dict.values())
        results.sort(key=lambda t: t[1])
        return results

    async def get_scan_summary(self) -> Dict[str, Any]:
        """Get summary including database stats."""
        mem_summary = {kid: len(chunks) for kid, chunks in self._scanned_chunks.items()}
        db_count = await self.client.db.get_object_count()

        return {
            "memory_objects": len(self.map_objects),
            "database_objects": db_count,
            "chunks_by_kingdom": mem_summary,
            "total_chunks_scanned": sum(mem_summary.values()),
        }

    def _generate_spiral_pattern(self, center_x: int, center_y: int, radius: int) -> List[Tuple[int, int]]:
        """Generate spiral scan pattern from center outward."""
        center_chunk_x = center_x // MAP_CHUNK_SIZE
        center_chunk_y = center_y // MAP_CHUNK_SIZE

        chunks = [(center_chunk_x, center_chunk_y)]

        for r in range(1, radius + 1):
            for x in range(center_chunk_x - r, center_chunk_x + r + 1):
                chunks.append((x, center_chunk_y - r))
                chunks.append((x, center_chunk_y + r))
            for y in range(center_chunk_y - r + 1, center_chunk_y + r):
                chunks.append((center_chunk_x - r, y))
                chunks.append((center_chunk_x + r, y))

        return chunks
