"""
Database storage for historical data.
"""
import sqlite3
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class GameDatabase:
    """SQLite database for game data."""
    
    def __init__(self, db_path: str = "empire_data.db"):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._create_tables()
    
    def connect(self):
        """Connect to database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
    
    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
    
    def _create_tables(self):
        """Create tables."""
        self.connect()
        cursor = self.conn.cursor()
        
        # Player history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                timestamp INTEGER,
                level INTEGER,
                gold INTEGER,
                rubies INTEGER
            )
        """)
        
        # Battle reports
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS battle_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER UNIQUE,
                timestamp INTEGER,
                attacker_id INTEGER,
                defender_id INTEGER,
                attacker_won INTEGER,
                data TEXT
            )
        """)
        
        self.conn.commit()
        logger.info(f"Database initialized: {self.db_path}")
    
    def save_player_snapshot(self, player):
        """Save player snapshot."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO player_history 
            (player_id, timestamp, level, gold, rubies)
            VALUES (?, ?, ?, ?, ?)
        """, (
            player.id,
            int(datetime.now().timestamp()),
            player.level,
            player.gold,
            player.rubies
        ))
        self.conn.commit()
