"""
Map scanning and exploration automation with asynchronous database persistence.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple

from empire_core.events.base import PacketEvent
from empire_core.state.world_models import MapObject
from empire_core.utils.calculations import calculate_distance
from empire_core.utils.enums import MapObjectType

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)

# The step between chunks is exactly 13 tiles (index 0-12 inclusive)
MAP_STEP = 13


@dataclass
class ScanResult:
    """Result of a map scan."""

    kingdom_id: int
    chunks_scanned: int
    objects_found: int
    duration: float
    targets_by_type: Dict[str, int] = field(default_factory=dict)


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
    - High-speed spiral scan pattern aligned to 13x13 grid
    - Persistent chunk caching in SQLite database (async)
    - Real-time database persistence via packet events
    - Progress callbacks for UI updates
    - Database-backed target discovery
    """

    def __init__(self, client: "EmpireClient"):
        self.client = client
        self._scanned_chunks: Dict[int, Set[Tuple[int, int]]] = {}  # kingdom -> chunk_coordinates
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

            # Register real-time persistence handler
            self.client.events.listen(self._on_gaa_packet)
        except Exception as e:
            logger.warning(f"MapScanner: Failed to initialize: {e}")

    async def _on_gaa_packet(self, event: PacketEvent):
        """Handle incoming map data and persist immediately."""
        if event.command_id == "gaa":
            try:
                objects = list(self.client.state.map_objects.values())
                if objects:
                    await self.client.db.save_map_objects(objects)
            except Exception as e:
                logger.error(f"MapScanner: Failed to persist map objects from packet: {e}")

    @property
    def map_objects(self) -> Dict[int, MapObject]:
        """Get all discovered map objects in current session memory."""
        return self.client.state.map_objects

    def get_scanned_chunk_count(self, kingdom_id: int = 0) -> int:
        """Get number of scanned chunks in a kingdom."""
        return len(self._scanned_chunks.get(kingdom_id, set()))

    def is_chunk_scanned(self, kingdom_id: int, x: int, y: int) -> bool:
        """Check if a coordinate belongs to a scanned chunk."""
        chunk_x = x // MAP_STEP
        chunk_y = y // MAP_STEP
        return (chunk_x, chunk_y) in self._scanned_chunks.get(kingdom_id, set())

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
        quit_on_empty: Optional[int] = None,
    ) -> ScanResult:
        """
        Scan an area around a center point at maximum speed.
        """
        start_time = time.time()
        objects_before = len(self.map_objects)

        chunks = self._generate_spiral_pattern(center_x, center_y, radius)
        total_chunks = len(chunks)
        completed = 0
        consecutive_empty = 0

        if kingdom_id not in self._scanned_chunks:
            self._scanned_chunks[kingdom_id] = set()

        self._running = True
        self._stop_event.clear()

        for chunk_x, chunk_y in chunks:
            if self._stop_event.is_set():
                logger.info("Scan cancelled")
                break

            chunk_key = (chunk_x, chunk_y)

            if not rescan and chunk_key in self._scanned_chunks[kingdom_id]:
                completed += 1
                continue

            # Calculate top-left tile coordinates for this chunk
            tile_x = chunk_x * MAP_STEP
            tile_y = chunk_y * MAP_STEP

            try:
                # Ensure we are connected
                if not self.client.connection.connected or not self.client.is_logged_in:
                    await self.client.wait_until_ready()

                objs_before_chunk = len(self.map_objects)

                # GAA command uses AX1, AY1, AX2, AY2.
                # To match 13-tile step, we request size 12 chunks (step-1).
                await self.client.get_map_chunk(kingdom_id, tile_x, tile_y)

                # Small yield
                await asyncio.sleep(0)

                new_in_chunk = len(self.map_objects) - objs_before_chunk
                if new_in_chunk > 0:
                    consecutive_empty = 0
                else:
                    consecutive_empty += 1

                # Update cache and DB for chunk
                self._scanned_chunks[kingdom_id].add(chunk_key)
                await self.client.db.mark_chunk_scanned(kingdom_id, chunk_x, chunk_y)

                if quit_on_empty and consecutive_empty >= quit_on_empty:
                    logger.info(f"MapScanner: Stopping early after {consecutive_empty} empty chunks.")
                    break

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

        self._running = False
        await asyncio.sleep(1.0)

        duration = time.time() - start_time
        objects_found = len(self.map_objects) - objects_before
        summary = await self.get_scan_summary()

        result = ScanResult(
            kingdom_id=kingdom_id,
            chunks_scanned=completed,
            objects_found=objects_found,
            duration=duration,
            targets_by_type=summary["objects_by_type"],
        )

        logger.info(f"High-speed scan complete: {completed} chunks in {duration:.1f}s")
        return result

    async def scan_around_castles(
        self, radius: int = 5, rescan: bool = False, quit_on_empty: Optional[int] = None
    ) -> List[ScanResult]:
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
                quit_on_empty=quit_on_empty,
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

        # 1. Search Database
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

        results = list(targets_dict.values())
        results.sort(key=lambda t: t[1])
        return results

    async def find_npc_targets(self, x: int, y: int, dist: float = 30.0) -> List[Tuple[Any, float]]:
        """Find permanent NPC targets (Robber Barons, etc)."""
        npc_types = [MapObjectType.ROBBER_BARON_CASTLE, MapObjectType.DUNGEON, MapObjectType.BOSS_DUNGEON]
        return await self.find_nearby_targets(x, y, max_distance=dist, target_types=npc_types)

    async def find_player_targets(self, x: int, y: int, dist: float = 50.0) -> List[Tuple[Any, float]]:
        """Find player targets (Castles, Outposts)."""
        player_types = [MapObjectType.CASTLE, MapObjectType.OUTPOST, MapObjectType.CAPITAL]
        return await self.find_nearby_targets(x, y, max_distance=dist, target_types=player_types)

    async def find_event_targets(self, x: int, y: int, dist: float = 40.0) -> List[Tuple[Any, float]]:
        """Find active event targets (Nomads, Samurai, Aliens)."""
        event_types = [
            MapObjectType.NOMAD_CAMP,
            MapObjectType.SAMURAI_CAMP,
            MapObjectType.ALIEN_CAMP,
            MapObjectType.RED_ALIEN_CAMP,
        ]
        return await self.find_nearby_targets(x, y, max_distance=dist, target_types=event_types)

    async def get_scan_summary(self) -> Dict[str, Any]:
        """Get summary including database stats."""
        mem_summary = {kid: len(chunks) for kid, chunks in self._scanned_chunks.items()}
        db_count = await self.client.db.get_object_count()
        db_types = await self.client.db.get_object_counts_by_type()

        readable_types = {}
        category_counts = {"Player": 0, "NPC": 0, "Event": 0, "Resource": 0, "Other": 0}

        for type_id, count in db_types.items():
            try:
                enum_type = MapObjectType(type_id)
                name = enum_type.name
                if enum_type.is_player:
                    category_counts["Player"] += count
                elif enum_type.is_npc:
                    category_counts["NPC"] += count
                elif enum_type.is_event:
                    category_counts["Event"] += count
                elif enum_type.is_resource:
                    category_counts["Resource"] += count
                else:
                    category_counts["Other"] += count
            except ValueError:
                name = f"Unknown({type_id})"
                category_counts["Other"] += count

            readable_types[name] = count

        return {
            "memory_objects": len(self.map_objects),
            "database_objects": db_count,
            "objects_by_type": readable_types,
            "objects_by_category": category_counts,
            "chunks_by_kingdom": mem_summary,
            "total_chunks_scanned": sum(mem_summary.values()),
        }

    def _generate_spiral_pattern(self, center_x: int, center_y: int, radius: int) -> List[Tuple[int, int]]:
        """Generate spiral scan pattern from center outward, ensuring coordinates are positive."""
        # Using MAP_STEP (13) for chunk grid
        center_chunk_x = max(0, center_x // MAP_STEP)
        center_chunk_y = max(0, center_y // MAP_STEP)

        chunks = [(center_chunk_x, center_chunk_y)]

        for r in range(1, radius + 1):
            # Top row
            for x in range(center_chunk_x - r, center_chunk_x + r + 1):
                if x >= 0 and (center_chunk_y - r) >= 0:
                    chunks.append((x, center_chunk_y - r))
            # Bottom row
            for x in range(center_chunk_x - r, center_chunk_x + r + 1):
                if x >= 0:
                    chunks.append((x, center_chunk_y + r))
            # Left column
            for y in range(center_chunk_y - r + 1, center_chunk_y + r):
                if (center_chunk_x - r) >= 0 and y >= 0:
                    chunks.append((center_chunk_x - r, y))
            # Right column
            for y in range(center_chunk_y - r + 1, center_chunk_y + r):
                if y >= 0:
                    chunks.append((center_chunk_x + r, y))

        return chunks
