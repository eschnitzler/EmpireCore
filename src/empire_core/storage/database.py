"""
Database storage for historical data and world mapping.
"""

import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class GameDatabase:
    """SQLite database for game data."""

    def __init__(self, db_path: str = "empire_data.db"):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._create_tables()

    @property
    def connection(self) -> sqlite3.Connection:
        """Get the database connection, ensuring it exists."""
        if self.conn is None:
            self.connect()
        if self.conn is None:
            raise RuntimeError("Failed to connect to database")
        return self.conn

    def connect(self):
        """Connect to database."""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row

    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def _create_tables(self):
        """Create tables if they don't exist."""
        cursor = self.connection.cursor()

        # Player history
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS player_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                timestamp INTEGER,
                level INTEGER,
                gold INTEGER,
                rubies INTEGER
            )
        """
        )

        # Battle reports
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS battle_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER UNIQUE,
                timestamp INTEGER,
                attacker_id INTEGER,
                defender_id INTEGER,
                attacker_won INTEGER,
                data TEXT
            )
        """
        )

        # Map Objects (World Map)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS map_objects (
                area_id INTEGER PRIMARY KEY,
                kingdom_id INTEGER,
                x INTEGER,
                y INTEGER,
                type INTEGER,
                level INTEGER,
                name TEXT,
                owner_id INTEGER,
                owner_name TEXT,
                alliance_id INTEGER,
                alliance_name TEXT,
                last_updated INTEGER
            )
        """
        )

        # Scanned Chunks (to avoid redundant network requests across sessions)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scanned_chunks (
                kingdom_id INTEGER,
                chunk_x INTEGER,
                chunk_y INTEGER,
                last_scanned INTEGER,
                PRIMARY KEY (kingdom_id, chunk_x, chunk_y)
            )
        """
        )

        self.connection.commit()
        logger.info(f"Database initialized: {self.db_path}")

    # === Player Snapshots ===

    def save_player_snapshot(self, player: Any):
        """Save player snapshot."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO player_history 
            (player_id, timestamp, level, gold, rubies)
            VALUES (?, ?, ?, ?, ?)
        """,
            (player.id, int(datetime.now().timestamp()), player.level, player.gold, player.rubies),
        )
        self.connection.commit()

    # === Map Persistence ===

    def save_map_object(self, obj: Any):
        """Save or update a map object in the database."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO map_objects 
            (area_id, kingdom_id, x, y, type, level, name, owner_id, owner_name, alliance_id, alliance_name, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                obj.area_id,
                obj.kingdom_id,
                obj.x,
                obj.y,
                int(obj.type),
                obj.level,
                obj.name,
                obj.owner_id,
                obj.owner_name,
                obj.alliance_id,
                obj.alliance_name,
                int(datetime.now().timestamp()),
            ),
        )
        self.connection.commit()

    def save_map_objects(self, objects: List[Any]):
        """Bulk save map objects."""
        if not objects:
            return
        cursor = self.connection.cursor()
        now = int(datetime.now().timestamp())
        data = [
            (
                obj.area_id,
                obj.kingdom_id,
                obj.x,
                obj.y,
                int(obj.type),
                obj.level,
                obj.name,
                obj.owner_id,
                obj.owner_name,
                obj.alliance_id,
                obj.alliance_name,
                now,
            )
            for obj in objects
        ]
        cursor.executemany(
            """
            INSERT OR REPLACE INTO map_objects 
            (area_id, kingdom_id, x, y, type, level, name, owner_id, owner_name, alliance_id, alliance_name, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            data,
        )
        self.connection.commit()

    def mark_chunk_scanned(self, kingdom_id: int, chunk_x: int, chunk_y: int):
        """Mark a chunk as scanned in the database."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO scanned_chunks (kingdom_id, chunk_x, chunk_y, last_scanned)
            VALUES (?, ?, ?, ?)
        """,
            (kingdom_id, chunk_x, chunk_y, int(datetime.now().timestamp())),
        )
        self.connection.commit()

    def get_scanned_chunks(self, kingdom_id: int) -> Set[Tuple[int, int]]:
        """Get all scanned chunks for a kingdom from database."""
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT chunk_x, chunk_y FROM scanned_chunks WHERE kingdom_id = ?",
            (kingdom_id,),
        )
        return {(row["chunk_x"], row["chunk_y"]) for row in cursor.fetchall()}

    def find_targets(
        self,
        kingdom_id: int,
        min_level: int = 0,
        max_level: int = 999,
        types: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """Query the database for targets matching criteria."""
        cursor = self.connection.cursor()
        query = "SELECT * FROM map_objects WHERE kingdom_id = ? AND level BETWEEN ? AND ?"
        params = [kingdom_id, min_level, max_level]

        if types:
            placeholders = ",".join(["?"] * len(types))
            query += f" AND type IN ({placeholders})"
            params.extend(types)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_object_count(self) -> int:
        """Get total number of objects in database."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM map_objects")
        return cursor.fetchone()["count"]
