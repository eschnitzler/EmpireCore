"""
Asynchronous Database storage using SQLModel and aiosqlite with Write Queue.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import Field, SQLModel, col, select

logger = logging.getLogger(__name__)


# === Models / Tables ===


class PlayerSnapshot(SQLModel, table=True):
    """Historical snapshot of player progress."""

    __tablename__ = "player_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    player_id: int = Field(index=True)
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    level: int
    gold: int
    rubies: int


class MapObjectRecord(SQLModel, table=True):
    """Persistent record of a discovered world object."""

    __tablename__ = "map_objects"

    area_id: int = Field(primary_key=True)
    kingdom_id: int = Field(index=True)
    x: int
    y: int
    type: int
    level: int
    name: Optional[str] = None
    owner_id: Optional[int] = None
    owner_name: Optional[str] = None
    alliance_id: Optional[int] = None
    alliance_name: Optional[str] = None
    last_updated: int = Field(default_factory=lambda: int(datetime.now().timestamp()))


class ScannedChunkRecord(SQLModel, table=True):
    """Record of a scanned map chunk."""

    __tablename__ = "scanned_chunks"

    kingdom_id: int = Field(primary_key=True)
    chunk_x: int = Field(primary_key=True)
    chunk_y: int = Field(primary_key=True)
    last_scanned: int = Field(default_factory=lambda: int(datetime.now().timestamp()))


# === Database Manager ===


class GameDatabase:
    """Async database manager with serialized write queue."""

    def __init__(self, db_path: str = "empire_data.db"):
        self.db_url = f"sqlite+aiosqlite:///{db_path}"
        # Set timeout to 30s
        self.engine = create_async_engine(self.db_url, echo=False, connect_args={"timeout": 30})
        self.async_session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

        # Write Queue
        self._write_queue: asyncio.Queue = asyncio.Queue()
        self._writer_task: Optional[asyncio.Task] = None
        self._running = False

    async def initialize(self):
        """Create tables and start writer loop."""
        async with self.engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA synchronous=NORMAL;"))
            await conn.run_sync(SQLModel.metadata.create_all)

        logger.info(f"Database initialized: {self.db_url} (WAL Mode)")
        self._start_writer()

    def _start_writer(self):
        """Start the background writer task."""
        if not self._running:
            self._running = True
            self._writer_task = asyncio.create_task(self._writer_loop())
            logger.debug("Database writer loop started.")

    async def close(self):
        """Shutdown engine and writer."""
        self._running = False
        if self._writer_task:
            # Wait for queue to drain
            await self._write_queue.join()
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass

        await self.engine.dispose()

    async def _writer_loop(self):
        """Consumes write operations from the queue and executes them serially."""
        while self._running:
            try:
                # Get batch of operations
                operation = await self._write_queue.get()
                batch = [operation]

                # Try to grab more if available (up to 50)
                try:
                    for _ in range(50):
                        batch.append(self._write_queue.get_nowait())
                except asyncio.QueueEmpty:
                    pass

                async with self.async_session_factory() as session:
                    try:
                        for op_type, data in batch:
                            if op_type == "player_snapshot":
                                session.add(data)
                            elif op_type == "map_objects":
                                for obj in data:
                                    await session.merge(obj)
                            elif op_type == "scanned_chunk":
                                await session.merge(data)

                        await session.commit()
                    except Exception as e:
                        logger.error(f"Database write error: {e}")
                        await session.rollback()
                    finally:
                        for _ in batch:
                            self._write_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Critical error in writer loop: {e}")
                await asyncio.sleep(1)

    # === Write Operations (Queued) ===

    async def save_player_snapshot(self, player: Any):
        """Queue player snapshot save."""
        snapshot = PlayerSnapshot(
            player_id=player.id,
            level=player.level,
            gold=player.gold,
            rubies=player.rubies,
        )
        await self._write_queue.put(("player_snapshot", snapshot))

    async def save_map_objects(self, objects: List[Any]):
        """Queue map objects save."""
        if not objects:
            return

        records = [
            MapObjectRecord(
                area_id=obj.area_id,
                kingdom_id=obj.kingdom_id,
                x=obj.x,
                y=obj.y,
                type=int(obj.type),
                level=obj.level,
                name=obj.name,
                owner_id=obj.owner_id,
                owner_name=obj.owner_name,
                alliance_id=obj.alliance_id,
                alliance_name=obj.alliance_name,
            )
            for obj in objects
        ]
        await self._write_queue.put(("map_objects", records))

    async def mark_chunk_scanned(self, kingdom_id: int, chunk_x: int, chunk_y: int):
        """Queue chunk scanned mark."""
        record = ScannedChunkRecord(kingdom_id=kingdom_id, chunk_x=chunk_x, chunk_y=chunk_y)
        await self._write_queue.put(("scanned_chunk", record))

    # === Read Operations (Direct) ===

    async def get_scanned_chunks(self, kingdom_id: int) -> Set[Tuple[int, int]]:
        """Get all scanned chunks for a kingdom."""
        async with self.async_session_factory() as session:
            statement = select(ScannedChunkRecord).where(ScannedChunkRecord.kingdom_id == kingdom_id)
            results = await session.execute(statement)
            return {(r.chunk_x, r.chunk_y) for r in results.scalars().all()}

    async def find_targets(
        self,
        kingdom_id: int,
        min_level: int = 0,
        max_level: int = 999,
        types: Optional[List[int]] = None,
    ) -> List[MapObjectRecord]:
        """Query world map from DB."""
        async with self.async_session_factory() as session:
            statement = select(MapObjectRecord).where(
                MapObjectRecord.kingdom_id == kingdom_id,
                MapObjectRecord.level >= min_level,
                MapObjectRecord.level <= max_level,
            )
            if types:
                statement = statement.where(col(MapObjectRecord.type).in_(types))

            results = await session.execute(statement)
            return list(results.scalars().all())

    async def get_object_count(self) -> int:
        """Total discovered objects."""
        async with self.async_session_factory() as session:
            # Simple way to get count in SQLModel
            statement = select(MapObjectRecord)
            results = await session.execute(statement)
            return len(results.scalars().all())

    async def get_object_counts_by_type(self) -> Dict[int, int]:
        """Get counts of objects grouped by type."""
        from sqlalchemy import func

        async with self.async_session_factory() as session:
            statement = select(col(MapObjectRecord.type), func.count(col(MapObjectRecord.area_id))).group_by(
                col(MapObjectRecord.type)
            )
            results = await session.execute(statement)
            return {row[0]: row[1] for row in results.all()}
