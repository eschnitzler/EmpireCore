"""
Asynchronous Database storage using SQLModel and aiosqlite.
"""

import logging
from datetime import datetime
from typing import Any, List, Optional, Set, Tuple

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import Field, SQLModel, col, select

logger = logging.getLogger(__name__)


# === Models / Tables ===


class PlayerSnapshot(SQLModel, table=True):
    """Historical snapshot of player progress."""

    id: Optional[int] = Field(default=None, primary_key=True)
    player_id: int = Field(index=True)
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    level: int
    gold: int
    rubies: int


class MapObjectRecord(SQLModel, table=True):
    """Persistent record of a discovered world object."""

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

    kingdom_id: int = Field(primary_key=True)
    chunk_x: int = Field(primary_key=True)
    chunk_y: int = Field(primary_key=True)
    last_scanned: int = Field(default_factory=lambda: int(datetime.now().timestamp()))


# === Database Manager ===


class GameDatabase:
    """Async database manager for EmpireCore."""

    def __init__(self, db_path: str = "empire_data.db"):
        self.db_url = f"sqlite+aiosqlite:///{db_path}"
        self.engine = create_async_engine(self.db_url, echo=False)
        self.async_session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def initialize(self):
        """Create tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info(f"Database initialized: {self.db_url}")

    async def close(self):
        """Shutdown engine."""
        await self.engine.dispose()

    # === Operations ===

    async def save_player_snapshot(self, player: Any):
        """Save a snapshot of the current player state."""
        async with self.async_session_factory() as session:
            snapshot = PlayerSnapshot(
                player_id=player.id,
                level=player.level,
                gold=player.gold,
                rubies=player.rubies,
            )
            session.add(snapshot)
            await session.commit()

    async def save_map_objects(self, objects: List[Any]):
        """Persist multiple map objects."""
        if not objects:
            return

        async with self.async_session_factory() as session:
            for obj in objects:
                record = MapObjectRecord(
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
                # Merge performs an "Insert or Update" based on primary key
                await session.merge(record)
            await session.commit()

    async def mark_chunk_scanned(self, kingdom_id: int, chunk_x: int, chunk_y: int):
        """Mark a chunk as scanned."""
        async with self.async_session_factory() as session:
            record = ScannedChunkRecord(kingdom_id=kingdom_id, chunk_x=chunk_x, chunk_y=chunk_y)
            await session.merge(record)
            await session.commit()

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
            return len(results.scalars().all())  # Note: Inefficient for large DBs, but works for now.
