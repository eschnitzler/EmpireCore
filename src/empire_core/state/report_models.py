"""
Models for battle reports and events.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class BattleParticipant(BaseModel):
    """A participant in a battle."""

    model_config = ConfigDict(extra="ignore")

    player_id: int
    player_name: str
    alliance_id: Optional[int] = None
    alliance_name: Optional[str] = None

    # Units before battle
    units_before: Dict[int, int] = Field(default_factory=dict)
    # Units after battle
    units_after: Dict[int, int] = Field(default_factory=dict)
    # Losses
    losses: Dict[int, int] = Field(default_factory=dict)


class BattleReport(BaseModel):
    """Battle report."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    RID: int = Field(default=-1)  # Report ID
    T: int = Field(default=0)  # Type
    TS: int = Field(default=0)  # Timestamp
    READ: bool = Field(default=False)  # Read status

    # Battle details
    attacker: Optional[BattleParticipant] = None
    defender: Optional[BattleParticipant] = None

    # Results
    winner: Optional[str] = None  # "attacker" or "defender"
    loot: Dict[str, int] = Field(default_factory=dict)  # Resources looted

    # Location
    target_x: int = 0
    target_y: int = 0
    target_name: Optional[str] = None

    @property
    def report_id(self) -> int:
        return self.RID

    @property
    def report_type(self) -> int:
        return self.T

    @property
    def timestamp(self) -> int:
        return self.TS

    @property
    def is_read(self) -> bool:
        return self.READ

    @property
    def datetime(self) -> datetime:
        """Convert timestamp to datetime."""
        return datetime.fromtimestamp(self.TS)


class EventReport(BaseModel):
    """Generic event report (building complete, etc.)."""

    model_config = ConfigDict(extra="ignore")

    event_id: int
    event_type: str
    timestamp: int
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)


class ReportManager:
    """Manages reports and events."""

    def __init__(self):
        self.battle_reports: Dict[int, BattleReport] = {}
        self.event_reports: Dict[int, EventReport] = {}
        self.unread_count: int = 0

    def add_battle_report(self, report: BattleReport):
        """Add a battle report."""
        self.battle_reports[report.report_id] = report
        if not report.is_read:
            self.unread_count += 1

    def mark_as_read(self, report_id: int):
        """Mark report as read."""
        if report_id in self.battle_reports:
            report = self.battle_reports[report_id]
            if not report.is_read:
                report.READ = True
                self.unread_count = max(0, self.unread_count - 1)

    def get_unread_reports(self) -> List[BattleReport]:
        """Get all unread reports."""
        return [r for r in self.battle_reports.values() if not r.is_read]

    def get_recent_reports(self, count: int = 10) -> List[BattleReport]:
        """Get most recent reports."""
        sorted_reports = sorted(self.battle_reports.values(), key=lambda r: r.timestamp, reverse=True)
        return sorted_reports[:count]
