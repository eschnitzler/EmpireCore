"""Automation modules for EmpireCore."""

from . import tasks
from .alliance_tools import AllianceService, ChatService
from .battle_reports import BattleReportService
from .building_queue import BuildingManager
from .defense_manager import DefenseManager
from .map_scanner import MapScanner
from .quest_automation import QuestService
from .resource_manager import ResourceManager
from .unit_production import UnitManager

__all__ = [
    "QuestService",
    "BattleReportService",
    "AllianceService",
    "ChatService",
    "MapScanner",
    "ResourceManager",
    "BuildingManager",
    "UnitManager",
    "DefenseManager",
    "tasks",
]
